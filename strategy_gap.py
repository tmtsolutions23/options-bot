from indicators import ema, atr
from config import (
    EMA_FAST, EMA_SLOW, ATR_LEN,
    GAP_MIN_PCT, GAP_VOL_MULT, PDT_RESERVE,
    STOP_ATR_MULT, SIGNAL_POINTS,
)
import pandas as pd


def score_gap(df: pd.DataFrame, ticker: str, premarket: dict | None,
              pdt_remaining: int) -> dict | None:
    if premarket is None:
        return None
    if pdt_remaining < PDT_RESERVE + 1:
        return None
    if len(df) < EMA_SLOW + 5:
        return None

    gap_pct = abs(premarket["change_pct"])
    if gap_pct < GAP_MIN_PCT:
        return None

    prev_close = premarket["prev_close"]
    pre_price = premarket["price"]
    gap_up = pre_price > prev_close

    ema_fast = ema(df["close"], EMA_FAST)
    ema_slow = ema(df["close"], EMA_SLOW)
    uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
    downtrend = ema_fast.iloc[-1] < ema_slow.iloc[-1]

    if gap_up and not uptrend:
        return None
    if not gap_up and not downtrend:
        return None

    direction = "CALL" if gap_up else "PUT"
    atr_val = float(atr(df["high"], df["low"], df["close"], ATR_LEN).iloc[-1])
    gap_range = abs(pre_price - prev_close)

    if gap_up:
        entry = prev_close + 0.5 * gap_range
        stop = entry - STOP_ATR_MULT * atr_val
        tp1 = pre_price
        tp2 = prev_close + 1.5 * gap_range
    else:
        entry = prev_close - 0.5 * gap_range
        stop = entry + STOP_ATR_MULT * atr_val
        tp1 = pre_price
        tp2 = prev_close - 1.5 * gap_range

    score = SIGNAL_POINTS * 2
    if gap_pct > 5.0:
        score += SIGNAL_POINTS

    return {
        "ticker": ticker,
        "strategy": f"Gap {'Up' if gap_up else 'Down'} {gap_pct:.1f}%",
        "direction": direction,
        "score": score,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "atr": round(atr_val, 2),
        "gap_pct": round(gap_pct, 1),
        "is_day_trade": True,
        "tag": f"DAY TRADE (uses 1 of {pdt_remaining} remaining)",
    }
