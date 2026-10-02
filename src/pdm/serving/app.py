"""Real-time prediction API.

    uvicorn pdm.serving.app:app --host 0.0.0.0 --port 8000

GET  /health        liveness + which model is loaded
GET  /ready         503 until a champion model is loaded
POST /predict       one machine, last >= 24 h of hourly telemetry
POST /predict/batch up to 500 machines in one call
POST /feedback      ground truth for an earlier prediction (for live recall / concept drift)
POST /admin/reload  reload the registry champion (called after promote / rollback)
GET  /metrics       Prometheus metrics
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

from pdm.config import ROOT, load_config
from pdm.features.build import build_features, feature_columns
from pdm.serving.model_loader import ModelBundle, champion_version, load_champion
from pdm.serving.payloads import request_to_frames
from pdm.serving.schemas import BatchRequest, BatchResponse, FeedbackRequest, PredictRequest, PredictResponse

log = logging.getLogger("pdm.api")
CFG = load_config()
NUMERIC, CATEGORICAL = feature_columns(CFG)
LOG_DIR = Path(os.environ.get("PDM_LOG_DIR", ROOT / "logs"))
# every worker checks the registry this often, so a promote/rollback reaches all of them
POLL_SECONDS = float(os.environ.get("MODEL_POLL_SECONDS", "30"))
MULTIPROC = bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))  # set when uvicorn runs several workers

REQUESTS = Counter("pdm_requests_total", "HTTP requests", ["endpoint", "status"])
LATENCY = Histogram(
    "pdm_request_latency_seconds",
    "Request latency",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1, 2.5),
)
PREDICTIONS = Counter("pdm_predictions_total", "Predictions by outcome", ["will_fail"])
FAIL_PROB = Histogram(
    "pdm_failure_probability",
    "Predicted failure probability",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
MODEL_VERSION = Gauge("pdm_model_version", "Registry version currently served", multiprocess_mode="max")
MODEL_LOADED = Gauge("pdm_model_loaded", "1 if a model is loaded", multiprocess_mode="min")

_state: dict = {"bundle": None, "started": time.time()}
_log_lock = threading.Lock()


def _set_bundle(bundle: ModelBundle | None) -> None:
    _state["bundle"] = bundle
    MODEL_LOADED.set(1 if bundle else 0)
    MODEL_VERSION.set(float(bundle.version) if bundle else 0)


def _try_load() -> str | None:
    try:
        _set_bundle(load_champion(CFG))
        log.info("loaded champion v%s", _state["bundle"].version)
        return None
    except Exception as e:  # registry down or no champion yet: keep serving /health
        log.warning("could not load champion: %s", e)
        return str(e)


def _poll_registry(stop: threading.Event) -> None:
    while not stop.wait(POLL_SECONDS):
        try:
            current = _state["bundle"].version if _state["bundle"] else None
            if champion_version(CFG) != current:
                _try_load()
        except Exception as e:
            log.warning("registry poll failed: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _try_load()
    stop = threading.Event()
    if POLL_SECONDS > 0:
        threading.Thread(target=_poll_registry, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Predictive Maintenance API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    endpoint = request.url.path
    t0 = time.perf_counter()
    response = await call_next(request)
    if endpoint != "/metrics":
        LATENCY.labels(endpoint).observe(time.perf_counter() - t0)
        REQUESTS.labels(endpoint, str(response.status_code)).inc()
    return response


def _append_jsonl(kind: str, record: dict) -> None:
    # one file per worker process: several processes appending to one file interleave lines
    with _log_lock, open(LOG_DIR / f"{kind}-{os.getpid()}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _bundle() -> ModelBundle:
    if _state["bundle"] is None:
        raise HTTPException(status_code=503, detail="no model loaded yet (run the training pipeline)")
    return _state["bundle"]


def _predict(items: list[PredictRequest]) -> list[PredictResponse]:
    bundle = _bundle()
    t0 = time.perf_counter()
    frames = [request_to_frames(r) for r in items]
    merged = {k: pd.concat([f[k] for f in frames], ignore_index=True) for k in frames[0]}
    feats = build_features(merged["telemetry"], merged["errors"], merged["maint"], merged["machines"], CFG)
    latest = feats.sort_values("datetime").groupby("machineID").tail(1).set_index("machineID")
    if latest.empty:
        raise HTTPException(status_code=422, detail="not enough history to build features")
    proba = bundle.model.predict_proba(latest[NUMERIC + CATEGORICAL])[:, 1]
    elapsed_ms = (time.perf_counter() - t0) * 1000

    out = []
    for (mid, row), p in zip(latest.iterrows(), proba, strict=False):
        will_fail = bool(p >= bundle.threshold)
        resp = PredictResponse(
            request_id=str(uuid.uuid4()),
            machine_id=int(mid),
            as_of=row["datetime"],
            failure_probability=round(float(p), 4),
            will_fail_24h=will_fail,
            threshold=bundle.threshold,
            model_version=bundle.version,
        )
        PREDICTIONS.labels(str(will_fail).lower()).inc()
        FAIL_PROB.observe(float(p))
        _append_jsonl(
            "predictions",
            {
                "logged_at": datetime.now(UTC).isoformat(),
                **resp.model_dump(mode="json"),
                "latency_ms": round(elapsed_ms / len(items), 3),
                "features": {c: (row[c] if c in CATEGORICAL else float(row[c])) for c in NUMERIC + CATEGORICAL},
            },
        )
        out.append(resp)
    return out


@app.get("/health")
def health():
    b = _state["bundle"]
    return {
        "status": "ok",
        "model_loaded": b is not None,
        "model_version": b.version if b else None,
        "uptime_s": round(time.time() - _state["started"], 1),
    }


@app.get("/ready")
def ready():
    _bundle()
    return {"ready": True}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    return _predict([req])[0]


@app.post("/predict/batch", response_model=BatchResponse)
def predict_batch(req: BatchRequest):
    ids = [r.machine_id for r in req.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="each machine_id may appear only once per batch")
    return BatchResponse(predictions=_predict(req.items))


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    _append_jsonl("feedback", {"logged_at": datetime.now(UTC).isoformat(), **req.model_dump()})
    return {"recorded": True}


@app.post("/admin/reload")
def reload_model():
    error = _try_load()
    if error:
        raise HTTPException(status_code=503, detail=f"reload failed: {error}")
    return {"reloaded": True, "model_version": _state["bundle"].version}


@app.get("/model")
def model_info():
    b = _bundle()
    return {
        "name": CFG["registry"]["model_name"],
        "version": b.version,
        "run_id": b.run_id,
        "threshold": b.threshold,
        "loaded_at": datetime.fromtimestamp(b.loaded_at, UTC).isoformat(),
    }


@app.get("/metrics")
def metrics():
    if MULTIPROC:  # aggregate the counters of all uvicorn workers
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return PlainTextResponse(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
