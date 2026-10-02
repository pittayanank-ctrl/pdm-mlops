# One command for everything:  make all
# (Windows without make: copy the commands from README.md)

COMPOSE = docker compose
JOB = $(COMPOSE) run --rm pipeline

.PHONY: all up down train validate bad-data drift-data drift-concept retrain-data retrain-concept \
        monitor-live rollback models batch loadtest test lint logs clean

all: up train            ## start services + run the full pipeline (raw data -> served model)

up:
	$(COMPOSE) up -d --build mlflow prefect api prometheus grafana

down:
	$(COMPOSE) down

train:                   ## ingest -> validate -> features -> train -> gate -> register -> reload API
	$(JOB) python -m pdm.pipelines.training_flow

validate:
	$(JOB) python -m pdm.validation.validate

bad-data:                ## demo: broken data is rejected (each command must FAIL)
	$(JOB) python -m pdm.validation.bad_data
	-$(JOB) python -m pdm.validation.validate --raw-dir data/bad/negative_vibration
	-$(JOB) python -m pdm.validation.validate --raw-dir data/bad/missing_column

drift-data:
	$(JOB) python -m pdm.monitoring.simulate_drift --scenario data --send-to-api 200

drift-concept:
	$(JOB) python -m pdm.monitoring.simulate_drift --scenario concept

retrain-data: drift-data
	$(JOB) python -m pdm.pipelines.retrain_flow --current data/drift/data_drift.parquet

retrain-concept: drift-concept
	$(JOB) python -m pdm.pipelines.retrain_flow --current data/drift/concept_drift.parquet

monitor-live:
	$(JOB) python -m pdm.monitoring.monitor --from-logs --last 500

models:
	$(JOB) python -m pdm.registry.register list

rollback:
	$(JOB) python -m pdm.registry.register rollback

batch:
	$(JOB) python -m pdm.serving.batch

loadtest:
	$(JOB) python -m pdm.serving.benchmark --url http://api:8000 --requests 2000 --concurrency 4

test:
	PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml pytest

lint:
	ruff check src tests && ruff format --check src tests

logs:
	$(COMPOSE) logs -f api

clean:                   ## remove containers AND volumes (registry, runs)
	$(COMPOSE) down -v
