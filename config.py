import os
from dotenv import load_dotenv

load_dotenv()

# --- Discord ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))

# --- Database ---
DB_PATH = os.environ.get("DB_PATH", "scanner.db")

# --- Equity ---
STARTING_EQUITY = float(os.environ.get("STARTING_EQUITY", "250.0"))

# --- Risk Tiers ---
RISK_TIERS = [
    {"equity_max": 500, "risk_pct": 0.04, "min_debit": 10, "max_debit": 25, "max_concurrent": 2, "daily_loss_cap_pct": 0.08},
    {"equity_max": 1500, "risk_pct": 0.03, "min_debit": 15, "max_debit": 50, "max_concurrent": 2, "daily_loss_cap_pct": 0.06},
    {"equity_max": 4000, "risk_pct": 0.025, "min_debit": 20, "max_debit": 80, "max_concurrent": 3, "daily_loss_cap_pct": 0.05},
    {"equity_max": 999999, "risk_pct": 0.02, "min_debit": 30, "max_debit": 120, "max_concurrent": 3, "daily_loss_cap_pct": 0.04},
]

# --- Indicators ---
EMA_FAST = 20
EMA_SLOW = 50
ATR_LEN = 14
RSI_LEN = 14
ADX_LEN = 14
ADX_MIN = 20

# --- Swing Strategy ---
BREAKOUT_LOOKBACK = 20
BREAKOUT_VOL_MULT = 1.5
PULLBACK_RSI_LOW = 40
PULLBACK_RSI_HIGH = 55
OVERSOLD_RSI = 30
VOL_SURGE_MULT = 2.0
MIN_SIGNALS_TO_QUALIFY = 2

# --- Scoring ---
SIGNAL_POINTS = 25
ROUND_NUMBER_BONUS = 10
SECTOR_ROTATION_BONUS = 10
EARNINGS_PENALTY = -15

# --- Entry/Stop/Target ---
STOP_ATR_MULT = 1.0
TP1_ATR_MULT = 1.5
TP2_ATR_MULT = 3.0

# --- Gap Strategy ---
GAP_MIN_PCT = 3.0
GAP_VOL_MULT = 2.0
MAX_GAP_ALERTS_PER_DAY = 1
PDT_RESERVE = 1

# --- Options ---
TARGET_DTE_MIN = 7
TARGET_DTE_MAX = 14
TARGET_DELTA_MIN = 0.35
TARGET_DELTA_MAX = 0.45
MAX_SPREAD_PCT = 0.30

# --- Universe ---
PRICE_MIN = 2.0
PRICE_MAX = 30.0
MIN_AVG_VOLUME = 500_000
DYNAMIC_MIN_VOLUME = 1_000_000

# --- Scan Schedule ---
SCAN_HOUR = 7
SCAN_MINUTE = 50
DELIVERY_HOUR = 8
DELIVERY_MINUTE = 0

# --- Loss Protection ---
WEEKLY_DRAWDOWN_HALT_PCT = 0.15
CONSECUTIVE_LOSS_PAUSE = 3

# --- Sector ETFs ---
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

# --- Rate Limiting ---
YFINANCE_CHUNK_SIZE = 25
YFINANCE_CHUNK_DELAY_MIN = 2.0
YFINANCE_CHUNK_DELAY_MAX = 4.0
YFINANCE_MAX_RETRIES = 3
