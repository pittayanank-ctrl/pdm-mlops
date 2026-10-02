"""Closed loop: monitor recent data -> drift found -> retrain -> gate -> promote (or keep champion).

    python -m pdm.pipelines.retrain_flow --current data/drift/concept_drift.parquet

The recent labelled window is split by time: first 50 % joins the training data,
next 25 % is validation (threshold), last 25 % is the test set on which the new
candidate must beat the current champion.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
from prefect import flow, task
from prefect.cache_policies import NO_CACHE

from pdm.config import load_config, path
from pdm.data.versioning import data_version
from pdm.modeling.train import train_experiments
from pdm.monitoring.monitor import run_monitoring
from pdm.registry.evaluate import evaluate_candidate
from pdm.registry.register import notify_api_reload, register_candidate

TASK = dict(cache_policy=NO_CACHE)


@task(name="monitor", **TASK)
def monitor(cur, cfg, name):
    return run_monitoring(cur, cfg, name)


@task(name="build-retrain-splits", **TASK)
def retrain_splits(cur: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    processed = path(cfg["data"]["processed_dir"])
    old = pd.concat([pd.read_parquet(processed / "train.parquet"), pd.read_parquet(processed / "val.parquet")])
    old = old[old["datetime"] < cur["datetime"].min()]  # never mix two versions of the same hours
    cur = cur.sort_values("datetime").drop(columns=["probability", "prediction", "model_version"], errors="ignore")
    t = cur["datetime"].drop_duplicates().sort_values().reset_index(drop=True)
    cut1, cut2 = t.iloc[int(len(t) * 0.5)], t.iloc[int(len(t) * 0.75)]
    # the world changed: recent rows describe it better, so they count more than old ones
    recent = cur[cur["datetime"] < cut1].assign(sample_weight=float(cfg["retrain"]["recent_weight"]))
    return {
        "train": pd.concat([old.assign(sample_weight=1.0), recent], ignore_index=True),
        "val": cur[(cur["datetime"] >= cut1) & (cur["datetime"] < cut2)].reset_index(drop=True),
        "test": cur[cur["datetime"] >= cut2].reset_index(drop=True),
    }


@task(name="train", **TASK)
def train(splits, cfg, version):
    return train_experiments(splits, cfg, version)


@task(name="evaluate-gate", **TASK)
def evaluate(run_id, test, cfg):
    return evaluate_candidate(run_id, test, cfg)


@task(name="register", **TASK)
def register(run_id, report, cfg):
    return register_candidate(run_id, report, cfg)


@flow(name="pdm-retrain-on-drift", log_prints=True)
def retrain_on_drift(current: str) -> dict:
    cfg = load_config()
    cur = pd.read_parquet(current)
    report = monitor(cur, cfg, Path(current).stem)
    decision = report["decision"]
    print(f"monitoring decision: {decision}")
    if not decision["retrain"]:
        return {"retrained": False, "decision": decision}

    splits = retrain_splits(cur, cfg)
    trained = train(splits, cfg, data_version([path(current)]))
    gate = evaluate(trained["candidate_run_id"], splits["test"], cfg)
    version = register(trained["candidate_run_id"], gate, cfg)
    if gate["passed"]:
        notify_api_reload()
    result = {
        "retrained": True,
        "decision": decision,
        "candidate": trained["candidate_name"],
        "model_version": version,
        "promoted": gate["passed"],
        "candidate_test_pr_auc": gate["test_metrics"]["pr_auc"],
        "champion_test_pr_auc": (gate["champion_test_metrics"] or {}).get("pr_auc"),
    }
    print(result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, help="parquet produced by pdm.monitoring.simulate_drift")
    retrain_on_drift(parser.parse_args().current)


if __name__ == "__main__":
    main()
