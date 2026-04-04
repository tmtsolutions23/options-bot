import pandas as pd
import numpy as np
from indicators import ema, atr, rsi, adx


def _sample_ohlcv(n=60):
    np.random.seed(42)
    close = 20.0 + np.cumsum(np.random.randn(n) * 0.3)
    high = close + np.abs(np.random.randn(n) * 0.2)
    low = close - np.abs(np.random.randn(n) * 0.2)
    volume = np.random.randint(500_000, 5_000_000, size=n).astype(float)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def test_ema_length():
    df = _sample_ohlcv()
    result = ema(df["close"], 20)
    assert len(result) == len(df)
    assert not np.isnan(result.iloc[-1])


def test_ema_smoothing():
    df = _sample_ohlcv()
    fast = ema(df["close"], 10)
    slow = ema(df["close"], 50)
    assert fast.std() > slow.std()


def test_atr_positive():
    df = _sample_ohlcv()
    result = atr(df["high"], df["low"], df["close"], 14)
    valid = result.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()


def test_rsi_range():
    df = _sample_ohlcv()
    result = rsi(df["close"], 14)
    valid = result.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_adx_positive():
    df = _sample_ohlcv()
    result = adx(df["high"], df["low"], df["close"], 14)
    valid = result.dropna()
    assert len(valid) > 0
    assert (valid >= 0).all()
