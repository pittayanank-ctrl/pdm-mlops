"""When do we retrain?

1. Concept drift (live recall < monitoring.min_recall once ground truth arrives) -> retrain now.
2. Data drift (>= drift_share_threshold of features with PSI > psi_threshold)     -> retrain now
   (failures are rare, so labels arrive slowly; waiting for recall to drop means
   missed breakdowns).
3. Neither -> no action; the scheduled weekly run still retrains on fresh data.
A retrained model is only deployed if it passes the same gate as any candidate
(including beating the current champion on the newest data).
"""

from __future__ import annotations


def classify(data_drift: bool, concept_drift: bool) -> str:
    if data_drift and concept_drift:
        return "data_and_concept_drift"
    if concept_drift:
        return "concept_drift"
    if data_drift:
        return "data_drift"
    return "no_drift"


def decide(data_drift: bool, concept_drift: bool) -> dict:
    status = classify(data_drift, concept_drift)
    reasons = {
        "concept_drift": "live recall below threshold while inputs look normal: input->failure relationship changed",
        "data_drift": "input distribution shifted: model is extrapolating",
        "data_and_concept_drift": "inputs shifted AND live recall dropped",
        "no_drift": "nothing to do (weekly scheduled retrain still applies)",
    }
    return {"status": status, "retrain": status != "no_drift", "reason": reasons[status]}
