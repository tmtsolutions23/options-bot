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


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "call") -> float:
    """Black-Scholes theoretical price for a European option."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
        return intrinsic
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def moneyness_label(spot: float, strike: float, option_type: str) -> str:
    """Return ITM, ATM, or OTM label."""
    pct_diff = abs(spot - strike) / spot
    if pct_diff <= 0.02:
        return "ATM"
    if option_type == "call":
        return "ITM" if strike < spot else "OTM"
    return "ITM" if strike > spot else "OTM"


def pick_contract(chain: pd.DataFrame, spot_price: float, direction: str,
                  max_debit: float, risk_free_rate: float = 0.05) -> dict | None:
    if chain.empty:
        return None

    option_type = "call" if direction == "CALL" else "put"
    filtered = chain[chain["option_type"] == option_type].copy()
    if filtered.empty:
        return None

    today = datetime.now()

    # Compute IV and time-to-expiry for each row (needed for BS fallback)
    ivs = []
    ttes = []
    for _, row in filtered.iterrows():
        iv = row.get("impliedVolatility", 0.40)
        if iv is None or iv <= 0:
            iv = 0.40
        ivs.append(iv)
        exp_date = datetime.strptime(row["expiration"], "%Y-%m-%d")
        T = max((exp_date - today).days / 365.0, 1 / 365.0)
        ttes.append(T)
    filtered["iv"] = ivs
    filtered["T"] = ttes

    # Mid price from market data; fall back to BS estimate when bid/ask are 0
    mids = []
    price_sources = []
    for _, row in filtered.iterrows():
        bid = row.get("bid", 0) or 0
        ask = row.get("ask", 0) or 0
        if bid > 0 and ask > 0:
            mids.append((bid + ask) / 2)
            price_sources.append("market")
        elif ask > 0:
            mids.append(ask * 0.85)  # conservative estimate from ask-only
            price_sources.append("est")
        else:
            # Full BS estimate — premarket or stale quotes
            theo = bs_price(spot_price, row["strike"], row["T"],
                            risk_free_rate, row["iv"], option_type)
            mids.append(max(theo, 0.01))
            price_sources.append("est")
    filtered["mid"] = mids
    filtered["price_source"] = price_sources

    filtered["spread_pct"] = (filtered["ask"] - filtered["bid"]) / (filtered["mid"] + 1e-12)
    filtered["cost"] = filtered["mid"] * 100
    filtered = filtered[filtered["cost"] <= max_debit]
    if filtered.empty:
        return None

    # Only filter on spread when we have real market data
    market_rows = filtered[filtered["price_source"] == "market"]
    if not market_rows.empty:
        tight_spread = market_rows[market_rows["spread_pct"] <= MAX_SPREAD_PCT]
        if not tight_spread.empty:
            filtered = tight_spread

    deltas = []
    for _, row in filtered.iterrows():
        d = bs_delta(spot_price, row["strike"], row["T"],
                     risk_free_rate, row["iv"], option_type)
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
    label = moneyness_label(spot_price, float(best["strike"]), option_type)
    is_estimated = best["price_source"] == "est"

    return {
        "strike": float(best["strike"]),
        "expiration": best["expiration"],
        "dte": dte,
        "option_type": option_type,
        "delta": round(float(best["abs_delta"]), 3),
        "mid_price": round(float(best["mid"]), 2),
        "cost": round(float(best["cost"]), 2),
        "bid": float(best.get("bid", 0) or 0),
        "ask": float(best.get("ask", 0) or 0),
        "iv": round(float(best["iv"]), 3),
        "open_interest": int(best.get("openInterest", 0)),
        "moneyness": label,
        "estimated": is_estimated,
    }
