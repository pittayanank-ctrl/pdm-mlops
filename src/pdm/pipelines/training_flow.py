"""End-to-end DAG: raw data -> validate -> features -> split -> train -> evaluate -> register -> serve.

python -m pdm.pipelines.training_flow                  # full run
python -m pdm.pipelines.training_flow --fail-on-reject # exit 1 if the gate rejects (CI)
"""

from __future__ import annotations

import argparse
import logging
import sys

from prefect import flow, task
from prefect.cache_policies import NO_CACHE

from pdm.config import load_config
from pdm.modeling.train import train_experiments
from pdm.pipelines import steps
from pdm.registry.evaluate import evaluate_candidate
from pdm.registry.register import notify_api_reload, register_candidate

TASK = dict(cache_policy=NO_CACHE)


@task(name="ingest", retries=2, retry_delay_seconds=10, **TASK)
def ingest(cfg):
    return steps.ingest_step(cfg)


@task(name="validate", **TASK)
def validate(tables, cfg):
    steps.validate_step(tables, cfg)


@task(name="build-features", **TASK)
def features(tables, cfg):
    return steps.features_step(tables, cfg)


@task(name="split", **TASK)
def split(df, cfg):
    return steps.split_step(df, cfg)


@task(name="save-reference", **TASK)
def reference(train, cfg):
    return steps.reference_step(train, cfg)


@task(name="train", **TASK)
def train(splits, cfg, version):
    return train_experiments(splits, cfg, version)


@task(name="evaluate-gate", **TASK)
def evaluate(run_id, test, cfg):
    return evaluate_candidate(run_id, test, cfg)


@task(name="register", **TASK)
def register(run_id, report, cfg):
    return register_candidate(run_id, report, cfg)


@task(name="reload-api", **TASK)
def reload_api():
    notify_api_reload()


@flow(name="pdm-training-pipeline", log_prints=True)
def training_pipeline() -> dict:
    cfg = load_config()
    tables, version = ingest(cfg)
    validate(tables, cfg)  # raises DataValidationError -> the whole flow stops here
    df = features(tables, cfg)
    splits = split(df, cfg)
    reference(splits["train"], cfg)
    trained = train(splits, cfg, version)
    report = evaluate(trained["candidate_run_id"], splits["test"], cfg)
    model_version = register(trained["candidate_run_id"], report, cfg)
    if report["passed"]:
        reload_api()
    result = {
        "data_version": version,
        "candidate": trained["candidate_name"],
        "model_version": model_version,
        "promoted": report["passed"],
    }
    print(result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-reject", action="store_true", help="exit 1 if the candidate fails the gate")
    args = parser.parse_args()
    result = training_pipeline()
    if args.fail_on_reject and not result["promoted"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
