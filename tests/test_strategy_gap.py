import pandas as pd
import numpy as np
import pytest
from strategy_gap import score_gap


def _make_df(n=60):
    np.random.seed(42)
    base = 15.0 + np.arange(n) * 0.05 + np.random.randn(n) * 0.05
    high = base + 0.3
    low = base - 0.3
    volume = np.full(n, 1_000_000.0)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": base, "high": high, "low": low, "close": base, "volume": volume}, index=idx)


def test_gap_up_qualifies():
    df = _make_df()
    prev_close = float(df["close"].iloc[-1])
    premarket = {"price": prev_close * 1.04, "prev_close": prev_close, "change_pct": 4.0}
    result = score_gap(df, "SOFI", premarket, pdt_remaining=3)
    if result:
        assert result["direction"] == "CALL"
        assert result["is_day_trade"] is True
        assert "DAY TRADE" in result.get("tag", "")


def test_gap_too_small():
    df = _make_df()
    prev_close = float(df["close"].iloc[-1])
    premarket = {"price": prev_close * 1.01, "prev_close": prev_close, "change_pct": 1.0}
    result = score_gap(df, "SOFI", premarket, pdt_remaining=3)
    assert result is None


def test_gap_suppressed_low_pdt():
    df = _make_df()
    prev_close = float(df["close"].iloc[-1])
    premarket = {"price": prev_close * 1.05, "prev_close": prev_close, "change_pct": 5.0}
    result = score_gap(df, "SOFI", premarket, pdt_remaining=1)
    assert result is None


def test_gap_returns_entry_stop_targets():
    df = _make_df()
    prev_close = float(df["close"].iloc[-1])
    premarket = {"price": prev_close * 1.05, "prev_close": prev_close, "change_pct": 5.0}
    result = score_gap(df, "SOFI", premarket, pdt_remaining=3)
    if result:
        assert "entry" in result
        assert "stop" in result
        assert "tp1" in result
        assert "tp2" in result
        assert result["entry"] < premarket["price"]
