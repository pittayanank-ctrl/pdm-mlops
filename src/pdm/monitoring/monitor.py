"""Run the monitoring checks on a window of recent data.

    python -m pdm.monitoring.monitor --current data/drift/data_drift.parquet
    python -m pdm.monitoring.monitor --from-logs        # API prediction log + /feedback labels
    python -m pdm.monitoring.monitor --from-logs --last 500   # only the 500 most recent predictions

Writes reports/monitoring/<name>.json + .html and alerts when drift is found.
Prediction quality: live recall/precision (needs labels) + predicted-positive rate.
System health (latency, errors, uptime) is watched by Prometheus/Grafana alert rules.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.metrics import average_precision_score, precision_score, recall_score

from pdm.config import ROOT, load_config, path
from pdm.data.labels import LABEL
from pdm.features.build import feature_columns
from pdm.monitoring.drift import detect_data_drift
from pdm.monitoring.retrain_policy import decide

log = logging.getLogger(__name__)


def live_performance(cur: pd.DataFrame) -> dict | None:
    """Recall/precision of what the model said vs. what really happened."""
    if LABEL not in cur or "prediction" not in cur:
        return None
    labelled = cur.dropna(subset=[LABEL])
    if labelled.empty or labelled[LABEL].sum() == 0:
        return None
    y, pred = labelled[LABEL].astype(int), labelled["prediction"].astype(int)
    out = {
        "n_labelled": int(len(labelled)),
        "positives": int(y.sum()),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "precision": float(precision_score(y, pred, zero_division=0)),
    }
    if "probability" in labelled and y.nunique() == 2:
        out["pr_auc"] = float(average_precision_score(y, labelled["probability"]))
    return out


def send_alert(message: str, cfg: dict) -> None:
    log.error("ALERT: %s", message)
    url = os.environ.get(cfg["validation"]["alert_webhook_env"])
    if url:
        try:
            requests.post(url, json={"content": message[:1900], "text": message[:1900]}, timeout=5)
        except requests.RequestException as e:
            log.warning("webhook alert failed: %s", e)


def _row(f: dict) -> str:
    bg = "#fde2e2" if f["drifted"] else "white"
    ks = "" if f["ks_pvalue"] is None else f"{f['ks_pvalue']:.2g}"
    flag = "DRIFT" if f["drifted"] else ""
    return (
        f"<tr style='background:{bg}'><td>{f['feature']}</td><td>{f['psi']:.3f}</td><td>{ks}</td><td>{flag}</td></tr>"
    )


def _html(report: dict) -> str:
    rows = "".join(_row(f) for f in report["data_drift"]["features"])
    perf = report["performance"]
    perf_html = (
        "<p>No ground-truth labels in this window.</p>"
        if perf is None
        else (
            "<ul>"
            + "".join(
                f"<li>{k}: {v:.3f}</li>" if isinstance(v, float) else f"<li>{k}: {v}</li>" for k, v in perf.items()
            )
            + "</ul>"
        )
    )
    d = report["decision"]
    return f"""<!doctype html><meta charset="utf-8"><title>Monitoring {report['name']}</title>
<body style="font-family:sans-serif;max-width:900px;margin:2em auto">
<h1>Monitoring report: {report['name']}</h1>
<p><b>Status:</b> {d['status']} &mdash; retrain: <b>{d['retrain']}</b> ({d['reason']})</p>
<p>Rows: {report['rows']} &middot; predicted positive rate: {report['predicted_positive_rate']}</p>
<h2>Prediction quality</h2>{perf_html}
<h2>Data drift (share {report['data_drift']['drift_share']:.0%}, threshold
{report['thresholds']['drift_share_threshold']:.0%}, PSI &gt; {report['thresholds']['psi_threshold']})</h2>
<table border="1" cellpadding="4" style="border-collapse:collapse">
<tr><th>feature</th><th>PSI</th><th>KS p-value</th><th></th></tr>{rows}</table></body>"""


def run_monitoring(cur: pd.DataFrame, cfg: dict, name: str) -> dict:
    mc = cfg["monitoring"]
    numeric, categorical = feature_columns(cfg)
    ref = pd.read_parquet(path(cfg["data"]["processed_dir"]) / "reference.parquet")

    drift = detect_data_drift(ref, cur, numeric, categorical, mc)
    perf = live_performance(cur)
    concept = perf is not None and perf["recall"] < mc["min_recall"]
    decision = decide(drift["data_drift"], concept)
    report = {
        "name": name,
        "rows": int(len(cur)),
        "predicted_positive_rate": round(float(cur["prediction"].mean()), 4) if "prediction" in cur else None,
        "thresholds": {k: mc[k] for k in ("psi_threshold", "drift_share_threshold", "min_recall")},
        "data_drift": drift,
        "performance": perf,
        "concept_drift": concept,
        "decision": decision,
    }

    out = path(mc["report_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out / f"{name}.html").write_text(_html(report), encoding="utf-8")

    if decision["status"] != "no_drift":
        msg = (
            f"[{name}] {decision['status']}: drift share {drift['drift_share']:.0%} "
            f"({', '.join(drift['drifted_features'][:6])})"
        )
        if perf:
            msg += f"; live recall {perf['recall']:.2f} (min {mc['min_recall']})"
        send_alert(msg + f" -> {decision['reason']}", cfg)
    log.info("monitoring %s: %s (report %s)", name, decision["status"], out / f"{name}.html")
    return report


def _read_jsonl(log_dir: Path, kind: str) -> pd.DataFrame:
    """Read every worker's log file; skip a line that is cut off (e.g. a crash mid-write)."""
    rows = []
    for f in sorted(log_dir.glob(f"{kind}*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("skipping corrupt line in %s", f.name)
    return pd.DataFrame(rows)


def load_from_logs(log_dir: Path, last: int | None = None) -> pd.DataFrame:
    preds = _read_jsonl(log_dir, "predictions")
    if preds.empty:
        raise SystemExit(f"no prediction logs in {log_dir}")
    preds = preds.sort_values("logged_at").reset_index(drop=True)
    if last:
        preds = preds.tail(last).reset_index(drop=True)
    feats = pd.json_normalize(preds["features"].tolist())
    cur = pd.concat([preds.drop(columns=["features"]), feats], axis=1)
    # the API response field has the same name as the label column; it is a PREDICTION, not ground truth
    cur["prediction"] = cur.pop("will_fail_24h").astype(int)
    cur["probability"] = cur["failure_probability"]
    fb = _read_jsonl(log_dir, "feedback")
    if not fb.empty:
        fb = fb[["request_id", "actual_failure"]].drop_duplicates("request_id", keep="last")
        cur = cur.merge(fb, on="request_id", how="left")
        cur[LABEL] = cur["actual_failure"].map({True: 1, False: 0})
    return cur


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--current", help="parquet with features (+ prediction/probability/label)")
    src.add_argument("--from-logs", action="store_true", help="use the API's prediction + feedback logs")
    parser.add_argument("--last", type=int, help="with --from-logs: only the N most recent predictions")
    args = parser.parse_args()
    cfg = load_config()
    if args.from_logs:
        cur, name = load_from_logs(Path(os.environ.get("PDM_LOG_DIR", ROOT / "logs")), args.last), "live"
    else:
        cur, name = pd.read_parquet(args.current), Path(args.current).stem
    report = run_monitoring(cur, cfg, name)
    print(json.dumps({k: report[k] for k in ("name", "rows", "concept_drift", "decision")}, indent=2))
    print("drifted features:", report["data_drift"]["drifted_features"])
    print("performance:", report["performance"])
    if np.isnan(report["data_drift"]["drift_share"]):
        raise SystemExit("no features compared")


if __name__ == "__main__":
    main()
