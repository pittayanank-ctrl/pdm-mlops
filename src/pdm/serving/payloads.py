"""Convert between raw tables and API payloads (used by the API, batch scoring, benchmark and tests)."""

from __future__ import annotations

import pandas as pd

from pdm.features.build import maint_with_failures
from pdm.serving.schemas import PredictRequest
from pdm.validation.schema import SENSORS


def request_to_frames(req: PredictRequest) -> dict[str, pd.DataFrame]:
    mid = req.machine_id
    tel = pd.DataFrame(
        [{"datetime": p.datetime, "machineID": mid, **{s: getattr(p, s) for s in SENSORS}} for p in req.telemetry]
    )
    tel["datetime"] = pd.to_datetime(tel["datetime"]).dt.tz_localize(None)
    errors = pd.DataFrame(
        [{"datetime": e.datetime, "machineID": mid, "errorID": e.errorID} for e in req.errors],
        columns=["datetime", "machineID", "errorID"],
    )
    errors["datetime"] = pd.to_datetime(errors["datetime"]).dt.tz_localize(None)
    maint = pd.DataFrame(
        [{"datetime": ts, "machineID": mid, "comp": c} for c, ts in req.last_maint.items()],
        columns=["datetime", "machineID", "comp"],
    )
    maint["datetime"] = pd.to_datetime(maint["datetime"]).dt.tz_localize(None)
    machines = pd.DataFrame([{"machineID": mid, "model": req.model, "age": req.age}])
    return {"telemetry": tel, "errors": errors, "maint": maint, "machines": machines}


def make_payload(tables: dict[str, pd.DataFrame], machine_id: int, as_of: pd.Timestamp, hours: int = 24) -> dict:
    """Build the JSON body the API expects from raw tables (what a plant gateway would send)."""
    as_of = pd.Timestamp(as_of)
    start = as_of - pd.Timedelta(hours=hours - 1)
    tel = tables["telemetry"]
    tel = tel[(tel["machineID"] == machine_id) & (tel["datetime"] >= start) & (tel["datetime"] <= as_of)]
    err = tables["errors"]
    err = err[(err["machineID"] == machine_id) & (err["datetime"] >= start) & (err["datetime"] <= as_of)]
    maint = maint_with_failures(tables["maint"], tables["failures"])
    maint = maint[(maint["machineID"] == machine_id) & (maint["datetime"] <= as_of)]
    last_maint = maint.groupby("comp")["datetime"].max()
    machine = tables["machines"].set_index("machineID").loc[machine_id]

    def _val(x):
        return None if pd.isna(x) else float(x)

    return {
        "machine_id": int(machine_id),
        "model": str(machine["model"]),
        "age": int(machine["age"]),
        "telemetry": [
            {"datetime": r.datetime.isoformat(), **{s: _val(getattr(r, s)) for s in SENSORS}}
            for r in tel.sort_values("datetime").itertuples()
        ],
        "errors": [{"datetime": r.datetime.isoformat(), "errorID": r.errorID} for r in err.itertuples()],
        "last_maint": {c: ts.isoformat() for c, ts in last_maint.items()},
    }
