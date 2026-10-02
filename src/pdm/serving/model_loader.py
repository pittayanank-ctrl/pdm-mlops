"""Load the model the registry alias `champion` points to."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import mlflow

from pdm.registry import tracking


@dataclass
class ModelBundle:
    model: object
    threshold: float
    version: str
    run_id: str
    loaded_at: float = field(default_factory=time.time)


def champion_version(cfg: dict) -> str | None:
    mlflow.set_tracking_uri(tracking.tracking_uri())
    try:
        return str(mlflow.MlflowClient().get_model_version_by_alias(cfg["registry"]["model_name"], "champion").version)
    except mlflow.exceptions.MlflowException:
        return None


def load_champion(cfg: dict) -> ModelBundle:
    mlflow.set_tracking_uri(tracking.tracking_uri())
    client = mlflow.MlflowClient()
    name = cfg["registry"]["model_name"]
    mv = client.get_model_version_by_alias(name, "champion")
    model = mlflow.sklearn.load_model(f"models:/{name}/{mv.version}")
    # one request = a handful of rows: extra predictor threads only fight each other under load
    clf = model.named_steps.get("clf")
    if clf is not None and "n_jobs" in clf.get_params():
        clf.set_params(n_jobs=1)
    threshold = float(client.get_run(mv.run_id).data.params["threshold"])
    return ModelBundle(model=model, threshold=threshold, version=str(mv.version), run_id=mv.run_id)
