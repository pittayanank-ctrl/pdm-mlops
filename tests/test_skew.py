"""Owner: Feature + Model (added after the API PR).
Proof that training and serving build identical features (no training-serving skew)."""

import numpy as np
import pandas as pd

from pdm.features.build import build_features, feature_columns
from pdm.serving.payloads import make_payload, request_to_frames
from pdm.serving.schemas import PredictRequest


def test_no_training_serving_skew(training_table, tables, cfg):
    """Features computed by the API from a JSON request == features used in training."""
    numeric, _ = feature_columns(cfg)
    sample = training_table.sample(25, random_state=0)
    for row in sample.itertuples():
        req = PredictRequest(**make_payload(tables, row.machineID, row.datetime))
        f = request_to_frames(req)
        served = build_features(f["telemetry"], f["errors"], f["maint"], f["machines"], cfg).iloc[-1]
        trained = training_table.loc[row.Index]
        np.testing.assert_allclose(
            served[numeric].astype(float),
            trained[numeric].astype(float),
            rtol=1e-9,
            err_msg=f"skew at machine {row.machineID} {row.datetime}",
        )
        assert served["model"] == trained["model"]


def test_features_do_not_need_maintenance_history(tables, cfg):
    t0 = pd.Timestamp("2015-02-10 06:00")
    req = PredictRequest(**{**make_payload(tables, 1, t0), "last_maint": {}, "errors": []})
    f = request_to_frames(req)
    row = build_features(f["telemetry"], f["errors"], f["maint"], f["machines"], cfg).iloc[-1]
    assert row["days_since_comp1"] == cfg["features"]["max_days_since_maint"]
