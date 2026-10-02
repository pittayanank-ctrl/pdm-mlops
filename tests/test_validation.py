"""Owner: Data Validation (schema, bad data, cleaning)."""

import numpy as np
import pandas as pd
import pytest

from pdm.validation import bad_data
from pdm.validation.cleaning import clean_telemetry
from pdm.validation.validate import DataValidationError, validate_or_raise, validate_tables


def test_clean_data_passes(tables, cfg):
    assert validate_tables(tables, cfg).passed


@pytest.mark.parametrize("case", sorted(bad_data.CASES))
def test_every_bad_data_case_is_caught(tables, cfg, case):
    broken = {**tables, "telemetry": bad_data.CASES[case](tables["telemetry"].head(5000).copy())}
    if case == "wrong_type":  # simulate what read_csv produces for a text value in a numeric column
        broken["telemetry"]["volt"] = broken["telemetry"]["volt"].astype(object)
    report = validate_tables(broken, cfg)
    assert not report.passed, f"{case} was not detected"


def test_pipeline_stops_on_bad_data(tables, cfg, tmp_path):
    cfg = {**cfg, "validation": {**cfg["validation"], "report_dir": str(tmp_path)}}
    broken = {**tables, "telemetry": bad_data._negative_vibration(tables["telemetry"].copy())}
    with pytest.raises(DataValidationError):
        validate_or_raise(broken, cfg)
    assert list(tmp_path.glob("*FAIL.json")), "a failure report must be written"


def test_cleaning_fills_gaps_and_clips_outliers(cfg):
    t = pd.DataFrame(
        {
            "datetime": pd.date_range("2015-01-01", periods=6, freq="h"),
            "machineID": 1,
            "volt": [170, np.nan, np.nan, 999, 170, 170],
            "rotate": 450.0,
            "pressure": 100.0,
            "vibration": 40.0,
        }
    )
    out = clean_telemetry(t, cfg)
    assert out["volt"].isna().sum() == 0
    assert out.loc[1, "volt"] == 170  # forward-filled
    assert out.loc[3, "volt"] == cfg["cleaning"]["clip"]["volt"][1]  # clipped
