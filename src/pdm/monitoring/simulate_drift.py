"""Simulate production data after something changed, score it with the champion,
and save it for monitoring + retraining demos.

    python -m pdm.monitoring.simulate_drift --scenario none     # control: test period as-is
    python -m pdm.monitoring.simulate_drift --scenario data     # sensors recalibrated / new environment
    python -m pdm.monitoring.simulate_drift --scenario concept  # new failure mode, inputs unchanged
    python -m pdm.monitoring.simulate_drift --scenario data --send-to-api 200   # also hit the live API

Data drift  : raw telemetry is shifted (vibration +20 %, pressure +15 %, volt +10 %) and features are
              rebuilt with the normal pipeline. Labels unchanged.
Concept drift: features unchanged, the ground truth changes - a new failure mode appears
              (high short-term pressure variance on model1/model2 machines).
Output: data/drift/<scenario>.parquet with features, will_fail_24h, probability, prediction.
"""

from __future__ import annotations

import argparse
import logging
import os

import numpy as np
import pandas as pd
import requests

from pdm.config import load_config, path
from pdm.data.ingest import load_raw
from pdm.data.labels import LABEL
from pdm.features.build import build_training_table, feature_columns
from pdm.serving.model_loader import load_champion
from pdm.serving.payloads import make_payload

log = logging.getLogger(__name__)


def _window(cfg) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Production period after training = validation + test months (enough labels to retrain on)."""
    return pd.Timestamp(cfg["split"]["val"][0]), pd.Timestamp(cfg["split"]["test"][1])


def data_drift(tables: dict, cfg: dict, seed: int) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    start, end = _window(cfg)
    tel = tables["telemetry"].copy()
    m = (tel["datetime"] >= start - pd.Timedelta(hours=24)) & (tel["datetime"] < end)
    tel.loc[m, "vibration"] *= 1.20
    tel.loc[m, "pressure"] = tel.loc[m, "pressure"] * 1.15 + rng.normal(0, 5, m.sum())
    tel.loc[m, "volt"] *= 1.10
    drifted = {**tables, "telemetry": tel}
    df = build_training_table(drifted, cfg)
    return df[(df["datetime"] >= start) & (df["datetime"] < end)].reset_index(drop=True), drifted


def concept_drift(tables: dict, cfg: dict) -> pd.DataFrame:
    """Same inputs, different outcome: a new failure mode appears on model1/model2 machines
    (e.g. a new batch of seals that fails when pressure fluctuates). The old model has never
    seen failures in this region, so its live recall drops although no input feature moved."""
    start, end = _window(cfg)
    df = build_training_table(tables, cfg)
    df = df[(df["datetime"] >= start) & (df["datetime"] < end)].reset_index(drop=True)
    candidates = df["model"].isin(["model1", "model2"])
    cut = df.loc[candidates, "pressure_std_3h"].quantile(0.93)
    df.loc[candidates & (df["pressure_std_3h"] >= cut), LABEL] = 1
    return df


def score(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    bundle = load_champion(cfg)
    numeric, categorical = feature_columns(cfg)
    df = df.copy()
    df["probability"] = bundle.model.predict_proba(df[numeric + categorical])[:, 1]
    df["prediction"] = (df["probability"] >= bundle.threshold).astype(int)
    df["model_version"] = bundle.version
    return df


def send_to_api(tables: dict, df: pd.DataFrame, n: int, url: str, seed: int) -> None:
    sample = df.sample(n=min(n, len(df)), random_state=seed)
    ok = 0
    with requests.Session() as s:
        for r in sample.itertuples():
            body = make_payload(tables, int(r.machineID), r.datetime)
            ok += s.post(f"{url}/predict", json=body, timeout=10).status_code == 200
    log.info("sent %d requests to %s (%d ok)", len(sample), url, ok)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["none", "data", "concept"], required=True)
    parser.add_argument("--send-to-api", type=int, default=0, metavar="N")
    parser.add_argument("--url", default=os.environ.get("API_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    cfg = load_config()
    tables = load_raw(cfg)

    if args.scenario == "data":
        df, used_tables = data_drift(tables, cfg, cfg["seed"])
    elif args.scenario == "concept":
        df, used_tables = concept_drift(tables, cfg), tables
    else:
        start, end = _window(cfg)
        df = build_training_table(tables, cfg)
        df, used_tables = df[(df["datetime"] >= start) & (df["datetime"] < end)].reset_index(drop=True), tables

    df = score(df, cfg)
    out = path("data/drift") / f"{args.scenario}_drift.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"{out}: {len(df)} rows, positives={int(df[LABEL].sum())}, predicted={int(df['prediction'].sum())}")
    if args.send_to_api:
        send_to_api(used_tables, df, args.send_to_api, args.url, cfg["seed"])


if __name__ == "__main__":
    main()
