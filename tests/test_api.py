"""Owner: Serving + Infra. The API is tested with a small real model, no MLflow needed."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pdm.data.labels import LABEL
from pdm.features.build import feature_columns
from pdm.modeling.models import make_model
from pdm.serving import app as app_module
from pdm.serving.model_loader import ModelBundle
from pdm.serving.payloads import make_payload

T0 = pd.Timestamp("2015-02-20 06:00")


@pytest.fixture(scope="module")
def client(training_table, cfg, tmp_path_factory):
    numeric, categorical = feature_columns(cfg)
    model = make_model("xgboost", {"n_estimators": 20}, numeric, categorical, 1, 10.0)
    model.fit(training_table[numeric + categorical], training_table[LABEL])
    bundle = ModelBundle(model=model, threshold=0.3, version="7", run_id="test-run")

    app_module.LOG_DIR = tmp_path_factory.mktemp("logs")
    app_module.load_champion = lambda _cfg: bundle  # instead of the MLflow registry
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def payload(tables):
    return make_payload(tables, 3, T0)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["model_loaded"] and body["model_version"] == "7"


def test_predict(client, payload):
    r = client.post("/predict", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert 0 <= body["failure_probability"] <= 1
    assert body["will_fail_24h"] == (body["failure_probability"] >= 0.3)
    assert body["as_of"].startswith("2015-02-20T06:00")


def test_missing_sensor_values_are_handled(client, payload):
    payload["telemetry"][5]["volt"] = None
    payload["telemetry"][6]["pressure"] = None
    assert client.post("/predict", json=payload).status_code == 200


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["telemetry"][3].update(vibration=-1),  # impossible value
        lambda p: p["telemetry"][3].update(rotate="fast"),  # wrong type
        lambda p: p.update(telemetry=p["telemetry"][:10]),  # not enough history
        lambda p: p["telemetry"].pop(10),  # gap in hourly series
        lambda p: p.update(model="model9"),  # unknown machine model
        lambda p: p.update(machine_id=0),  # invalid id
        lambda p: p.pop("telemetry"),  # missing field
        lambda p: [r.update(volt=None) for r in p["telemetry"][:12]],  # mostly missing
    ],
)
def test_bad_requests_are_rejected_not_crashing(client, payload, mutate):
    mutate(payload)
    assert client.post("/predict", json=payload).status_code == 422


def test_batch(client, tables):
    items = [make_payload(tables, m, T0) for m in (1, 2, 3)]
    r = client.post("/predict/batch", json={"items": items})
    assert r.status_code == 200
    assert {p["machine_id"] for p in r.json()["predictions"]} == {1, 2, 3}


def test_batch_rejects_duplicate_machines(client, tables):
    items = [make_payload(tables, 1, T0)] * 2
    assert client.post("/predict/batch", json={"items": items}).status_code == 422


def test_feedback_and_logs(client, payload):
    rid = client.post("/predict", json=payload).json()["request_id"]
    assert client.post("/feedback", json={"request_id": rid, "actual_failure": True}).json()["recorded"]
    assert any(rid in f.read_text() for f in app_module.LOG_DIR.glob("predictions-*.jsonl"))


def test_metrics_exposed(client, payload):
    client.post("/predict", json=payload)
    text = client.get("/metrics").text
    assert "pdm_requests_total" in text and "pdm_request_latency_seconds" in text and "pdm_model_version" in text
