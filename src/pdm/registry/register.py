"""Model registry: versions + status, promotion through the gate, and rollback.

Status lives in a version tag `status`:
  candidate -> champion (passed gate) | rejected (failed gate)
  champion  -> archived (replaced)    | rolled_back (rollback away from it)
The alias `champion` always points at the version the API serves.

    python -m pdm.registry.register list
    python -m pdm.registry.register rollback            # back to the previous champion
    python -m pdm.registry.register rollback --to 3
"""

from __future__ import annotations

import argparse
import logging
import os

import mlflow
import requests

from pdm.config import load_config
from pdm.registry import tracking

log = logging.getLogger(__name__)
ALIAS = "champion"


def current_champion(client: mlflow.MlflowClient, name: str) -> str | None:
    try:
        return str(client.get_model_version_by_alias(name, ALIAS).version)
    except mlflow.exceptions.MlflowException:
        return None


def _set_status(client, name, version, status, reason=""):
    client.set_model_version_tag(name, version, "status", status)
    if reason:
        client.set_model_version_tag(name, version, "status_reason", reason)


def promote(client: mlflow.MlflowClient, name: str, version: str, reason: str = "passed gate") -> None:
    previous = current_champion(client, name)
    client.set_registered_model_alias(name, ALIAS, version)
    _set_status(client, name, version, "champion", reason)
    if previous and previous != version:
        _set_status(client, name, previous, "archived", f"replaced by v{version}")
        client.set_model_version_tag(name, version, "previous_champion", previous)
    log.info("promoted v%s to %s (previous: %s)", version, ALIAS, previous)


def register_candidate(run_id: str, report: dict, cfg: dict) -> str:
    """Register every evaluated candidate so rejected ones stay visible in the registry."""
    tracking.setup(cfg)
    client = mlflow.MlflowClient()
    name = cfg["registry"]["model_name"]
    mv = mlflow.register_model(f"runs:/{run_id}/model", name)
    version = str(mv.version)
    client.set_model_version_tag(name, version, "threshold", str(report["threshold"]))
    client.set_model_version_tag(name, version, "test_pr_auc", f"{report['test_metrics']['pr_auc']:.4f}")
    if report["passed"]:
        promote(client, name, version)
    else:
        failed = ", ".join(c["name"] for c in report["checks"] if not c["passed"])
        _set_status(client, name, version, "rejected", f"failed: {failed}")
        log.warning("v%s rejected (%s); champion unchanged", version, failed)
    return version


def rollback(cfg: dict, to_version: str | None = None) -> str:
    tracking.setup(cfg)
    client = mlflow.MlflowClient()
    name = cfg["registry"]["model_name"]
    current = current_champion(client, name)
    if current is None:
        raise SystemExit("no champion to roll back from")

    if to_version is None:
        to_version = client.get_model_version(name, current).tags.get("previous_champion")
    if to_version is None:  # fall back to the newest older version that once passed the gate
        older = [
            v
            for v in client.search_model_versions(f"name='{name}'")
            if int(v.version) < int(current) and v.tags.get("status") in ("archived", "rolled_back", "champion")
        ]
        if not older:
            raise SystemExit("no earlier approved version to roll back to")
        to_version = str(max(older, key=lambda v: int(v.version)).version)

    client.set_registered_model_alias(name, ALIAS, to_version)
    _set_status(client, name, current, "rolled_back", f"rolled back to v{to_version}")
    _set_status(client, name, to_version, "champion", f"restored by rollback from v{current}")
    log.warning("ROLLBACK: champion v%s -> v%s", current, to_version)
    notify_api_reload()
    return to_version


def notify_api_reload() -> None:
    """Tell a running API to load the new champion (no-op if API_URL is not set)."""
    url = os.environ.get("API_URL")
    if not url:
        return
    try:
        r = requests.post(f"{url.rstrip('/')}/admin/reload", timeout=30)
        log.info("API reload: %s %s", r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.warning("API reload failed: %s", e)


def list_versions(cfg: dict) -> None:
    tracking.setup(cfg)
    client = mlflow.MlflowClient()
    name = cfg["registry"]["model_name"]
    champ = current_champion(client, name)
    print(f"{'ver':>4}  {'status':<12} {'test_pr_auc':>11}  run_id")
    for v in sorted(client.search_model_versions(f"name='{name}'"), key=lambda v: int(v.version)):
        mark = " <- champion" if v.version == champ else ""
        print(f"{v.version:>4}  {v.tags.get('status', '?'):<12} {v.tags.get('test_pr_auc', '-'):>11}  {v.run_id}{mark}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    rb = sub.add_parser("rollback")
    rb.add_argument("--to", dest="to_version")
    args = parser.parse_args()
    cfg = load_config()
    if args.cmd == "list":
        list_versions(cfg)
    else:
        print(f"champion is now v{rollback(cfg, args.to_version)}")


if __name__ == "__main__":
    main()
