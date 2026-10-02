"""Request/response contracts. Sensor bounds come from the same HARD_BOUNDS as the
training data schema, so the API rejects exactly what the pipeline would reject."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from pdm.validation.schema import AGE_RANGE, ERROR_IDS, HARD_BOUNDS, MACHINE_ID_RANGE

MIN_HISTORY, MAX_HISTORY = 24, 168
Model = Literal["model1", "model2", "model3", "model4"]
Component = Literal["comp1", "comp2", "comp3", "comp4"]


class TelemetryPoint(BaseModel):
    datetime: datetime
    # None = sensor dropout; filled the same way as in training (pdm.validation.cleaning)
    volt: float | None = Field(None, ge=HARD_BOUNDS["volt"][0], le=HARD_BOUNDS["volt"][1])
    rotate: float | None = Field(None, ge=HARD_BOUNDS["rotate"][0], le=HARD_BOUNDS["rotate"][1])
    pressure: float | None = Field(None, ge=HARD_BOUNDS["pressure"][0], le=HARD_BOUNDS["pressure"][1])
    vibration: float | None = Field(None, ge=HARD_BOUNDS["vibration"][0], le=HARD_BOUNDS["vibration"][1])


class ErrorEvent(BaseModel):
    datetime: datetime
    errorID: Literal[tuple(ERROR_IDS)]  # type: ignore[valid-type]


class PredictRequest(BaseModel):
    machine_id: int = Field(..., ge=MACHINE_ID_RANGE[0], le=MACHINE_ID_RANGE[1])
    model: Model
    age: int = Field(..., ge=AGE_RANGE[0], le=AGE_RANGE[1])
    telemetry: list[TelemetryPoint] = Field(
        ...,
        min_length=MIN_HISTORY,
        max_length=MAX_HISTORY,
        description="hourly readings, oldest first, last 24 h at least",
    )
    errors: list[ErrorEvent] = Field(default_factory=list)
    last_maint: dict[Component, datetime] = Field(
        default_factory=dict, description="last replacement/service time per component"
    )

    @field_validator("telemetry")
    @classmethod
    def hourly_and_ordered(cls, v: list[TelemetryPoint]) -> list[TelemetryPoint]:
        for a, b in zip(v, v[1:], strict=False):
            if b.datetime - a.datetime != timedelta(hours=1):
                raise ValueError(f"telemetry must be consecutive hourly readings (gap at {b.datetime.isoformat()})")
        nulls = sum(p.volt is None or p.rotate is None or p.pressure is None or p.vibration is None for p in v)
        if nulls > len(v) // 4:
            raise ValueError(f"too many missing sensor readings ({nulls} of {len(v)} rows)")
        return v

    @model_validator(mode="after")
    def maint_not_in_future(self) -> PredictRequest:
        last = self.telemetry[-1].datetime
        for comp, ts in self.last_maint.items():
            if ts > last:
                raise ValueError(f"last_maint[{comp}] is after the last telemetry reading")
        return self


class PredictResponse(BaseModel):
    request_id: str
    machine_id: int
    as_of: datetime
    failure_probability: float
    will_fail_24h: bool
    threshold: float
    model_version: str


class BatchRequest(BaseModel):
    items: list[PredictRequest] = Field(..., min_length=1, max_length=500)


class BatchResponse(BaseModel):
    predictions: list[PredictResponse]


class FeedbackRequest(BaseModel):
    request_id: str
    actual_failure: bool
