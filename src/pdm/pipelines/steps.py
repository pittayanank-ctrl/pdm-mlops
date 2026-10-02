"""Plain-Python pipeline steps. Prefect flows wrap these as tasks; tests can call them directly."""

from __future__ import annotations

import logging

import pandas as pd

from pdm.config import load_config, path
from pdm.data import ingest
from pdm.data.split import split_by_time
from pdm.data.versioning import data_version
from pdm.features.build import build_training_table, feature_columns
from pdm.validation.schema import feature_schema
from pdm.validation.validate import validate_or_raise

log = logging.getLogger(__name__)


def ingest_step(cfg: dict) -> tuple[dict[str, pd.DataFrame], str]:
    ingest.download(cfg)
    raw_dir = path(cfg["data"]["raw_dir"])
    version = data_version([raw_dir / f for f in cfg["data"]["files"].values()])
    log.info("data version %s", version)
    return ingest.load_raw(cfg), version


def validate_step(tables: dict[str, pd.DataFrame], cfg: dict) -> None:
    validate_or_raise(tables, cfg, source=cfg["data"]["raw_dir"])


def features_step(tables: dict[str, pd.DataFrame], cfg: dict) -> pd.DataFrame:
    df = build_training_table(tables, cfg)
    numeric, _ = feature_columns(cfg)
    feature_schema(numeric).validate(df)  # catch feature bugs before training
    out = path(cfg["data"]["processed_dir"])
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "features.parquet", index=False)
    log.info("features: %d rows, positive rate %.3f", len(df), df["will_fail_24h"].mean())
    return df


def split_step(df: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    splits = split_by_time(df, cfg["split"])
    out = path(cfg["data"]["processed_dir"])
    for name, part in splits.items():
        part.to_parquet(out / f"{name}.parquet", index=False)
        log.info("%-5s %7d rows  %4d positives", name, len(part), int(part["will_fail_24h"].sum()))
    return splits


def reference_step(train: pd.DataFrame, cfg: dict) -> str:
    """Reference sample of training features for drift monitoring."""
    n = min(cfg["monitoring"]["reference_sample_rows"], len(train))
    ref = train.sample(n=n, random_state=cfg["seed"])
    out = path(cfg["data"]["processed_dir"]) / "reference.parquet"
    ref.to_parquet(out, index=False)
    return str(out)


def default_cfg() -> dict:
    return load_config()
