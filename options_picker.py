import numpy as np
from scipy.stats import norm
import pandas as pd
from config import (
    TARGET_DELTA_MIN, TARGET_DELTA_MAX, TARGET_DTE_MIN, TARGET_DTE_MAX,
    MAX_SPREAD_PCT,
)
from datetime import datetime


def bs_delta(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "call") -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if option_type == "call":
        return float(norm.cdf(d1))
    return float(norm.cdf(d1) - 1)


def pick_contract(chain: pd.DataFrame, spot_price: float, direction: str,
                  max_debit: float, risk_free_rate: float = 0.05) -> dict | None:
    if chain.empty:
        return None

    option_type = "call" if direction == "CALL" else "put"
    filtered = chain[chain["option_type"] == option_type].copy()
    if filtered.empty:
        return None

    filtered["mid"] = (filtered["bid"] + filtered["ask"]) / 2
    filtered["spread_pct"] = (filtered["ask"] - filtered["bid"]) / (filtered["mid"] + 1e-12)
    filtered["cost"] = filtered["mid"] * 100
    filtered = filtered[filtered["cost"] <= max_debit]
    if filtered.empty:
        return None

    tight_spread = filtered[filtered["spread_pct"] <= MAX_SPREAD_PCT]
    if not tight_spread.empty:
        filtered = tight_spread

    today = datetime.now()
    deltas = []
    for _, row in filtered.iterrows():
        exp_date = datetime.strptime(row["expiration"], "%Y-%m-%d")
        T = max((exp_date - today).days / 365.0, 1 / 365.0)
        iv = row.get("impliedVolatility", 0.40)
        if iv <= 0:
            iv = 0.40
        d = bs_delta(spot_price, row["strike"], T, risk_free_rate, iv, option_type)
        deltas.append(abs(d))
    filtered["abs_delta"] = deltas

    in_range = filtered[
        (filtered["abs_delta"] >= TARGET_DELTA_MIN)
        & (filtered["abs_delta"] <= TARGET_DELTA_MAX)
    ]

    if in_range.empty:
        filtered["delta_dist"] = abs(filtered["abs_delta"] - 0.40)
        best = filtered.loc[filtered["delta_dist"].idxmin()]
    else:
        in_range = in_range.copy()
        in_range["delta_dist"] = abs(in_range["abs_delta"] - 0.40)
        best = in_range.loc[in_range["delta_dist"].idxmin()]

    exp_date = datetime.strptime(best["expiration"], "%Y-%m-%d")
    dte = (exp_date - today).days

    return {
        "strike": float(best["strike"]),
        "expiration": best["expiration"],
        "dte": dte,
        "option_type": option_type,
        "delta": round(float(best["abs_delta"]), 3),
        "mid_price": round(float(best["mid"]), 2),
        "cost": round(float(best["cost"]), 2),
        "bid": float(best["bid"]),
        "ask": float(best["ask"]),
        "iv": round(float(best.get("impliedVolatility", 0.40)), 3),
        "open_interest": int(best.get("openInterest", 0)),
    }
