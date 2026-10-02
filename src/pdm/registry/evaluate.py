"""Quality gate: evaluate the candidate on the untouched test set and decide
whether it may be promoted. All gating metrics come from config.gate."""

from __future__ import annotations

import io
import json
import logging
import time

import joblib
import mlflow
import numpy as np
import pandas as pd

from pdm.config import path
from pdm.data.labels import LABEL
from pdm.features.build import feature_columns
from pdm.modeling.metrics import classification_metrics
from pdm.registry import tracking

log = logging.getLogger(__name__)


def measure_latency_ms(model, X: pd.DataFrame, n: int = 200) -> dict[str, float]:
    """Single-row predict latency of the model itself (API overhead is measured separately)."""
    rows = [X.iloc[[i % len(X)]] for i in range(n)]
    model.predict_proba(rows[0])  # warm-up
    times = []
    for r in rows:
        t0 = time.perf_counter()
        model.predict_proba(r)
        times.append((time.perf_counter() - t0) * 1000)
    return {"p50": float(np.percentile(times, 50)), "p95": float(np.percentile(times, 95))}


def model_size_mb(model) -> float:
    buf = io.BytesIO()
    joblib.dump(model, buf)
    return buf.tell() / 1e6


def gate_checks(
    metrics: dict, latency_p95_ms: float, size_mb: float, champion_pr_auc: float | None, gate: dict
) -> list[dict]:
    """Pure function -> easy to unit test. Every check must pass."""
    checks = [
        {
            "name": "recall",
            "value": metrics["recall"],
            "rule": f">= {gate['min_recall']}",
            "passed": metrics["recall"] >= gate["min_recall"],
        },
        {
            "name": "precision",
            "value": metrics["precision"],
            "rule": f">= {gate['min_precision']}",
            "passed": metrics["precision"] >= gate["min_precision"],
        },
        {
            "name": "p95_latency_ms",
            "value": latency_p95_ms,
            "rule": f"< {gate['max_p95_latency_ms']}",
            "passed": latency_p95_ms < gate["max_p95_latency_ms"],
        },
        {
            "name": "model_size_mb",
            "value": size_mb,
            "rule": f"< {gate['max_model_size_mb']}",
            "passed": size_mb < gate["max_model_size_mb"],
        },
    ]
    if gate.get("must_beat_champion") and champion_pr_auc is not None:
        checks.append(
            {
                "name": "pr_auc_vs_champion",
                "value": metrics["pr_auc"],
                "rule": f">= {champion_pr_auc:.4f}",
                "passed": metrics["pr_auc"] >= champion_pr_auc,
            }
        )
    return checks


def load_champion(cfg: dict):
    """Return (model, threshold, version) of the current champion, or None."""
    client = mlflow.MlflowClient()
    name = cfg["registry"]["model_name"]
    try:
        mv = client.get_model_version_by_alias(name, "champion")
    except mlflow.exceptions.MlflowException:
        return None
    model = mlflow.sklearn.load_model(f"models:/{name}@champion")
    threshold = float(client.get_run(mv.run_id).data.params["threshold"])
    return model, threshold, mv.version


def evaluate_candidate(run_id: str, test: pd.DataFrame, cfg: dict) -> dict:
    tracking.setup(cfg)
    client = mlflow.MlflowClient()
    numeric, categorical = feature_columns(cfg)
    X, y = test[numeric + categorical], test[LABEL].to_numpy()
    costs = cfg["costs"]

    model = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
    threshold = float(client.get_run(run_id).data.params["threshold"])
    metrics = classification_metrics(
        y, model.predict_proba(X)[:, 1], threshold, costs["false_negative"], costs["false_positive"]
    )
    latency = measure_latency_ms(model, X)
    size = model_size_mb(model)

    champion = load_champion(cfg)
    champion_metrics, champion_version = None, None
    if champion is not None:
        c_model, c_thr, champion_version = champion
        champion_metrics = classification_metrics(
            y, c_model.predict_proba(X)[:, 1], c_thr, costs["false_negative"], costs["false_positive"]
        )

    checks = gate_checks(
        metrics, latency["p95"], size, champion_metrics["pr_auc"] if champion_metrics else None, cfg["gate"]
    )
    report = {
        "run_id": run_id,
        "threshold": threshold,
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "test_metrics": metrics,
        "latency_ms": latency,
        "model_size_mb": size,
        "champion_version": champion_version,
        "champion_test_metrics": champion_metrics,
    }

    with mlflow.start_run(run_id=run_id):
        mlflow.log_metrics({f"test_{k}": v for k, v in metrics.items()})
        mlflow.log_metrics(
            {"model_p50_latency_ms": latency["p50"], "model_p95_latency_ms": latency["p95"], "model_size_mb": size}
        )
        mlflow.log_dict(report, "gate/gate_report.json")
        mlflow.set_tag("gate_passed", str(report["passed"]))

    out = path("reports/gate/latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for c in checks:
        log.info("gate %-20s %-10.4f %-12s %s", c["name"], c["value"], c["rule"], "PASS" if c["passed"] else "FAIL")
    log.info("gate result: %s", "PASSED" if report["passed"] else "REJECTED")
    return report
