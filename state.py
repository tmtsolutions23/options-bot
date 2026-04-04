import aiosqlite
from config import STARTING_EQUITY
from datetime import datetime, timedelta
import pandas_market_calendars as mcal


class StateDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = None

    async def init(self):
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()

    async def close(self):
        if self.db:
            await self.db.close()

    async def _create_tables(self):
        # C1 fix: split CREATE TABLE statements from parameterized INSERT OR IGNORE
        # to prevent SQL injection via string formatting of STARTING_EQUITY.
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS equity (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                amount REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                setup_number INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                strategy TEXT NOT NULL,
                direction TEXT NOT NULL,
                is_day_trade INTEGER NOT NULL DEFAULT 0,
                pnl REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS day_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weekly_stats (
                week_key TEXT PRIMARY KEY,
                start_equity REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS open_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                setup_number INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                strategy TEXT NOT NULL,
                direction TEXT NOT NULL,
                is_day_trade INTEGER NOT NULL DEFAULT 0,
                opened_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS consecutive_losses (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                count INTEGER NOT NULL DEFAULT 0
            );
        """)
        # Parameterized inserts — safe from injection
        await self.db.execute(
            "INSERT OR IGNORE INTO equity (id, amount) VALUES (1, ?)", (STARTING_EQUITY,)
        )
        await self.db.execute(
            "INSERT OR IGNORE INTO consecutive_losses (id, count) VALUES (1, 0)"
        )
        await self.db.commit()

    async def get_equity(self) -> float:
        async with self.db.execute("SELECT amount FROM equity WHERE id = 1") as cur:
            row = await cur.fetchone()
            return float(row["amount"]) if row else STARTING_EQUITY

    async def update_equity(self, amount: float):
        await self.db.execute("UPDATE equity SET amount = ? WHERE id = 1", (amount,))
        await self.db.commit()

    async def log_trade(self, date: str, setup_number: int, ticker: str,
                        strategy: str, direction: str, is_day_trade: bool, pnl: float):
        await self.db.execute(
            "INSERT INTO trades (date, setup_number, ticker, strategy, direction, is_day_trade, pnl) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, setup_number, ticker, strategy, direction, int(is_day_trade), pnl),
        )
        equity = await self.get_equity()
        await self.update_equity(equity + pnl)
        if pnl < 0:
            await self.db.execute(
                "UPDATE consecutive_losses SET count = count + 1 WHERE id = 1"
            )
        else:
            await self.db.execute(
                "UPDATE consecutive_losses SET count = 0 WHERE id = 1"
            )
        await self.db.commit()

    async def get_trades_since(self, since_date: str) -> list:
        async with self.db.execute(
            "SELECT * FROM trades WHERE date >= ? ORDER BY date", (since_date,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def get_trades_for_date(self, date: str) -> list:
        async with self.db.execute(
            "SELECT * FROM trades WHERE date = ?", (date,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def record_day_trade(self, trade_date: str):
        await self.db.execute(
            "INSERT INTO day_trades (trade_date) VALUES (?)", (trade_date,)
        )
        await self.db.commit()

    async def get_day_trades_in_window(self, as_of_date: str) -> int:
        nyse = mcal.get_calendar("NYSE")
        end = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        # Look back far enough to find the 5 most recent trading days
        schedule = nyse.valid_days(
            start_date=end - timedelta(days=14), end_date=end
        )
        if len(schedule) < 5:
            trading_days = [d.strftime("%Y-%m-%d") for d in schedule]
        else:
            trading_days = [d.strftime("%Y-%m-%d") for d in schedule[-5:]]
        # Use a date range: from the start of the rolling window up to as_of_date
        # This ensures trades recorded on non-trading-day dates (e.g. weekends) are counted
        window_start = trading_days[0] if trading_days else as_of_date
        async with self.db.execute(
            "SELECT COUNT(*) as cnt FROM day_trades WHERE trade_date >= ? AND trade_date <= ?",
            (window_start, as_of_date),
        ) as cur:
            row = await cur.fetchone()
            return row["cnt"]

    async def get_remaining_day_trades(self, as_of_date: str) -> int:
        used = await self.get_day_trades_in_window(as_of_date)
        return max(0, 3 - used)

    async def save_week_start_equity(self, week_key: str, equity: float):
        await self.db.execute(
            "INSERT OR REPLACE INTO weekly_stats (week_key, start_equity) VALUES (?, ?)",
            (week_key, equity),
        )
        await self.db.commit()

    async def get_week_start_equity(self, week_key: str) -> float:
        async with self.db.execute(
            "SELECT start_equity FROM weekly_stats WHERE week_key = ?", (week_key,)
        ) as cur:
            row = await cur.fetchone()
            return float(row["start_equity"]) if row else await self.get_equity()

    async def open_position(self, scan_date: str, setup_number: int, ticker: str,
                            strategy: str, direction: str, is_day_trade: bool):
        await self.db.execute(
            "INSERT INTO open_positions (scan_date, setup_number, ticker, strategy, direction, is_day_trade) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scan_date, setup_number, ticker, strategy, direction, int(is_day_trade)),
        )
        if is_day_trade:
            await self.record_day_trade(scan_date)
        await self.db.commit()

    async def get_open_positions(self) -> list:
        async with self.db.execute("SELECT * FROM open_positions") as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def close_position(self, position_id: int, pnl: float, close_date: str | None = None):
        async with self.db.execute(
            "SELECT * FROM open_positions WHERE id = ?", (position_id,)
        ) as cur:
            pos = await cur.fetchone()
        if not pos:
            return
        pos = dict(pos)
        # C2 fix: use close_date (today) rather than the position's scan_date so
        # multi-day swing P&L is recorded on the day it was actually closed.
        trade_date = close_date if close_date is not None else pos["scan_date"]
        await self.log_trade(
            date=trade_date,
            setup_number=pos["setup_number"],
            ticker=pos["ticker"],
            strategy=pos["strategy"],
            direction=pos["direction"],
            is_day_trade=bool(pos["is_day_trade"]),
            pnl=pnl,
        )
        await self.db.execute("DELETE FROM open_positions WHERE id = ?", (position_id,))
        await self.db.commit()

    async def get_consecutive_losses(self) -> int:
        async with self.db.execute(
            "SELECT count FROM consecutive_losses WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
            return row["count"] if row else 0

    async def get_daily_pnl(self, date: str) -> float:
        async with self.db.execute(
            "SELECT COALESCE(SUM(pnl), 0) as total FROM trades WHERE date = ?", (date,)
        ) as cur:
            row = await cur.fetchone()
            return float(row["total"])
