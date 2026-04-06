import pytest
import pandas as pd
import numpy as np
from options_picker import bs_delta, bs_price, moneyness_label, pick_contract


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


def test_bs_price_call_atm():
    price = bs_price(S=20.0, K=20.0, T=10 / 365, r=0.05, sigma=0.40, option_type="call")
    assert 0.5 < price < 2.0


def test_bs_price_put_atm():
    price = bs_price(S=20.0, K=20.0, T=10 / 365, r=0.05, sigma=0.40, option_type="put")
    assert 0.3 < price < 2.0


def test_bs_price_expired():
    # ITM call at expiry = intrinsic
    price = bs_price(S=25.0, K=20.0, T=0, r=0.05, sigma=0.40, option_type="call")
    assert price == pytest.approx(5.0)
    # OTM call at expiry = 0
    price = bs_price(S=15.0, K=20.0, T=0, r=0.05, sigma=0.40, option_type="call")
    assert price == pytest.approx(0.0)


def test_moneyness_label_call():
    assert moneyness_label(20.0, 18.0, "call") == "ITM"
    assert moneyness_label(20.0, 20.0, "call") == "ATM"
    assert moneyness_label(20.0, 22.0, "call") == "OTM"


def test_moneyness_label_put():
    assert moneyness_label(20.0, 22.0, "put") == "ITM"
    assert moneyness_label(20.0, 20.0, "put") == "ATM"
    assert moneyness_label(20.0, 18.0, "put") == "OTM"


def test_pick_contract_zero_bid_ask_uses_bs_estimate():
    """When bid/ask are 0 (premarket), BS estimate should be used."""
    chain = pd.DataFrame({
        "strike": [18.0, 19.0, 20.0, 21.0, 22.0],
        "lastPrice": [2.50, 1.80, 1.10, 0.55, 0.25],
        "bid": [0, 0, 0, 0, 0],
        "ask": [0, 0, 0, 0, 0],
        "impliedVolatility": [0.45, 0.42, 0.40, 0.38, 0.36],
        "openInterest": [500, 1000, 2000, 1500, 300],
        "volume": [100, 200, 500, 300, 50],
        "option_type": ["call"] * 5,
        "expiration": ["2026-04-17"] * 5,
    })
    result = pick_contract(chain, spot_price=20.0, direction="CALL", max_debit=200.0)
    assert result is not None
    assert result["cost"] > 0, "BS estimate should produce non-zero cost"
    assert result["delta"] > 0, "Delta should be computed"
    assert result["estimated"] is True
    assert result["moneyness"] in ("ITM", "ATM", "OTM")


def test_pick_contract_has_moneyness_and_estimated_fields():
    chain = pd.DataFrame({
        "strike": [19.0, 20.0, 21.0],
        "lastPrice": [1.80, 1.10, 0.55],
        "bid": [1.70, 1.00, 0.50],
        "ask": [1.90, 1.20, 0.60],
        "impliedVolatility": [0.42, 0.40, 0.38],
        "openInterest": [1000, 2000, 1500],
        "volume": [200, 500, 300],
        "option_type": ["call"] * 3,
        "expiration": ["2026-04-17"] * 3,
    })
    result = pick_contract(chain, spot_price=20.0, direction="CALL", max_debit=200.0)
    assert result is not None
    assert "moneyness" in result
    assert "estimated" in result
    assert result["estimated"] is False  # real bid/ask provided
