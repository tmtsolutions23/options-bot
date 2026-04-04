import time
import random
import yfinance as yf
import pandas as pd
from config import (
    YFINANCE_CHUNK_SIZE, YFINANCE_CHUNK_DELAY_MIN, YFINANCE_CHUNK_DELAY_MAX,
    YFINANCE_MAX_RETRIES, SECTOR_ETFS,
)


def fetch_daily_ohlcv(tickers: list[str], period: str = "3mo") -> dict[str, pd.DataFrame]:
    """Batch-download daily OHLCV for all tickers. Returns {ticker: DataFrame}."""
    result = {}
    for attempt in range(YFINANCE_MAX_RETRIES):
        try:
            data = yf.download(
                tickers, period=period, interval="1d",
                group_by="ticker", progress=False, threads=True,
            )
            if data.empty:
                return result
            if len(tickers) == 1:
                result[tickers[0]] = data.dropna()
            else:
                for ticker in tickers:
                    try:
                        df = data[ticker].dropna()
                        if not df.empty:
                            df.columns = [c.lower() for c in df.columns]
                            result[ticker] = df
                    except (KeyError, AttributeError):
                        continue
            return result
        except Exception:
            if attempt < YFINANCE_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return result


def fetch_premarket_data(tickers: list[str]) -> dict[str, dict]:
    """Fetch pre-market price and volume for tickers. Returns {ticker: {price, change_pct, volume}}."""
    result = {}
    chunks = [tickers[i:i + YFINANCE_CHUNK_SIZE] for i in range(0, len(tickers), YFINANCE_CHUNK_SIZE)]
    for chunk in chunks:
        for ticker in chunk:
            try:
                tk = yf.Ticker(ticker)
                info = tk.info
                pre_price = info.get("preMarketPrice")
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
                if pre_price and prev_close and prev_close > 0:
                    change_pct = ((pre_price - prev_close) / prev_close) * 100
                    result[ticker] = {
                        "price": pre_price,
                        "prev_close": prev_close,
                        "change_pct": change_pct,
                    }
            except Exception:
                continue
        delay = random.uniform(YFINANCE_CHUNK_DELAY_MIN, YFINANCE_CHUNK_DELAY_MAX)
        time.sleep(delay)
    return result


def fetch_sector_relative_strength() -> dict[str, float]:
    """Calculate 5-day return for each sector ETF. Returns {sector_name: return_pct}."""
    etf_tickers = list(SECTOR_ETFS.values())
    data = yf.download(etf_tickers, period="10d", interval="1d", progress=False, threads=True)
    result = {}
    for sector_name, etf in SECTOR_ETFS.items():
        try:
            if len(etf_tickers) == 1:
                closes = data["Close"]
            else:
                closes = data[etf]["Close"] if etf in data.columns.get_level_values(0) else data[(etf, "Close")]
            if len(closes) >= 5:
                ret = (closes.iloc[-1] - closes.iloc[-5]) / closes.iloc[-5] * 100
                result[sector_name] = float(ret)
        except Exception:
            continue
    return result


def fetch_options_chain(ticker: str, max_dte: int = 14) -> pd.DataFrame:
    """Fetch options chain for a ticker, filtering to expirations within max_dte days."""
    try:
        tk = yf.Ticker(ticker)
        expirations = tk.options
        if not expirations:
            return pd.DataFrame()
        from datetime import datetime, timedelta
        cutoff = (datetime.now() + timedelta(days=max_dte)).strftime("%Y-%m-%d")
        valid_exps = [e for e in expirations if e <= cutoff]
        if not valid_exps:
            return pd.DataFrame()
        frames = []
        for exp in valid_exps:
            try:
                chain = tk.option_chain(exp)
                calls = chain.calls.copy()
                calls["option_type"] = "call"
                calls["expiration"] = exp
                puts = chain.puts.copy()
                puts["option_type"] = "put"
                puts["expiration"] = exp
                frames.extend([calls, puts])
            except Exception:
                continue
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
    except Exception:
        return pd.DataFrame()


def get_earnings_date(ticker: str):
    """Return next earnings date or None."""
    try:
        tk = yf.Ticker(ticker)
        cal = tk.calendar
        if cal is not None and "Earnings Date" in cal:
            dates = cal["Earnings Date"]
            if isinstance(dates, list) and len(dates) > 0:
                return dates[0]
            return dates
    except Exception:
        pass
    return None
