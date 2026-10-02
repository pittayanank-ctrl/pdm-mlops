"""Model metrics and the business-cost-based decision threshold."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def expected_cost(y_true, y_pred, cost_fn: float, cost_fp: float) -> float:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return float(fn * cost_fn + fp * cost_fp)


def choose_threshold(
    y_true, proba, cost_fn: float, cost_fp: float, min_recall: float = 0.0, min_precision: float = 0.0
) -> float:
    """Lowest total cost (missed failure vs. needless inspection) among thresholds that also meet
    the gate's recall/precision on this data. If none meets them, fall back to lowest cost."""
    y_true = np.asarray(y_true)
    grid = np.round(np.arange(0.02, 0.99, 0.01), 2)
    costs, ok = [], []
    for t in grid:
        pred = (proba >= t).astype(int)
        costs.append(expected_cost(y_true, pred, cost_fn, cost_fp))
        ok.append(
            recall_score(y_true, pred, zero_division=0) >= min_recall
            and precision_score(y_true, pred, zero_division=0) >= min_precision
        )
    costs, ok = np.array(costs), np.array(ok)
    candidates = np.where(ok, costs, np.inf) if ok.any() else costs
    return float(grid[int(np.argmin(candidates))])


def classification_metrics(y_true, proba, threshold: float, cost_fn: float, cost_fp: float) -> dict[str, float]:
    y_true = np.asarray(y_true)
    pred = (np.asarray(proba) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    has_both = len(np.unique(y_true)) == 2
    cost = expected_cost(y_true, pred, cost_fn, cost_fp)
    no_model_cost = float(y_true.sum() * cost_fn)  # every failure is a surprise breakdown
    return {
        "pr_auc": float(average_precision_score(y_true, proba)) if has_both else float("nan"),
        "roc_auc": float(roc_auc_score(y_true, proba)) if has_both else float("nan"),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "cost_thb": cost,
        "saving_vs_no_model_thb": no_model_cost - cost,
    }
