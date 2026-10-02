"""Data contracts for every raw table and for the feature table.

HARD_BOUNDS is the single source of truth for valid sensor ranges; the API's
request models import it too, so training data and live requests obey the same rules.
"""

from __future__ import annotations

import pandera as pa
from pandera import Check, Column, DataFrameSchema

SENSORS = ["volt", "rotate", "pressure", "vibration"]
HARD_BOUNDS = {  # physically impossible outside these -> reject
    "volt": (50.0, 300.0),
    "rotate": (0.0, 1000.0),
    "pressure": (0.0, 300.0),
    "vibration": (0.0, 150.0),
}
MACHINE_ID_RANGE = (1, 100)
MODELS = ["model1", "model2", "model3", "model4"]
AGE_RANGE = (0, 30)
ERROR_IDS = ["error1", "error2", "error3", "error4", "error5"]
COMPONENTS = ["comp1", "comp2", "comp3", "comp4"]


def _machine_id() -> Column:
    return Column(int, Check.in_range(*MACHINE_ID_RANGE), nullable=False)


def telemetry_schema(max_null_fraction: float = 0.05) -> DataFrameSchema:
    sensors = {s: Column(float, Check.in_range(lo, hi), nullable=True) for s, (lo, hi) in HARD_BOUNDS.items()}
    # a few missing readings are cleaned later; too many means the feed is broken.
    # (dataframe-level: column checks never see nulls when nullable=True)
    null_check = Check(
        lambda df: df[[s for s in SENSORS if s in df]].isna().mean() <= max_null_fraction,
        error=f"sensor null fraction > {max_null_fraction:.0%}",
    )
    return DataFrameSchema(
        {"datetime": Column("datetime64[ns]", nullable=False), "machineID": _machine_id(), **sensors},
        checks=[null_check],
        unique=["machineID", "datetime"],
        strict=False,
        name="telemetry",
    )


def errors_schema() -> DataFrameSchema:
    return DataFrameSchema(
        {
            "datetime": Column("datetime64[ns]", nullable=False),
            "machineID": _machine_id(),
            "errorID": Column(str, Check.isin(ERROR_IDS), nullable=False),
        },
        name="errors",
    )


def maint_schema(name: str = "maint", column: str = "comp") -> DataFrameSchema:
    return DataFrameSchema(
        {
            "datetime": Column("datetime64[ns]", nullable=False),
            "machineID": _machine_id(),
            column: Column(str, Check.isin(COMPONENTS), nullable=False),
        },
        name=name,
    )


def machines_schema() -> DataFrameSchema:
    return DataFrameSchema(
        {
            "machineID": Column(int, Check.in_range(*MACHINE_ID_RANGE), nullable=False, unique=True),
            "model": Column(str, Check.isin(MODELS), nullable=False),
            "age": Column(int, Check.in_range(*AGE_RANGE), nullable=False),
        },
        name="machines",
    )


def raw_schemas(max_null_fraction: float = 0.05) -> dict[str, DataFrameSchema]:
    return {
        "telemetry": telemetry_schema(max_null_fraction),
        "errors": errors_schema(),
        "maint": maint_schema(),
        "failures": maint_schema("failures", "failure"),
        "machines": machines_schema(),
    }


def feature_schema(numeric_cols: list[str]) -> DataFrameSchema:
    """After feature engineering nothing may be NaN/inf (catches bugs in build_features)."""
    cols = {
        c: Column(
            float,
            Check(
                lambda s: s.notna().all() & ~s.isin([float("inf"), float("-inf")]).any(),
                element_wise=False,
                error="NaN/inf in feature",
            ),
            coerce=True,
        )
        for c in numeric_cols
    }
    cols["model"] = Column(str, Check.isin(MODELS))
    return DataFrameSchema(cols, strict=False, name="features")


__all__ = ["pa", "HARD_BOUNDS", "SENSORS", "raw_schemas", "feature_schema"]
