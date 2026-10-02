"""Model factory. Every model is a full sklearn Pipeline (preprocessing + estimator),
saved as ONE artifact, so serving applies exactly the same preprocessing."""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from pdm.validation.schema import MODELS


class ThresholdRule(BaseEstimator, ClassifierMixin):
    """Baseline that mimics what a technician would do without ML:
    "alarm when one sensor is high". Score = the feature min-max scaled to [0, 1]."""

    def fit(self, X, y, sample_weight=None):  # weights do not change a min-max rule
        x = np.asarray(X, dtype=float).ravel()
        self.lo_, self.hi_ = float(np.min(x)), float(np.max(x))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        x = np.asarray(X, dtype=float).ravel()
        p = np.clip((x - self.lo_) / max(self.hi_ - self.lo_, 1e-9), 0, 1)
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            ("cat", OneHotEncoder(categories=[MODELS], handle_unknown="ignore"), categorical),
        ]
    )


def make_model(
    kind: str, params: dict, numeric: list[str], categorical: list[str], seed: int, pos_weight: float
) -> Pipeline:
    if kind == "rule":
        feature = params["feature"]
        pre = ColumnTransformer([("rule", "passthrough", [feature])])
        return Pipeline([("pre", pre), ("clf", ThresholdRule())])
    if kind == "logreg":
        clf = LogisticRegression(C=params.get("C", 1.0), class_weight="balanced", max_iter=2000, random_state=seed)
    elif kind == "random_forest":
        clf = RandomForestClassifier(class_weight="balanced_subsample", n_jobs=-1, random_state=seed, **params)
    elif kind == "xgboost":
        clf = XGBClassifier(
            scale_pos_weight=pos_weight, eval_metric="aucpr", tree_method="hist", n_jobs=4, random_state=seed, **params
        )
    else:
        raise ValueError(f"unknown model kind: {kind}")
    return Pipeline([("pre", _preprocessor(numeric, categorical)), ("clf", clf)])
