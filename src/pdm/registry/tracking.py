"""MLflow setup + the 6 things every run must record:
code version, data version, hyperparameters, metrics, artifacts, environment."""

from __future__ import annotations

import os
import platform
import subprocess
import sys

import mlflow

from pdm.config import ROOT


def tracking_uri() -> str:
    # docker compose sets MLFLOW_TRACKING_URI=http://mlflow:5000; locally fall back to a sqlite file
    return os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{(ROOT / 'mlflow.db').as_posix()}")


def setup(cfg: dict) -> str:
    uri = tracking_uri()
    mlflow.set_tracking_uri(uri)
    name = cfg["registry"]["experiment_name"]
    exp = mlflow.get_experiment_by_name(name)
    if exp is None:
        artifact_location = None if uri.startswith("http") else (ROOT / "mlruns").as_uri()
        exp_id = mlflow.create_experiment(name, artifact_location=artifact_location)
    else:
        exp_id = exp.experiment_id
    mlflow.set_experiment(experiment_id=exp_id)
    return exp_id


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def code_version() -> dict[str, str]:
    commit = os.environ.get("GIT_COMMIT") or _git("rev-parse", "HEAD") or "unknown"
    dirty = _git("status", "--porcelain")
    return {"git_commit": commit, "git_dirty": str(bool(dirty)) if dirty is not None else "unknown"}


def environment() -> dict[str, str]:
    return {"python_version": platform.python_version(), "platform": platform.platform()}


def pip_freeze() -> str:
    try:
        return subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return "pip freeze failed"


def log_run_context(cfg: dict, data_version: str) -> None:
    """Call inside an active run."""
    mlflow.set_tags(
        {
            **code_version(),
            **environment(),
            "data_version": data_version,
            "config_file": os.environ.get("PDM_CONFIG", "configs/params.yaml"),
        }
    )
    mlflow.log_dict(cfg, "config/params.json")
    mlflow.log_text(pip_freeze(), "environment/requirements-frozen.txt")
