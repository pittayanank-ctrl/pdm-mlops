"""Load configs/params.yaml, optionally overridden by the file named in $PDM_CONFIG."""

from __future__ import annotations

import json
import copy
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE_CONFIG = ROOT / "configs" / "params.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@cache
def _load(override_path: str | None) -> dict[str, Any]:
    with open(BASE_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if override_path:
        path = Path(override_path)
        if not path.is_absolute():
            path = ROOT / path
        with open(path, encoding="utf-8") as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})
    return cfg


def load_config() -> dict[str, Any]:
    """Return a fresh copy so callers can't mutate the cached config."""
    return copy.deepcopy(_load(os.environ.get("PDM_CONFIG")))


def path(relative: str) -> Path:
    """Resolve a config path relative to the project root."""
    p = Path(relative)
    return p if p.is_absolute() else ROOT / p
