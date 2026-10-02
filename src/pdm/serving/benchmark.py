"""Load test the running API and compare against the SLO.

    python -m pdm.serving.benchmark --url http://localhost:8000 --requests 1000 --concurrency 10
Writes reports/slo/latest.json (p50, p95, p99, throughput, error rate, SLO verdict).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
import requests

from pdm.config import load_config, path
from pdm.data.ingest import load_raw
from pdm.serving.payloads import make_payload


def build_payloads(cfg: dict, n: int, seed: int = 0) -> list[dict]:
    tables = load_raw(cfg)
    rng = random.Random(seed)
    start, end = (pd.Timestamp(x) for x in cfg["split"]["test"])
    hours = pd.date_range(start + pd.Timedelta(hours=24), min(end, tables["telemetry"]["datetime"].max()), freq="h")
    machines = tables["machines"]["machineID"].tolist()
    pool = [make_payload(tables, rng.choice(machines), rng.choice(hours)) for _ in range(min(n, 200))]
    return [pool[i % len(pool)] for i in range(n)]


def _client(args: tuple[str, list[dict]]) -> list[tuple[float, int]]:
    """One simulated caller = one OS process with its own connection (threads in one Python
    process share the GIL and inflate the measured latency - we saw p95 x4 that way)."""
    url, bodies = args
    out = []
    with requests.Session() as s:
        for body in bodies:
            t0 = time.perf_counter()
            try:
                status = s.post(f"{url}/predict", json=body, timeout=10).status_code
            except requests.RequestException:
                status = 599
            out.append(((time.perf_counter() - t0) * 1000, status))
    return out


def run(url: str, payloads: list[dict], concurrency: int) -> dict:
    chunks = [(url, payloads[i::concurrency]) for i in range(concurrency)]
    t0 = time.perf_counter()
    with Pool(concurrency) as pool:
        results = [r for chunk in pool.map(_client, chunks) for r in chunk]
    wall = time.perf_counter() - t0
    lat = np.array([r[0] for r in results])
    errors = sum(1 for r in results if r[1] >= 500)
    rejected = sum(1 for r in results if 400 <= r[1] < 500)
    return {
        "requests": len(results),
        "concurrency": concurrency,
        "wall_seconds": round(wall, 2),
        "throughput_rps": round(len(results) / wall, 1),
        "p50_ms": round(float(np.percentile(lat, 50)), 2),
        "p95_ms": round(float(np.percentile(lat, 95)), 2),
        "p99_ms": round(float(np.percentile(lat, 99)), 2),
        "error_rate": round(errors / len(results), 4),
        "client_errors_4xx": rejected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    # 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and adds ~2 s to new connections
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    cfg = load_config()
    slo = cfg["serving"]["slo"]

    payloads = build_payloads(cfg, args.requests)
    requests.post(f"{args.url}/predict", json=payloads[0], timeout=30)  # warm-up
    result = run(args.url, payloads, args.concurrency)
    result["slo"] = {
        "p95_latency_ms": {
            "target": slo["p95_latency_ms"],
            "actual": result["p95_ms"],
            "met": result["p95_ms"] < slo["p95_latency_ms"],
        },
        "error_rate": {
            "target": slo["error_rate"],
            "actual": result["error_rate"],
            "met": result["error_rate"] < slo["error_rate"],
        },
    }
    result["slo_met"] = all(v["met"] for v in result["slo"].values())

    out = path("reports/slo/latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
