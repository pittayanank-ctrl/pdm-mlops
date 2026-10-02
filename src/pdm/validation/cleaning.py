"""Missing values and outliers. Used by build_features, so training and serving
clean data in exactly the same way (all constants come from config, nothing is
fitted on the data at hand)."""

from __future__ import annotations

import pandas as pd

from pdm.validation.schema import SENSORS


def clean_telemetry(telemetry: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cc = cfg["cleaning"]
    df = (
        telemetry.drop_duplicates(subset=["machineID", "datetime"], keep="last")
        .sort_values(["machineID", "datetime"])
        .reset_index(drop=True)
    )
    df[SENSORS] = df[SENSORS].apply(pd.to_numeric, errors="coerce").astype(float)
    lo = pd.Series({s: cc["clip"][s][0] for s in SENSORS})
    hi = pd.Series({s: cc["clip"][s][1] for s in SENSORS})

    # 1) short gaps: carry the last reading forward (sensor dropped a few samples)
    sensors = df.groupby("machineID")[SENSORS].ffill(limit=cc["ffill_limit_hours"])
    # 2) still missing: fixed fallback = middle of the normal range (NOT a data-dependent median,
    #    which would differ between a 24-row request and the full training set)
    sensors = sensors.fillna((lo + hi) / 2)
    # 3) outliers: clip to the normal operating range
    df[SENSORS] = sensors.clip(lower=lo, upper=hi, axis=1)
    return df
