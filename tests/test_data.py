"""Owner: Data Engineer (labels, split, versioning)."""

import pandas as pd
import pytest

from pdm.data.labels import LABEL, add_labels
from pdm.data.split import split_by_time
from pdm.data.versioning import data_version


def test_label_is_one_only_within_horizon():
    rows = pd.DataFrame(
        {
            "machineID": [1] * 5,
            "datetime": pd.to_datetime(
                ["2015-01-01 00:00", "2015-01-01 06:00", "2015-01-01 07:00", "2015-01-02 06:00", "2015-01-02 07:00"]
            ),
        }
    )
    failures = pd.DataFrame({"machineID": [1], "datetime": pd.to_datetime(["2015-01-02 06:00"])})
    out = add_labels(rows, failures, horizon_hours=24)
    # 00:00 is 30h before -> 0; 06:00 is exactly 24h before -> 1; at/after failure -> 0
    assert out[LABEL].tolist() == [0, 1, 1, 0, 0]


def test_labels_do_not_leak_across_machines():
    rows = pd.DataFrame({"machineID": [1, 2], "datetime": pd.to_datetime(["2015-01-01 06:00"] * 2)})
    failures = pd.DataFrame({"machineID": [2], "datetime": pd.to_datetime(["2015-01-01 12:00"])})
    assert add_labels(rows, failures)[LABEL].tolist() == [0, 1]


def test_split_is_time_ordered_and_reproducible(tables, cfg):
    a = split_by_time(tables["telemetry"], cfg["split"])
    b = split_by_time(tables["telemetry"], cfg["split"])
    assert a["train"]["datetime"].max() < a["val"]["datetime"].min()
    assert a["val"]["datetime"].max() < a["test"]["datetime"].min()
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])


def test_split_rejects_empty_range(tables):
    bad = {
        "train": ["2015-01-01", "2015-02-01"],
        "val": ["2030-01-01", "2030-02-01"],
        "test": ["2015-02-15", "2015-03-01"],
    }
    with pytest.raises(ValueError):
        split_by_time(tables["telemetry"], bad)


def test_data_version_changes_only_with_content(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x\n1\n")
    v1 = data_version([f])
    assert v1 == data_version([f])
    f.write_text("x\n2\n")
    assert data_version([f]) != v1
