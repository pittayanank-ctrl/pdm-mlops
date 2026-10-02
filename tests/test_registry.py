"""Owner: Tracking + Registry (gate logic, promotion, rollback)."""

import mlflow
import pytest
from sklearn.dummy import DummyClassifier

from pdm.registry import register
from pdm.registry.evaluate import gate_checks

GATE = {
    "min_recall": 0.8,
    "min_precision": 0.5,
    "max_p95_latency_ms": 100,
    "max_model_size_mb": 50,
    "must_beat_champion": True,
}
GOOD = {"recall": 0.9, "precision": 0.6, "pr_auc": 0.8}


def test_gate_passes_good_model():
    assert all(c["passed"] for c in gate_checks(GOOD, 5.0, 1.0, champion_pr_auc=0.7, gate=GATE))


@pytest.mark.parametrize(
    "metrics,latency,size,champion,failed",
    [
        ({**GOOD, "recall": 0.5}, 5, 1, None, "recall"),
        ({**GOOD, "precision": 0.1}, 5, 1, None, "precision"),
        (GOOD, 250, 1, None, "p95_latency_ms"),
        (GOOD, 5, 80, None, "model_size_mb"),
        (GOOD, 5, 1, 0.95, "pr_auc_vs_champion"),
    ],
)
def test_gate_rejects(metrics, latency, size, champion, failed):
    checks = {c["name"]: c["passed"] for c in gate_checks(metrics, latency, size, champion, GATE)}
    assert checks[failed] is False


@pytest.fixture
def local_registry(tmp_path, monkeypatch, cfg):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.delenv("API_URL", raising=False)
    from pdm.registry import tracking

    monkeypatch.setattr(tracking, "ROOT", tmp_path)
    tracking.setup(cfg)
    return cfg


def _log_dummy_run():
    with mlflow.start_run() as run:
        mlflow.log_param("threshold", 0.5)
        mlflow.sklearn.log_model(DummyClassifier().fit([[0], [1]], [0, 1]), "model")
    return run.info.run_id


def _report(passed, pr_auc=0.8):
    return {
        "passed": passed,
        "threshold": 0.5,
        "test_metrics": {"pr_auc": pr_auc},
        "checks": [{"name": "recall", "passed": passed}],
    }


def test_promote_reject_and_rollback(local_registry):
    cfg = local_registry
    name = cfg["registry"]["model_name"]
    client = mlflow.MlflowClient()

    v1 = register.register_candidate(_log_dummy_run(), _report(True), cfg)
    v2 = register.register_candidate(_log_dummy_run(), _report(False), cfg)
    assert register.current_champion(client, name) == v1  # rejected model never serves
    assert client.get_model_version(name, v2).tags["status"] == "rejected"

    v3 = register.register_candidate(_log_dummy_run(), _report(True), cfg)
    assert register.current_champion(client, name) == v3
    assert client.get_model_version(name, v1).tags["status"] == "archived"

    assert register.rollback(cfg) == v1
    assert register.current_champion(client, name) == v1
    assert client.get_model_version(name, v3).tags["status"] == "rolled_back"
