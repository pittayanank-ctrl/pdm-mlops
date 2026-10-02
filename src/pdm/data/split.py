"""Time-based train/val/test split (no shuffling -> no leakage from the future)."""

from __future__ import annotations

import pandas as pd


def split_by_time(df: pd.DataFrame, split_cfg: dict, time_col: str = "datetime") -> dict[str, pd.DataFrame]:
    """Return {"train", "val", "test"}; each range is [start, end)."""
    parts = {}
    for name in ("train", "val", "test"):
        start, end = (pd.Timestamp(x) for x in split_cfg[name])
        mask = (df[time_col] >= start) & (df[time_col] < end)
        parts[name] = df.loc[mask].reset_index(drop=True)
        if parts[name].empty:
            raise ValueError(f"split '{name}' {start}..{end} is empty")
    check_no_overlap(parts, time_col)
    return parts


def check_no_overlap(parts: dict[str, pd.DataFrame], time_col: str = "datetime") -> None:
    order = ["train", "val", "test"]
    for a, b in zip(order, order[1:], strict=False):
        if parts[a][time_col].max() >= parts[b][time_col].min():
            raise ValueError(f"time overlap between {a} and {b}")
