"""Validate raw tables against the schema. On failure: write a report, alert, and stop.

    python -m pdm.validation.validate                       # uses data.raw_dir
    python -m pdm.validation.validate --raw-dir data/bad/negative_vibration
Exit code 1 when validation fails (CI and the pipeline rely on this).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import pandas as pd
import pandera as pa
import requests

from pdm.config import load_config, path
from pdm.validation.schema import raw_schemas

log = logging.getLogger(__name__)


class DataValidationError(RuntimeError):
    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(report.summary())


@dataclass
class ValidationReport:
    source: str
    passed: bool = True
    issues: list[dict] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def add(self, table: str, column: str | None, check: str, count: int, examples: list) -> None:
        self.passed = False
        self.issues.append(
            {"table": table, "column": column, "check": check, "count": int(count), "examples": examples[:5]}
        )

    def summary(self) -> str:
        if self.passed:
            return f"[{self.source}] data validation passed"
        lines = [f"[{self.source}] data validation FAILED ({len(self.issues)} issue(s)):"]
        lines += [f"  - {i['table']}.{i['column']}: {i['check']} (n={i['count']})" for i in self.issues]
        return "\n".join(lines)


def _schema_issues(report: ValidationReport, table: str, exc: pa.errors.SchemaErrors) -> None:
    fc = exc.failure_cases
    for (column, check), grp in fc.groupby(["column", "check"], dropna=False):
        report.add(
            table,
            None if pd.isna(column) else str(column),
            str(check),
            len(grp),
            [str(x) for x in grp["failure_case"].head(5)],
        )


def validate_tables(tables: dict[str, pd.DataFrame], cfg: dict | None = None, source: str = "raw") -> ValidationReport:
    cfg = cfg or load_config()
    report = ValidationReport(source=source)
    schemas = raw_schemas(cfg["validation"]["max_null_fraction"])

    for name, schema in schemas.items():
        if name not in tables:
            report.add(name, None, "table missing", 1, [])
            continue
        missing = [c for c in schema.columns if c not in tables[name].columns]
        if missing:
            report.add(name, ",".join(missing), "column missing", len(missing), missing)
            continue
        try:
            schema.validate(tables[name], lazy=True)
        except pa.errors.SchemaErrors as exc:
            _schema_issues(report, name, exc)

    # cross-table check: every machine in telemetry must exist in machines
    if "telemetry" in tables and "machines" in tables and "machineID" in tables["telemetry"]:
        unknown = set(tables["telemetry"]["machineID"].dropna().unique()) - set(tables["machines"]["machineID"])
        if unknown:
            report.add(
                "telemetry",
                "machineID",
                "unknown machine (not in machines table)",
                len(unknown),
                sorted(map(str, unknown)),
            )
    return report


def alert(report: ValidationReport, cfg: dict) -> None:
    """Log loudly and, if a webhook URL is configured, push the message there."""
    msg = report.summary()
    log.error(msg)
    url = os.environ.get(cfg["validation"]["alert_webhook_env"])
    if url:
        try:
            requests.post(url, json={"content": msg[:1900], "text": msg[:1900]}, timeout=5)
        except requests.RequestException as e:  # alerting must never crash the pipeline
            log.warning("webhook alert failed: %s", e)


def save_report(report: ValidationReport, cfg: dict) -> str:
    out_dir = path(cfg["validation"]["report_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"{stamp}_{report.source.replace('/', '_')}_{'pass' if report.passed else 'FAIL'}.json"
    out.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out)


def validate_or_raise(
    tables: dict[str, pd.DataFrame], cfg: dict | None = None, source: str = "raw"
) -> ValidationReport:
    """Pipeline entry point: stop the run (raise) if the data breaks the contract."""
    cfg = cfg or load_config()
    report = validate_tables(tables, cfg, source)
    report_path = save_report(report, cfg)
    if not report.passed:
        alert(report, cfg)
        raise DataValidationError(report)
    log.info("%s -> %s", report.summary(), report_path)
    return report


def main() -> None:
    from pdm.data.ingest import load_raw

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", help="validate this folder instead of data.raw_dir")
    args = parser.parse_args()

    cfg = load_config()
    if args.raw_dir:
        cfg["data"]["raw_dir"] = args.raw_dir
    source = cfg["data"]["raw_dir"]
    try:
        validate_or_raise(load_raw(cfg), cfg, source)
    except DataValidationError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"[{source}] data validation passed")


if __name__ == "__main__":
    main()
