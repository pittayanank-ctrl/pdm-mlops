"""Batch scoring once per shift: rank every machine by failure risk.

    python -m pdm.serving.batch                          # as of the latest telemetry hour
    python -m pdm.serving.batch --as-of 2015-12-01T06:00
Writes reports/batch/scores_<as_of>.csv for the maintenance planner.
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from pdm.config import load_config, path
from pdm.data.ingest import load_raw
from pdm.features.build import build_features, feature_columns, maint_with_failures
from pdm.serving.model_loader import load_champion

log = logging.getLogger(__name__)


def score_all(tables: dict[str, pd.DataFrame], as_of: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    bundle = load_champion(cfg)
    start = as_of - pd.Timedelta(hours=cfg["serving"]["history_hours"] - 1)
    tel = tables["telemetry"]
    tel = tel[(tel["datetime"] >= start) & (tel["datetime"] <= as_of)]
    err = tables["errors"]
    err = err[(err["datetime"] >= start) & (err["datetime"] <= as_of)]
    maint = maint_with_failures(tables["maint"], tables["failures"])
    maint = maint[maint["datetime"] <= as_of]

    feats = build_features(tel, err, maint, tables["machines"], cfg)
    latest = feats[feats["datetime"] == as_of].copy()
    numeric, categorical = feature_columns(cfg)
    latest["failure_probability"] = bundle.model.predict_proba(latest[numeric + categorical])[:, 1]
    latest["will_fail_24h"] = latest["failure_probability"] >= bundle.threshold
    latest["model_version"] = bundle.version
    cols = ["machineID", "datetime", "failure_probability", "will_fail_24h", "model_version", "model", "age"]
    return latest[cols].sort_values("failure_probability", ascending=False).reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", help="timestamp to score (default: latest telemetry hour)")
    args = parser.parse_args()
    cfg = load_config()
    tables = load_raw(cfg)
    as_of = pd.Timestamp(args.as_of) if args.as_of else tables["telemetry"]["datetime"].max()
    scores = score_all(tables, as_of, cfg)
    out = path("reports/batch") / f"scores_{as_of:%Y%m%d_%H%M}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out, index=False)
    print(scores.head(10).to_string(index=False))
    print(f"\n{int(scores['will_fail_24h'].sum())} of {len(scores)} machines flagged -> {out}")


if __name__ == "__main__":
    main()
