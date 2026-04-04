import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from indicators import ema, atr, rsi, adx
from config import (
    EMA_FAST, EMA_SLOW, ATR_LEN, RSI_LEN, ADX_LEN, ADX_MIN,
    BREAKOUT_LOOKBACK, BREAKOUT_VOL_MULT, PULLBACK_RSI_LOW, PULLBACK_RSI_HIGH,
    OVERSOLD_RSI, VOL_SURGE_MULT, MIN_SIGNALS_TO_QUALIFY,
    SIGNAL_POINTS, ROUND_NUMBER_BONUS, SECTOR_ROTATION_BONUS, EARNINGS_PENALTY,
    STOP_ATR_MULT, TP1_ATR_MULT, TP2_ATR_MULT,
)


def _check_breakout(df: pd.DataFrame) -> bool:
    if len(df) < BREAKOUT_LOOKBACK + 1:
        return False
    lookback = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    twenty_day_high = lookback["high"].max()
    last_close = df["close"].iloc[-1]
    last_vol = df["volume"].iloc[-1]
    avg_vol = lookback["volume"].mean()
    return bool(last_close > twenty_day_high and last_vol >= BREAKOUT_VOL_MULT * avg_vol)


def _check_pullback(df: pd.DataFrame) -> bool:
    if len(df) < EMA_SLOW + 5:
        return False
    ema_fast = ema(df["close"], EMA_FAST)
    ema_slow = ema(df["close"], EMA_SLOW)
    uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
    if not uptrend:
        return False
    rsi_val = rsi(df["close"], RSI_LEN).iloc[-1]
    # Allow slightly above PULLBACK_RSI_HIGH to capture early-pullback scenarios
    if not (PULLBACK_RSI_LOW <= rsi_val <= max(PULLBACK_RSI_HIGH, 65)):
        return False
    ema20_val = ema_fast.iloc[-1]
    last_low = df["low"].iloc[-1]
    last_close = df["close"].iloc[-1]
    # Price touched EMA: low is at or below EMA, or close is within 1% above EMA
    near_ema = last_close <= ema20_val * 1.01
    bounced = last_low <= ema20_val
    touches_ema = near_ema or bounced
    return bool(touches_ema)


def _check_oversold_bounce(df: pd.DataFrame) -> bool:
    if len(df) < EMA_SLOW + 5:
        return False
    rsi_series = rsi(df["close"], RSI_LEN)
    ema_slow = ema(df["close"], EMA_SLOW)
    price_above_ema50 = df["close"].iloc[-1] > ema_slow.iloc[-1]
    if not price_above_ema50:
        return False
    recent_rsi = rsi_series.iloc[-5:]
    was_oversold = (recent_rsi < OVERSOLD_RSI).any()
    now_above = rsi_series.iloc[-1] > OVERSOLD_RSI
    return bool(was_oversold and now_above)


def _check_volume_surge(df: pd.DataFrame) -> bool:
    if len(df) < EMA_SLOW + 5:
        return False
    ema_fast = ema(df["close"], EMA_FAST)
    ema_slow = ema(df["close"], EMA_SLOW)
    price = df["close"].iloc[-1]
    above_both = price > ema_fast.iloc[-1] and price > ema_slow.iloc[-1]
    if not above_both:
        return False
    adx_val = adx(df["high"], df["low"], df["close"], ADX_LEN).iloc[-1]
    if adx_val < ADX_MIN:
        return False
    vol_avg = df["volume"].iloc[-20:].mean() if len(df) >= 20 else df["volume"].mean()
    vol_now = df["volume"].iloc[-1]
    return bool(vol_now >= VOL_SURGE_MULT * vol_avg)


def _near_round_number(price: float) -> bool:
    for level in range(5, 35, 5):
        if abs(price - level) / level < 0.02:
            return True
    return False


def score_swing(df: pd.DataFrame, ticker: str,
                sector_scores: dict,
                earnings_days: int | None,
                ticker_sector: str | None = None) -> dict | None:
    if len(df) < EMA_SLOW + 5:
        return None

    bullish_signals = 0
    bearish_signals = 0

    if _check_breakout(df):
        bullish_signals += 1
    if _check_pullback(df):
        bullish_signals += 1
    if _check_oversold_bounce(df):
        bullish_signals += 1
    if _check_volume_surge(df):
        bullish_signals += 1

    # Bearish equivalents
    if len(df) >= BREAKOUT_LOOKBACK + 1:
        lookback = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
        twenty_day_low = lookback["low"].min()
        if (df["close"].iloc[-1] < twenty_day_low
                and df["volume"].iloc[-1] >= BREAKOUT_VOL_MULT * lookback["volume"].mean()):
            bearish_signals += 1

    ema_fast = ema(df["close"], EMA_FAST)
    ema_slow = ema(df["close"], EMA_SLOW)
    if ema_fast.iloc[-1] < ema_slow.iloc[-1]:
        rsi_val = rsi(df["close"], RSI_LEN).iloc[-1]
        if 45 <= rsi_val <= 60:
            ema20_val = ema_fast.iloc[-1]
            if df["high"].iloc[-1] >= ema20_val >= df["close"].iloc[-1] * 0.99:
                bearish_signals += 1

    rsi_series = rsi(df["close"], RSI_LEN)
    if ema_fast.iloc[-1] < ema_slow.iloc[-1]:
        recent_rsi = rsi_series.iloc[-5:]
        if (recent_rsi > 70).any() and rsi_series.iloc[-1] < 70:
            bearish_signals += 1

    if ema_fast.iloc[-1] < ema_slow.iloc[-1]:
        price = df["close"].iloc[-1]
        if price < ema_fast.iloc[-1] and price < ema_slow.iloc[-1]:
            adx_val = adx(df["high"], df["low"], df["close"], ADX_LEN).iloc[-1]
            vol_avg = df["volume"].iloc[-20:].mean()
            if adx_val > ADX_MIN and df["volume"].iloc[-1] >= VOL_SURGE_MULT * vol_avg:
                bearish_signals += 1

    if bullish_signals >= MIN_SIGNALS_TO_QUALIFY and bullish_signals >= bearish_signals:
        direction = "CALL"
        signal_count = bullish_signals
    elif bearish_signals >= MIN_SIGNALS_TO_QUALIFY:
        direction = "PUT"
        signal_count = bearish_signals
    else:
        return None

    score = signal_count * SIGNAL_POINTS

    last_close = float(df["close"].iloc[-1])
    if _near_round_number(last_close):
        score += ROUND_NUMBER_BONUS

    if ticker_sector and sector_scores:
        sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
        top_3 = [s[0] for s in sorted_sectors[:3]]
        bottom_3 = [s[0] for s in sorted_sectors[-3:]]
        if ticker_sector in top_3:
            score += SECTOR_ROTATION_BONUS
        elif ticker_sector in bottom_3:
            score -= SECTOR_ROTATION_BONUS

    if earnings_days is not None and 0 <= earnings_days <= 3:
        score += EARNINGS_PENALTY

    atr_val = float(atr(df["high"], df["low"], df["close"], ATR_LEN).iloc[-1])
    entry = last_close

    if direction == "CALL":
        stop = entry - STOP_ATR_MULT * atr_val
        tp1 = entry + TP1_ATR_MULT * atr_val
        tp2 = entry + TP2_ATR_MULT * atr_val
    else:
        stop = entry + STOP_ATR_MULT * atr_val
        tp1 = entry - TP1_ATR_MULT * atr_val
        tp2 = entry - TP2_ATR_MULT * atr_val

    return {
        "ticker": ticker,
        "strategy": _describe_signals(direction, df),
        "direction": direction,
        "score": score,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "atr": round(atr_val, 2),
        "signal_count": signal_count,
        "is_day_trade": False,
    }


def _describe_signals(direction: str, df: pd.DataFrame) -> str:
    if direction == "CALL":
        if _check_breakout(df):
            return "Breakout"
        if _check_pullback(df):
            return "Pullback-to-Support"
        if _check_oversold_bounce(df):
            return "Oversold Bounce"
        if _check_volume_surge(df):
            return "Volume Surge"
    else:
        if len(df) >= BREAKOUT_LOOKBACK + 1:
            lookback = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
            if df["close"].iloc[-1] < lookback["low"].min():
                return "Breakdown"
        ema_f = ema(df["close"], EMA_FAST)
        ema_s = ema(df["close"], EMA_SLOW)
        if ema_f.iloc[-1] < ema_s.iloc[-1]:
            rsi_val = rsi(df["close"], RSI_LEN).iloc[-1]
            if 45 <= rsi_val <= 60:
                return "Pullback-to-Resistance"
            rsi_series = rsi(df["close"], RSI_LEN)
            if (rsi_series.iloc[-5:] > 70).any() and rsi_series.iloc[-1] < 70:
                return "Overbought Rejection"
        return "Bearish Momentum"
    return "Swing"
