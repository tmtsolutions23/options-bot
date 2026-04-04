import pandas as pd
import numpy as np
import pytest
from strategy_swing import score_swing, _check_breakout, _check_pullback, _check_oversold_bounce, _check_volume_surge


def _make_uptrend_df(n=60):
    """Create a DataFrame with a clear uptrend."""
    np.random.seed(42)
    base = 15.0 + np.arange(n) * 0.1 + np.random.randn(n) * 0.05
    high = base + 0.3
    low = base - 0.3
    volume = np.full(n, 1_000_000.0)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": base, "high": high, "low": low, "close": base, "volume": volume}, index=idx)


def _make_breakout_df():
    """Price breaks above 20-day high with volume spike."""
    df = _make_uptrend_df(60)
    twenty_day_high = df["high"].iloc[-21:-1].max()
    df.loc[df.index[-1], "close"] = twenty_day_high + 1.0
    df.loc[df.index[-1], "high"] = twenty_day_high + 1.2
    df.loc[df.index[-1], "volume"] = df["volume"].iloc[-21:-1].mean() * 2.0
    return df


def test_check_breakout_fires():
    df = _make_breakout_df()
    assert _check_breakout(df) is True


def test_check_breakout_no_volume():
    df = _make_breakout_df()
    df.loc[df.index[-1], "volume"] = 100
    assert _check_breakout(df) is False


def test_check_pullback_in_uptrend():
    df = _make_uptrend_df(60)
    from indicators import ema
    ema20 = ema(df["close"], 20)
    df.loc[df.index[-1], "close"] = ema20.iloc[-1] + 0.01
    df.loc[df.index[-1], "low"] = ema20.iloc[-1] - 0.05
    assert _check_pullback(df) is True


def test_oversold_bounce():
    df = _make_uptrend_df(60)
    df.loc[df.index[-3], "close"] = df["close"].iloc[-4] - 5.0
    df.loc[df.index[-2], "close"] = df["close"].iloc[-4] - 6.0
    df.loc[df.index[-1], "close"] = df["close"].iloc[-4] - 4.0
    result = _check_oversold_bounce(df)
    assert isinstance(result, bool)


def test_score_swing_returns_dict_or_none():
    df = _make_breakout_df()
    result = score_swing(df, "SOFI", sector_scores={"Technology": 5.0}, earnings_days=None)
    assert result is None or isinstance(result, dict)
    if result:
        assert "score" in result
        assert "direction" in result
        assert "entry" in result
        assert "stop" in result
        assert "tp1" in result
        assert "tp2" in result


def test_score_swing_needs_min_signals():
    df = _make_uptrend_df(60)
    result = score_swing(df, "SOFI", sector_scores={}, earnings_days=None)
    assert result is None
