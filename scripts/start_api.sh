#!/bin/sh
# Start the API with several worker processes; Prometheus metrics are aggregated across workers.
# gunicorn (not `uvicorn --workers`): in our Linux container uvicorn's own multi-worker mode added
# ~44 ms to every request, gunicorn + UvicornWorker does not (measured: /health 44 ms -> 1 ms).
set -e
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
exec gunicorn pdm.serving.app:app -c scripts/gunicorn_conf.py
