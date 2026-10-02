"""Create deliberately broken copies of the raw data to demo that validation stops the pipeline.

    python -m pdm.validation.bad_data          # writes data/bad/<case>/ for every case
Then:  python -m pdm.validation.validate --raw-dir data/bad/negative_vibration   -> exit 1
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from pdm.config import load_config, path
from pdm.data.ingest import TABLES, load_raw

log = logging.getLogger(__name__)
MAX_ROWS = 20_000  # keep the demo copies small


def _missing_column(t):
    return t.drop(columns=["vibration"])


def _wrong_type(t):
    t = t.astype({"volt": object})
    t.loc[t.index[:10], "volt"] = "sensor_error"  # not "N/A": read_csv would turn that into NaN
    return t


def _negative_vibration(t):
    t.loc[t.index[:25], "vibration"] = -5.0
    return t


def _out_of_range_rotate(t):
    t.loc[t.index[100:110], "rotate"] = 5000.0
    return t


def _too_many_nulls(t):
    idx = t.sample(frac=0.10, random_state=0).index
    t.loc[idx, "pressure"] = np.nan
    return t


def _duplicate_rows(t):
    return pd.concat([t, t.head(50)], ignore_index=True)


def _unknown_machine(t):
    t.loc[t.index[:5], "machineID"] = 999  # a machine that was never registered
    return t


CASES = {
    "missing_column": _missing_column,
    "wrong_type": _wrong_type,
    "negative_vibration": _negative_vibration,
    "out_of_range_rotate": _out_of_range_rotate,
    "too_many_nulls": _too_many_nulls,
    "duplicate_rows": _duplicate_rows,
    "unknown_machine": _unknown_machine,
}


def make_bad_data(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    tables = load_raw(cfg)
    files = cfg["data"]["files"]
    out = []
    for case, corrupt in CASES.items():
        case_dir = path("data/bad") / case
        case_dir.mkdir(parents=True, exist_ok=True)
        for name in TABLES:
            df = tables[name].copy()
            if name == "telemetry":
                df = corrupt(df.head(MAX_ROWS).copy())
            df.to_csv(case_dir / files[name], index=False)
        out.append(str(case_dir))
        log.info("wrote %s", case_dir)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for d in make_bad_data():
        print(d)
