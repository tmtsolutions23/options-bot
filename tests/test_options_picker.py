import pytest
import pandas as pd
import numpy as np
from options_picker import bs_delta, pick_contract


def test_bs_delta_call_atm():
    d = bs_delta(S=20.0, K=20.0, T=10 / 365, r=0.05, sigma=0.40, option_type="call")
    assert 0.45 < d < 0.60


def test_bs_delta_put_atm():
    d = bs_delta(S=20.0, K=20.0, T=10 / 365, r=0.05, sigma=0.40, option_type="put")
    assert -0.60 < d < -0.45


def test_bs_delta_deep_itm_call():
    d = bs_delta(S=25.0, K=15.0, T=10 / 365, r=0.05, sigma=0.30, option_type="call")
    assert d > 0.90


def test_bs_delta_deep_otm_call():
    d = bs_delta(S=15.0, K=25.0, T=10 / 365, r=0.05, sigma=0.30, option_type="call")
    assert d < 0.10


def test_pick_contract_returns_best():
    chain = pd.DataFrame({
        "strike": [18.0, 19.0, 20.0, 21.0, 22.0],
        "lastPrice": [2.50, 1.80, 1.10, 0.55, 0.25],
        "bid": [2.40, 1.70, 1.00, 0.50, 0.20],
        "ask": [2.60, 1.90, 1.20, 0.60, 0.30],
        "impliedVolatility": [0.45, 0.42, 0.40, 0.38, 0.36],
        "openInterest": [500, 1000, 2000, 1500, 300],
        "volume": [100, 200, 500, 300, 50],
        "option_type": ["call"] * 5,
        "expiration": ["2026-04-11"] * 5,
    })
    result = pick_contract(chain, spot_price=20.0, direction="CALL", max_debit=25.0)
    assert result is not None
    assert "strike" in result
    assert "cost" in result
    assert result["cost"] <= 25.0


def test_pick_contract_skips_expensive():
    chain = pd.DataFrame({
        "strike": [18.0],
        "lastPrice": [3.00],
        "bid": [2.90],
        "ask": [3.10],
        "impliedVolatility": [0.40],
        "openInterest": [100],
        "volume": [50],
        "option_type": ["call"],
        "expiration": ["2026-04-11"],
    })
    result = pick_contract(chain, spot_price=20.0, direction="CALL", max_debit=25.0)
    assert result is None


def test_pick_contract_put():
    chain = pd.DataFrame({
        "strike": [18.0, 19.0, 20.0, 21.0, 22.0],
        "lastPrice": [0.20, 0.50, 1.00, 1.70, 2.50],
        "bid": [0.15, 0.45, 0.90, 1.60, 2.40],
        "ask": [0.25, 0.55, 1.10, 1.80, 2.60],
        "impliedVolatility": [0.36, 0.38, 0.40, 0.42, 0.45],
        "openInterest": [300, 1500, 2000, 1000, 500],
        "volume": [50, 300, 500, 200, 100],
        "option_type": ["put"] * 5,
        "expiration": ["2026-04-11"] * 5,
    })
    result = pick_contract(chain, spot_price=20.0, direction="PUT", max_debit=25.0)
    assert result is not None
    assert result["option_type"] == "put"
