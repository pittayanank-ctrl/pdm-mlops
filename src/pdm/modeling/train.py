"""Train every experiment in config, log each one to MLflow, pick the candidate.

Selection: best validation PR-AUC (optimizing metric). The decision threshold is
chosen on validation data by minimising business cost. Test data is NOT touched
here - that is evaluate.py's job.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from mlflow.models import infer_signature  # noqa: E402
from sklearn.metrics import ConfusionMatrixDisplay, PrecisionRecallDisplay  # noqa: E402

from pdm.config import path  # noqa: E402
from pdm.data.labels import LABEL  # noqa: E402
from pdm.features.build import feature_columns  # noqa: E402
from pdm.modeling.metrics import choose_threshold, classification_metrics  # noqa: E402
from pdm.modeling.models import make_model  # noqa: E402
from pdm.registry import tracking  # noqa: E402

log = logging.getLogger(__name__)


def _plots(y, proba, threshold, name, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pr_path, cm_path = out_dir / "pr_curve.png", out_dir / "confusion_matrix.png"
    fig, ax = plt.subplots(figsize=(5, 4))
    PrecisionRecallDisplay.from_predictions(y, proba, ax=ax, name=name)
    fig.tight_layout()
    fig.savefig(pr_path, dpi=100)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(4, 4))
    ConfusionMatrixDisplay.from_predictions(y, (proba >= threshold).astype(int), ax=ax, colorbar=False)
    ax.set_title(f"{name} @ threshold {threshold:.2f}")
    fig.tight_layout()
    fig.savefig(cm_path, dpi=100)
    plt.close(fig)
    return [pr_path, cm_path]


def _feature_importance(model, numeric: list[str]) -> pd.DataFrame | None:
    clf = model.named_steps["clf"]
    try:
        names = list(model.named_steps["pre"].get_feature_names_out())
    except Exception:  # rule baseline has no meaningful names
        return None
    if hasattr(clf, "feature_importances_"):
        values = clf.feature_importances_
    elif hasattr(clf, "coef_"):
        values = np.abs(clf.coef_[0])
    else:
        return None
    return pd.DataFrame({"feature": names, "importance": values}).sort_values("importance", ascending=False)


def train_experiments(splits: dict[str, pd.DataFrame], cfg: dict, data_version: str) -> dict:
    tracking.setup(cfg)
    numeric, categorical = feature_columns(cfg)
    cols = numeric + categorical
    tr, va = splits["train"], splits["val"]
    X_tr, y_tr, X_va, y_va = tr[cols], tr[LABEL].to_numpy(), va[cols], va[LABEL].to_numpy()
    # optional per-row weight (retraining after drift gives recent rows more weight)
    weight = tr["sample_weight"].to_numpy() if "sample_weight" in tr else None
    pos_weight = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))
    costs = cfg["costs"]

    results = []
    for exp in cfg["experiments"]:
        with mlflow.start_run(run_name=exp["name"]) as run:
            tracking.log_run_context(cfg, data_version)
            mlflow.log_params(
                {
                    "model_kind": exp["model"],
                    **exp["params"],
                    "seed": cfg["seed"],
                    "n_train": len(tr),
                    "n_val": len(va),
                    "n_features": len(cols),
                    "train_positive_rate": round(float(y_tr.mean()), 4),
                    "weighted": weight is not None,
                }
            )

            model = make_model(exp["model"], exp["params"], numeric, categorical, cfg["seed"], pos_weight)
            t0 = time.perf_counter()
            model.fit(X_tr, y_tr, **({"clf__sample_weight": weight} if weight is not None else {}))
            train_seconds = time.perf_counter() - t0

            proba = model.predict_proba(X_va)[:, 1]
            threshold = choose_threshold(
                y_va,
                proba,
                costs["false_negative"],
                costs["false_positive"],
                min_recall=cfg["gate"]["min_recall"] + cfg["gate"].get("threshold_margin", 0.0),
                min_precision=cfg["gate"]["min_precision"] + cfg["gate"].get("threshold_margin", 0.0),
            )
            metrics = classification_metrics(y_va, proba, threshold, costs["false_negative"], costs["false_positive"])
            mlflow.log_param("threshold", threshold)
            mlflow.log_metrics({f"val_{k}": v for k, v in metrics.items()} | {"train_seconds": train_seconds})

            art_dir = path("reports/experiments") / exp["name"]
            for p in _plots(y_va, proba, threshold, exp["name"], art_dir):
                mlflow.log_artifact(str(p), "plots")
            fi = _feature_importance(model, numeric)
            if fi is not None:
                fi.to_csv(art_dir / "feature_importance.csv", index=False)
                mlflow.log_artifact(str(art_dir / "feature_importance.csv"), "explain")

            mlflow.sklearn.log_model(
                model, "model", signature=infer_signature(X_va.head(20), proba[:20]), input_example=X_va.head(3)
            )
            results.append(
                {
                    "name": exp["name"],
                    "run_id": run.info.run_id,
                    "threshold": threshold,
                    **{f"val_{k}": v for k, v in metrics.items()},
                }
            )
            log.info(
                "%-14s val PR-AUC=%.3f recall=%.3f precision=%.3f thr=%.2f",
                exp["name"],
                metrics["pr_auc"],
                metrics["recall"],
                metrics["precision"],
                threshold,
            )

    table = pd.DataFrame(results).sort_values("val_pr_auc", ascending=False, na_position="last")
    out = path("reports/experiments/comparison.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    best = table.iloc[0]
    mlflow.MlflowClient().set_tag(best["run_id"], "candidate", "true")
    log.info("candidate: %s (run %s)", best["name"], best["run_id"])
    return {"candidate_run_id": best["run_id"], "candidate_name": best["name"], "results": results}
