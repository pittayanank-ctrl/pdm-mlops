"""Owner: Monitoring + Retraining."""

import json

import numpy as np
import pandas as pd

from pdm.data.labels import LABEL
from pdm.monitoring.drift import detect_data_drift, psi_categorical, psi_numeric
from pdm.monitoring.monitor import live_performance
from pdm.monitoring.retrain_policy import decide

MON = {"psi_threshold": 0.2, "drift_share_threshold": 0.3, "min_recall": 0.7}


def test_psi_small_for_same_distribution_and_large_for_shift():
    rng = np.random.default_rng(0)
    ref = pd.Series(rng.normal(40, 4, 5000))
    assert psi_numeric(ref, pd.Series(rng.normal(40, 4, 5000))) < 0.05
    assert psi_numeric(ref, pd.Series(rng.normal(48, 4, 5000))) > 0.2


def test_psi_categorical():
    ref = pd.Series(["model1"] * 50 + ["model2"] * 50)
    assert psi_categorical(ref, ref) == 0
    assert psi_categorical(ref, pd.Series(["model1"] * 95 + ["model2"] * 5)) > 0.2


def test_detect_data_drift_flags_shifted_features():
    rng = np.random.default_rng(1)
    ref = pd.DataFrame({"a": rng.normal(0, 1, 3000), "b": rng.normal(0, 1, 3000), "model": "model1"})
    cur = ref.assign(a=ref["a"] + 2)
    out = detect_data_drift(ref, cur, ["a", "b"], ["model"], MON)
    assert out["drifted_features"] == ["a"]
    assert out["data_drift"]  # 1 of 3 features = 33% >= 30%


def test_retrain_policy_distinguishes_drift_types():
    assert decide(False, False)["status"] == "no_drift" and not decide(False, False)["retrain"]
    assert decide(True, False)["status"] == "data_drift"
    assert decide(False, True)["status"] == "concept_drift"
    assert decide(True, True)["retrain"]


def test_live_performance_needs_labels():
    df = pd.DataFrame({"prediction": [1, 0, 0, 1], "probability": [0.9, 0.1, 0.2, 0.8]})
    assert live_performance(df) is None
    df[LABEL] = [1, 1, 0, 0]
    perf = live_performance(df)
    assert perf["recall"] == 0.5 and perf["precision"] == 0.5


def test_logged_prediction_is_not_mistaken_for_ground_truth(tmp_path):
    from pdm.monitoring.monitor import load_from_logs

    rec = {
        "logged_at": "2026-01-01T00:00:00",
        "request_id": "r1",
        "failure_probability": 0.9,
        "will_fail_24h": True,
        "features": {"a": 1.0},
    }
    (tmp_path / "predictions-1.jsonl").write_text(json.dumps(rec) + "\n{broken line\n")
    cur = load_from_logs(tmp_path)
    assert LABEL not in cur and live_performance(cur) is None  # no feedback yet -> no recall
    (tmp_path / "feedback-1.jsonl").write_text(json.dumps({"request_id": "r1", "actual_failure": False}) + "\n")
    assert load_from_logs(tmp_path)[LABEL].tolist() == [0]
