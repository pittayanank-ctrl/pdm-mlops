"""Generate a small synthetic dataset with the same schema as Azure PdM.

Used by CI and for offline demos. Failures are preceded by a 36 h degradation
ramp in one sensor (depends on the failing component) and a burst of errors,
so a model can actually learn the signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COMPONENTS = ["comp1", "comp2", "comp3", "comp4"]
# which sensor drifts before each component fails, and by how much at failure time
DEGRADATION = {
    "comp1": ("volt", +35.0),
    "comp2": ("rotate", -120.0),
    "comp3": ("pressure", +30.0),
    "comp4": ("vibration", +18.0),
}
ERROR_FOR_COMP = {"comp1": "error1", "comp2": "error2", "comp3": "error3", "comp4": "error4"}
BASE = {"volt": (170.0, 12.0), "rotate": (446.0, 40.0), "pressure": (100.0, 8.0), "vibration": (40.0, 4.0)}
RAMP_HOURS = 36


def generate(machines: int = 12, start: str = "2015-01-01", days: int = 90, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    hours = pd.date_range(start, periods=days * 24, freq="h")
    n = len(hours)

    machine_df = pd.DataFrame(
        {
            "machineID": np.arange(1, machines + 1, dtype=np.int64),
            "model": rng.choice(["model1", "model2", "model3", "model4"], size=machines),
            "age": rng.integers(0, 21, size=machines),
        }
    )

    telemetry, errors, maint, failures = [], [], [], []
    for mid in machine_df["machineID"]:
        sensors = {s: rng.normal(mu, sd, n) for s, (mu, sd) in BASE.items()}
        error_rate = np.full(n, 0.002)
        error_type = rng.choice(["error1", "error2", "error3", "error4", "error5"], size=n)

        # failure schedule: first after 5-15 days, then every 12-25 days, always at 06:00
        t = int(rng.integers(5, 16)) * 24 + 6
        while t < n:
            comp = COMPONENTS[int(rng.integers(0, 4))]
            sensor, delta = DEGRADATION[comp]
            lo = max(0, t - RAMP_HOURS)
            ramp = np.linspace(0, 1, t - lo + 1)
            sensors[sensor][lo : t + 1] += delta * ramp
            sensors["vibration"][lo : t + 1] += 6.0 * ramp  # every failure shakes a bit
            err_lo = max(0, t - 48)
            error_rate[err_lo:t] = 0.06
            error_type[err_lo:t] = ERROR_FOR_COMP[comp]
            failures.append((hours[t], mid, comp))
            maint.append((hours[t], mid, comp))  # failed component is replaced
            t += int(rng.integers(12, 26)) * 24

        # routine maintenance every ~15 days on a random component
        for d in range(int(rng.integers(0, 15)), days, 15):
            maint.append((hours[d * 24 + 6], mid, COMPONENTS[int(rng.integers(0, 4))]))

        fired = rng.random(n) < error_rate
        errors.extend((hours[i], mid, error_type[i]) for i in np.flatnonzero(fired))
        telemetry.append(pd.DataFrame({"datetime": hours, "machineID": mid, **sensors}))

    tel = pd.concat(telemetry, ignore_index=True)
    tel[["volt", "rotate", "pressure", "vibration"]] = tel[["volt", "rotate", "pressure", "vibration"]].round(4)
    return {
        "telemetry": tel,
        "errors": pd.DataFrame(errors, columns=["datetime", "machineID", "errorID"]),
        "maint": pd.DataFrame(maint, columns=["datetime", "machineID", "comp"]).sort_values(["machineID", "datetime"]),
        "failures": pd.DataFrame(failures, columns=["datetime", "machineID", "failure"]),
        "machines": machine_df,
    }
