"""Download (or generate) the raw tables and load them with parsed types.

python -m pdm.data.ingest            # download Azure PdM into data/raw
PDM_CONFIG=configs/params.ci.yaml python -m pdm.data.ingest   # synthetic sample
"""

from __future__ import annotations

import logging

import pandas as pd
import requests

from pdm.config import load_config, path
from pdm.data import sample_data

log = logging.getLogger(__name__)
TABLES = ["telemetry", "errors", "maint", "failures", "machines"]


def download(cfg: dict | None = None, force: bool = False) -> None:
    """Make sure every raw CSV exists in data.raw_dir (download or generate)."""
    cfg = cfg or load_config()
    dc = cfg["data"]
    raw_dir = path(dc["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    targets = {t: raw_dir / dc["files"][t] for t in TABLES}

    if not force and all(p.exists() for p in targets.values()):
        log.info("raw data already present in %s", raw_dir)
        return

    if dc["source"] == "sample":
        tables = sample_data.generate(**dc.get("sample", {}))
        for name, df in tables.items():
            df.to_csv(targets[name], index=False)
        log.info("generated synthetic sample data in %s", raw_dir)
        return

    for name, target in targets.items():
        for base in dc["base_urls"]:  # official source first, then mirrors of the same files
            url = f"{base}/{dc['files'][name]}"
            log.info("downloading %s", url)
            try:
                _fetch(url, target)
                break
            except requests.RequestException as e:
                log.warning("failed (%s), trying next source", e.__class__.__name__)
        else:
            raise RuntimeError(f"could not download {dc['files'][name]} from any source")


def _fetch(url: str, target) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = target.with_suffix(".part")  # never leave a half-written CSV behind
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.replace(target)


def load_raw(cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    """Read the raw CSVs. Types are coerced but NOT validated (see pdm.validation)."""
    cfg = cfg or load_config()
    dc = cfg["data"]
    raw_dir = path(dc["raw_dir"])
    tables = {}
    for name in TABLES:
        df = pd.read_csv(raw_dir / dc["files"][name])
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", format="mixed")
        tables[name] = df
    return tables


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    download()
    for name, df in load_raw().items():
        print(f"{name:10s} {len(df):>9,d} rows  columns={list(df.columns)}")


if __name__ == "__main__":
    main()
