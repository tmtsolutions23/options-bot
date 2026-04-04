import json
import os
import yfinance as yf
from config import PRICE_MIN, PRICE_MAX, DYNAMIC_MIN_VOLUME


SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_universe.json")


def load_seed_universe() -> list[str]:
    with open(SEED_FILE) as f:
        return json.load(f)


def get_dynamic_tickers() -> list[str]:
    """Fetch previous day's most active / top gainers / top losers via yfinance screener."""
    dynamic = []
    for screen_name in ["most_actives", "day_gainers", "day_losers"]:
        try:
            result = yf.screen(screen_name)
            if result and "quotes" in result:
                for quote in result["quotes"]:
                    symbol = quote.get("symbol", "")
                    price = quote.get("regularMarketPrice", 0) or 0
                    avg_vol = quote.get("averageDailyVolume3Month", 0) or 0
                    if (PRICE_MIN <= price <= PRICE_MAX
                            and avg_vol >= DYNAMIC_MIN_VOLUME
                            and symbol.isalpha()
                            and len(symbol) <= 5):
                        dynamic.append(symbol)
        except Exception:
            continue
    return list(set(dynamic))


def build_daily_universe() -> list[str]:
    seed = load_seed_universe()
    dynamic = get_dynamic_tickers()
    combined = list(dict.fromkeys(seed + dynamic))  # preserves order, deduplicates
    return combined
