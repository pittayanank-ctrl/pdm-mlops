"""Owner: Feature + Model."""

import numpy as np

from pdm.data.labels import LABEL
from pdm.features.build import feature_columns
from pdm.modeling.metrics import choose_threshold, classification_metrics
from pdm.modeling.models import make_model


def test_feature_table_is_complete(training_table, cfg):
    numeric, categorical = feature_columns(cfg)
    assert list(training_table.columns[2:-1]) == numeric + categorical
    assert not training_table[numeric].isna().any().any()
    assert training_table[LABEL].isin([0, 1]).all()


def test_every_model_kind_trains_and_predicts(training_table, cfg):
    numeric, categorical = feature_columns(cfg)
    X, y = training_table[numeric + categorical], training_table[LABEL]
    for kind, params in [
        ("rule", {"feature": "vibration_mean_24h"}),
        ("logreg", {}),
        ("random_forest", {"n_estimators": 10}),
        ("xgboost", {"n_estimators": 10}),
    ]:
        model = make_model(kind, params, numeric, categorical, seed=1, pos_weight=10.0).fit(X, y)
        p = model.predict_proba(X.head(5))[:, 1]
        assert ((p >= 0) & (p <= 1)).all(), kind


def test_threshold_minimises_business_cost():
    y = np.array([0] * 90 + [1] * 10)
    proba = np.r_[np.linspace(0, 0.4, 90), np.linspace(0.3, 0.9, 10)]
    t = choose_threshold(y, proba, cost_fn=50000, cost_fp=5000)
    m = classification_metrics(y, proba, t, 50000, 5000)
    assert m["recall"] >= 0.9  # missing a failure is 10x more expensive than a false alarm
    assert m["cost_thb"] <= classification_metrics(y, proba, 0.5, 50000, 5000)["cost_thb"]
