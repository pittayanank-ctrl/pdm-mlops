"""build_features() is THE feature code. train.py and the API both call it,
which is how we prevent training-serving skew.

One output row per (machineID, datetime) that has a full history window:
  - rolling mean/std of each sensor over 3 h and 24 h
  - count of each error type in the last 24 h
  - days since each component was last replaced/serviced
  - machine model and age
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pdm.config import load_config
from pdm.validation.cleaning import clean_telemetry

CATEGORICAL = ["model"]


def feature_columns(cfg: dict | None = None) -> tuple[list[str], list[str]]:
    """Return (numeric, categorical) feature names in a fixed order."""
    fc = (cfg or load_config())["features"]
    numeric = [f"{s}_{stat}_{w}h" for w in fc["windows_hours"] for s in fc["sensors"] for stat in ("mean", "std")]
    numeric += [f"{e}_count_24h" for e in fc["error_types"]]
    numeric += [f"days_since_{c}" for c in fc["components"]]
    numeric += ["age"]
    return numeric, CATEGORICAL


def maint_with_failures(maint: pd.DataFrame, failures: pd.DataFrame) -> pd.DataFrame:
    """A failure means the component was replaced, so it also resets 'days since maintenance'."""
    f = failures.rename(columns={"failure": "comp"})[["datetime", "machineID", "comp"]]
    return pd.concat([maint[["datetime", "machineID", "comp"]], f], ignore_index=True).drop_duplicates()


def _rolling_sensors(tel: pd.DataFrame, sensors: list[str], windows: list[int]) -> pd.DataFrame:
    out = {}
    grouped = tel.set_index("datetime").groupby("machineID")[sensors]
    for w in windows:
        roll = grouped.rolling(f"{w}h", min_periods=1)
        mean, std = roll.mean(), roll.std()
        for s in sensors:
            out[f"{s}_mean_{w}h"] = mean[s].to_numpy()
            out[f"{s}_std_{w}h"] = std[s].fillna(0.0).to_numpy()
    return pd.DataFrame(out, index=tel.index)


def _error_counts(tel: pd.DataFrame, errors: pd.DataFrame, error_types: list[str]) -> pd.DataFrame:
    grid = tel[["machineID", "datetime"]].copy()
    if len(errors):
        e = errors.assign(datetime=errors["datetime"].dt.floor("h"))
        onehot = (
            pd.crosstab([e["machineID"], e["datetime"]], e["errorID"])
            .reindex(columns=error_types, fill_value=0)
            .reset_index()
        )
        grid = grid.merge(onehot, on=["machineID", "datetime"], how="left")
    for col in error_types:
        if col not in grid:
            grid[col] = 0
    grid[error_types] = grid[error_types].fillna(0).astype(float)
    counts = grid.set_index("datetime").groupby("machineID")[error_types].rolling("24h", min_periods=1).sum()
    return pd.DataFrame({f"{c}_count_24h": counts[c].to_numpy() for c in error_types}, index=tel.index)


def _days_since_maint(tel: pd.DataFrame, maint: pd.DataFrame, components: list[str], cap_days: float) -> pd.DataFrame:
    if maint.empty:  # e.g. an API request without maintenance history
        return pd.DataFrame({f"days_since_{c}": float(cap_days) for c in components}, index=tel.index)
    maint = maint.astype({"machineID": tel["machineID"].dtype})
    left = tel[["machineID", "datetime"]].reset_index().sort_values("datetime")
    # wide table: at each maintenance event, the latest service time of every component so far
    events = (
        maint.assign(last=maint["datetime"])
        .groupby(["machineID", "datetime", "comp"])["last"]
        .max()
        .unstack("comp")
        .reindex(columns=components)
        .groupby(level="machineID")
        .ffill()
        .reset_index()
        .sort_values("datetime")
    )
    merged = pd.merge_asof(left, events, on="datetime", by="machineID", direction="backward").set_index("index")
    merged = merged.reindex(tel.index)
    out = pd.DataFrame(index=tel.index)
    for comp in components:
        days = (merged["datetime"] - pd.to_datetime(merged[comp])).dt.total_seconds() / 86400
        out[f"days_since_{comp}"] = days.fillna(cap_days).clip(upper=cap_days).to_numpy()
    return out


def build_features(
    telemetry: pd.DataFrame,
    errors: pd.DataFrame,
    maint: pd.DataFrame,
    machines: pd.DataFrame,
    cfg: dict | None = None,
    sample_every_hours: int | None = None,
) -> pd.DataFrame:
    """Return one feature row per (machineID, datetime) with a full 24 h history.

    `maint` should already include failures (see maint_with_failures) when training.
    `sample_every_hours` keeps only rows on that hour grid (training); serving passes None.
    """
    cfg = cfg or load_config()
    fc = cfg["features"]
    max_window = max(fc["windows_hours"])

    tel = clean_telemetry(telemetry, cfg)
    feats = pd.concat(
        [
            tel[["machineID", "datetime"]],
            _rolling_sensors(tel, fc["sensors"], fc["windows_hours"]),
            _error_counts(tel, errors, fc["error_types"]),
            _days_since_maint(tel, maint, fc["components"], fc["max_days_since_maint"]),
        ],
        axis=1,
    )
    feats = feats.merge(machines[["machineID", "model", "age"]], on="machineID", how="left")
    feats["age"] = feats["age"].astype(float)

    # only keep rows whose 24 h window is complete (same rule in training and serving)
    first_seen = feats.groupby("machineID")["datetime"].transform("min")
    feats = feats[feats["datetime"] >= first_seen + pd.Timedelta(hours=max_window - 1)]
    if sample_every_hours:
        feats = feats[feats["datetime"].dt.hour % sample_every_hours == 0]

    numeric, categorical = feature_columns(cfg)
    feats[numeric] = feats[numeric].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return feats[["machineID", "datetime", *numeric, *categorical]].reset_index(drop=True)


def build_training_table(tables: dict[str, pd.DataFrame], cfg: dict | None = None) -> pd.DataFrame:
    """Features + label for the whole history (used by the training pipeline)."""
    from pdm.data.labels import add_labels

    cfg = cfg or load_config()
    feats = build_features(
        tables["telemetry"],
        tables["errors"],
        maint_with_failures(tables["maint"], tables["failures"]),
        tables["machines"],
        cfg,
        sample_every_hours=cfg["features"]["sample_every_hours"],
    )
    return add_labels(feats, tables["failures"], cfg["label"]["horizon_hours"])
