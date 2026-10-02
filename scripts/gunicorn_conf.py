"""Gunicorn settings for the API container (see scripts/start_api.sh)."""

import os

from prometheus_client import multiprocess

bind = "0.0.0.0:8000"
workers = int(os.environ.get("API_WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 60


def child_exit(server, worker):
    # drop a dead worker's gauges from the aggregated /metrics
    multiprocess.mark_process_dead(worker.pid)
