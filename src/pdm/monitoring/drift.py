"""Data drift = the INPUT distribution moved away from what the model was trained on.
Measured per feature with PSI (main rule) and the KS test (reported for context)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

EPS = 1e-4


def psi_numeric(ref: pd.Series, cur: pd.Series, bins: int = 10) -> float:
    """Population Stability Index with quantile bins taken from the reference."""
    ref, cur = ref.dropna().to_numpy(float), cur.dropna().to_numpy(float)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:  # constant reference column (e.g. a rare error count)
        return 0.0 if np.allclose(cur, edges[0]) else float(np.mean(cur != edges[0]) * np.log(1 / EPS))
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, EPS, None), np.clip(c, EPS, None)
    return float(np.sum((c - r) * np.log(c / r)))


def psi_categorical(ref: pd.Series, cur: pd.Series) -> float:
    cats = sorted(set(ref.dropna()) | set(cur.dropna()))
    r = ref.value_counts(normalize=True).reindex(cats, fill_value=0).clip(lower=EPS)
    c = cur.value_counts(normalize=True).reindex(cats, fill_value=0).clip(lower=EPS)
    return float(np.sum((c - r) * np.log(c / r)))


def detect_data_drift(
    ref: pd.DataFrame, cur: pd.DataFrame, numeric: list[str], categorical: list[str], mon_cfg: dict
) -> dict:
    rows = []
    for col in numeric + categorical:
        if col in categorical:
            psi, ks_p = psi_categorical(ref[col], cur[col]), None
        else:
            psi = psi_numeric(ref[col], cur[col])
            ks_p = float(ks_2samp(ref[col], cur[col]).pvalue)
        rows.append(
            {"feature": col, "psi": round(psi, 4), "ks_pvalue": ks_p, "drifted": psi > mon_cfg["psi_threshold"]}
        )
    table = pd.DataFrame(rows).sort_values("psi", ascending=False)
    share = float(table["drifted"].mean())
    return {
        "drift_share": round(share, 3),
        "data_drift": share >= mon_cfg["drift_share_threshold"],
        "drifted_features": table.loc[table["drifted"], "feature"].tolist(),
        "features": table.to_dict(orient="records"),
    }
