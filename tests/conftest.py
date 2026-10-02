import os

import pandas as pd
import pytest

os.environ.setdefault("PDM_CONFIG", "configs/params.ci.yaml")
os.environ.setdefault("MODEL_POLL_SECONDS", "0")

from pdm.config import load_config  # noqa: E402
from pdm.data import sample_data  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    c = load_config()
    c["split"] = {
        "train": ["2015-01-01", "2015-02-01"],
        "val": ["2015-02-01", "2015-02-15"],
        "test": ["2015-02-15", "2015-03-02"],
    }
    return c


@pytest.fixture(scope="session")
def tables():
    """Small in-memory synthetic dataset (8 machines x 60 days), same schema as Azure PdM."""
    t = sample_data.generate(machines=8, start="2015-01-01", days=60, seed=3)
    for name in ("telemetry", "errors", "maint", "failures"):
        t[name]["datetime"] = pd.to_datetime(t[name]["datetime"])
    return t


@pytest.fixture(scope="session")
def training_table(tables, cfg):
    from pdm.features.build import build_training_table

    return build_training_table(tables, cfg)
