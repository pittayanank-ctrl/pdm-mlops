"""Create the target: will the machine fail within the next `horizon_hours`?"""

from __future__ import annotations

import numpy as np
import pandas as pd

LABEL = "will_fail_24h"


def add_labels(rows: pd.DataFrame, failures: pd.DataFrame, horizon_hours: int = 24) -> pd.DataFrame:
    """Add LABEL = 1 if a failure happens in (t, t + horizon] for that machine.

    `rows` needs columns machineID, datetime. Order of rows is preserved.
    """
    out = rows.copy()
    left = out[["machineID", "datetime"]].reset_index().sort_values("datetime")
    right = (
        failures[["machineID", "datetime"]]
        .rename(columns={"datetime": "next_failure"})
        .assign(datetime=lambda d: d["next_failure"])
        .sort_values("datetime")
    )
    merged = pd.merge_asof(
        left,
        right,
        on="datetime",
        by="machineID",
        direction="forward",
        allow_exact_matches=False,  # a failure exactly at t belongs to the past
    ).set_index("index")
    delta = (merged["next_failure"] - merged["datetime"]).dt.total_seconds() / 3600
    out[LABEL] = np.where(delta.reindex(out.index) <= horizon_hours, 1, 0).astype(int)
    return out
