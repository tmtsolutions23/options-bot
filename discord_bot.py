"""
discord_bot.py — Integration layer wiring all scanner modules into a Discord bot.

Slash commands: /close, /eod, /bankroll
Scheduled task: morning_scan at 7:50 AM ET (weekdays)
Reaction listener: on_raw_reaction_add to open positions from scan results
"""

import asyncio
import logging
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks

from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    DB_PATH,
    SCAN_HOUR,
    SCAN_MINUTE,
)
from state import StateDB
from scanner import (
    fetch_daily_ohlcv,
    fetch_premarket_data,
    fetch_sector_relative_strength,
    fetch_options_chain,
    get_earnings_date,
)
from strategy_swing import score_swing
from strategy_gap import score_gap
from options_picker import pick_contract
from risk_manager import get_tier, calc_debit_budget, should_halt, check_loss_protection
from universe import build_daily_universe

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Number emojis for the first 9 setups
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


class ScannerBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.message_content = True
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)
        self.db = StateDB(DB_PATH)
        # Maps message_id -> list of setup dicts (populated after each scan)
        self.scan_results: dict[int, list[dict]] = {}

    async def setup_hook(self):
        await self.db.init()
        self._register_commands()
        await self.tree.sync()
        self.morning_scan.start()
        logger.info("Bot ready, slash commands synced, morning_scan loop started.")

    async def close(self):
        self.morning_scan.cancel()
        await self.db.close()
        await super().close()

    # ------------------------------------------------------------------ #
    #  Slash commands                                                       #
    # ------------------------------------------------------------------ #

    def _register_commands(self):
        @self.tree.command(name="close", description="Close a trade and log P&L")
        @app_commands.describe(
            setup_number="The setup number from the scan message",
            pnl="Profit or loss (negative for a loss, e.g. -15.50)",
        )
        async def cmd_close(interaction: discord.Interaction, setup_number: int, pnl: float):
            await interaction.response.defer(ephemeral=False)
            today_str = datetime.now(tz=ET).strftime("%Y-%m-%d")

            # C5 fix: match by setup_number only — no date filter — so multi-day swing
            # trades can be closed on a different day than they were opened.
            # If multiple matches exist (e.g. same number reused), pick the most recent.
            open_positions = await self.db.get_open_positions()
            matched = [p for p in open_positions if p["setup_number"] == setup_number]

            if not matched:
                await interaction.followup.send(
                    f"No open position found for setup #{setup_number}."
                )
                return

            # Most recent = highest id (auto-increment)
            pos = max(matched, key=lambda p: p["id"])
            await self.db.close_position(pos["id"], pnl, close_date=today_str)

            equity = await self.db.get_equity()
            sign = "+" if pnl >= 0 else ""
            await interaction.followup.send(
                f"**Closed #{setup_number}** — {pos['ticker']} {pos['strategy']} {pos['direction']}\n"
                f"P&L: **{sign}${pnl:.2f}**\n"
                f"New bankroll: **${equity:.2f}**"
            )

        @self.tree.command(name="eod", description="Show end-of-day summary")
        async def cmd_eod(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False)
            today_str = datetime.now(tz=ET).strftime("%Y-%m-%d")

            equity = await self.db.get_equity()
            daily_pnl = await self.db.get_daily_pnl(today_str)
            equity_before = equity - daily_pnl

            trades_today = await self.db.get_trades_for_date(today_str)
            open_positions = await self.db.get_open_positions()
            open_swings = [p for p in open_positions if not p["is_day_trade"]]

            # Weekly P&L
            today = datetime.now(tz=ET).date()
            week_monday = today - timedelta(days=today.weekday())
            week_key = week_monday.strftime("%Y-%m-%d")
            week_start_eq = await self.db.get_week_start_equity(week_key)
            weekly_pnl = equity - week_start_eq

            pdt_remaining = await self.db.get_remaining_day_trades(today_str)

            # Build summary
            wins = sum(1 for t in trades_today if t["pnl"] > 0)
            losses = sum(1 for t in trades_today if t["pnl"] <= 0)
            closed_count = len(trades_today)

            lines = [
                "**End-of-Day Summary**",
                f"Date: {today_str}",
                f"Trades closed: {closed_count} ({wins}W / {losses}L)",
                f"Daily P&L: {'+'if daily_pnl >= 0 else ''}${daily_pnl:.2f}",
                f"Bankroll: ${equity_before:.2f} → **${equity:.2f}**",
                f"Weekly P&L: {'+'if weekly_pnl >= 0 else ''}${weekly_pnl:.2f}",
                f"Day trades remaining (rolling 5-day): {pdt_remaining}",
            ]

            if open_swings:
                lines.append(f"\nOpen swing positions ({len(open_swings)}):")
                for pos in open_swings:
                    lines.append(f"  • #{pos['setup_number']} {pos['ticker']} {pos['strategy']} {pos['direction']}")

            await interaction.followup.send("\n".join(lines))

        @self.tree.command(name="bankroll", description="Show current bankroll, risk tier, and budget")
        async def cmd_bankroll(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False)
            today_str = datetime.now(tz=ET).strftime("%Y-%m-%d")

            equity = await self.db.get_equity()
            tier = get_tier(equity)
            budget = calc_debit_budget(equity)
            pdt_remaining = await self.db.get_remaining_day_trades(today_str)

            tier_index = 1
            from config import RISK_TIERS
            for i, t in enumerate(RISK_TIERS):
                if tier is t:
                    tier_index = i + 1
                    break

            await interaction.followup.send(
                f"**Bankroll Status**\n"
                f"Equity: **${equity:.2f}**\n"
                f"Risk tier: {tier_index} (max debit ${tier['min_debit']}–${tier['max_debit']}, "
                f"risk {tier['risk_pct']:.1%}/trade)\n"
                f"Suggested debit budget: **${budget:.2f}**\n"
                f"Day trades remaining (rolling 5-day): {pdt_remaining}\n"
                f"Max concurrent positions: {tier['max_concurrent']}"
            )

    # ------------------------------------------------------------------ #
    #  Scheduled morning scan                                              #
    # ------------------------------------------------------------------ #

    @tasks.loop(time=dtime(hour=SCAN_HOUR, minute=SCAN_MINUTE, tzinfo=ET))
    async def morning_scan(self):
        now = datetime.now(tz=ET)
        # Weekdays only (Monday=0 … Friday=4)
        if now.weekday() > 4:
            return

        channel = self.get_channel(DISCORD_CHANNEL_ID)
        if channel is None:
            logger.warning("Scan channel %d not found.", DISCORD_CHANNEL_ID)
            return

        today_str = now.strftime("%Y-%m-%d")
        today = now.date()

        # Monday: post weekly summary then save new week start equity
        if now.weekday() == 0:
            await self._post_weekly_summary(channel, today)
            equity = await self.db.get_equity()
            week_key = today.strftime("%Y-%m-%d")
            await self.db.save_week_start_equity(week_key, equity)

        # Gather async state before handing off to thread
        equity = await self.db.get_equity()
        week_monday = today - timedelta(days=today.weekday())
        week_key = week_monday.strftime("%Y-%m-%d")
        week_start_eq = await self.db.get_week_start_equity(week_key)
        consecutive_losses = await self.db.get_consecutive_losses()
        daily_pnl = await self.db.get_daily_pnl(today_str)
        pdt_remaining = await self.db.get_remaining_day_trades(today_str)

        # Halt check
        halt, halt_reason = should_halt(equity, week_start_eq, consecutive_losses, daily_pnl)
        if halt:
            await channel.send(f"**Scan halted.** {halt_reason}")
            return

        # Loss protection check
        protection = check_loss_protection(equity, daily_pnl)
        if protection["daily_cap_hit"]:
            await channel.send(
                f"**Daily loss cap reached** (${protection['daily_cap']:.2f}). "
                f"No new positions today."
            )
            return

        await channel.send(
            f"**Pre-market scan starting** — {today_str}\n"
            f"Equity: ${equity:.2f} | PDT remaining: {pdt_remaining}"
        )

        # Run blocking scan in a thread
        try:
            setups = await asyncio.to_thread(
                _run_scan, equity, today_str, protection, pdt_remaining
            )
        except Exception as exc:
            logger.exception("Scan failed: %s", exc)
            await channel.send(f"Scan error: {exc}")
            return

        if not setups:
            await channel.send("No qualifying setups found today.")
            return

        # Post results
        budget = calc_debit_budget(equity)
        lines = [f"**Morning Scan — {today_str}** | Budget/trade: ${budget:.2f}\n"]
        for i, setup in enumerate(setups[:9]):
            emoji = NUMBER_EMOJIS[i]
            contract = setup.get("contract")
            contract_str = ""
            if contract:
                est_tag = "~" if contract.get("estimated") else ""
                moneyness = contract.get("moneyness", "")
                contract_str = (
                    f" | {contract['option_type'].upper()} ${contract['strike']} "
                    f"{moneyness} exp {contract['expiration']} "
                    f"({est_tag}${contract['cost']:.0f} debit, "
                    f"δ{contract['delta']:.2f}, IV {contract['iv']:.0%})"
                )
            tag = f" [{setup.get('tag', '')}]" if setup.get("tag") else ""
            day_trade_flag = " 📅 DAY TRADE" if setup.get("is_day_trade") else ""
            lines.append(
                f"{emoji} **#{i+1} {setup['ticker']}** — {setup['strategy']} {setup['direction']}{day_trade_flag}{tag}\n"
                f"   Entry: ${setup['entry']} | Stop: ${setup['stop']} | "
                f"TP1: ${setup['tp1']} | TP2: ${setup['tp2']}"
                f"{contract_str}"
            )

        msg = await channel.send("\n".join(lines))
        # I7 fix: clear previous scan entries so the dict doesn't grow unbounded;
        # only the latest scan message needs to be tracked for reaction handling.
        self.scan_results.clear()
        self.scan_results[msg.id] = setups[:9]

        # Add number reactions
        for i in range(min(len(setups), 9)):
            await msg.add_reaction(NUMBER_EMOJIS[i])

    @morning_scan.before_loop
    async def before_morning_scan(self):
        await self.wait_until_ready()

    # ------------------------------------------------------------------ #
    #  Reaction listener — open a position                                 #
    # ------------------------------------------------------------------ #

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore the bot's own reactions
        if payload.user_id == self.user.id:
            return

        msg_id = payload.message_id
        if msg_id not in self.scan_results:
            return

        emoji = str(payload.emoji)
        if emoji not in NUMBER_EMOJIS:
            return

        setup_idx = NUMBER_EMOJIS.index(emoji)
        setups = self.scan_results[msg_id]
        if setup_idx >= len(setups):
            return

        setup = setups[setup_idx]
        setup_number = setup_idx + 1
        today_str = datetime.now(tz=ET).strftime("%Y-%m-%d")

        # Guard: don't open the same setup twice
        open_positions = await self.db.get_open_positions()
        already_open = any(
            p["setup_number"] == setup_number and p["scan_date"] == today_str
            for p in open_positions
        )
        if already_open:
            return

        await self.db.open_position(
            scan_date=today_str,
            setup_number=setup_number,
            ticker=setup["ticker"],
            strategy=setup["strategy"],
            direction=setup["direction"],
            is_day_trade=bool(setup.get("is_day_trade", False)),
        )

        channel = self.get_channel(payload.channel_id)
        if channel:
            await channel.send(
                f"Opened #{setup_number} — **{setup['ticker']}** "
                f"{setup['strategy']} {setup['direction']}"
                + (" (DAY TRADE)" if setup.get("is_day_trade") else "")
            )

    # ------------------------------------------------------------------ #
    #  Weekly summary helper                                               #
    # ------------------------------------------------------------------ #

    async def _post_weekly_summary(self, channel: discord.TextChannel, today):
        """Post last week's performance summary on Monday morning."""
        # Previous week: Monday..Sunday using timedelta (safe across year boundaries)
        prev_monday = today - timedelta(days=7)
        prev_sunday = today - timedelta(days=1)
        prev_week_key = prev_monday.strftime("%Y-%m-%d")
        prev_sunday_str = prev_sunday.strftime("%Y-%m-%d")

        week_start_eq = await self.db.get_week_start_equity(prev_week_key)
        trades = await self.db.get_trades_since(prev_week_key)
        # Filter to previous week only (up to Sunday)
        trades = [t for t in trades if t["date"] <= prev_sunday_str]

        if not trades:
            await channel.send(
                f"**Weekly Summary** ({prev_week_key} → {prev_sunday_str})\n"
                f"No trades last week."
            )
            return

        total_pnl = sum(t["pnl"] for t in trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0.0
        equity_now = await self.db.get_equity()
        bankroll_change = equity_now - week_start_eq

        # Best strategy by total P&L
        strategy_pnl: dict[str, float] = {}
        for t in trades:
            strategy_pnl[t["strategy"]] = strategy_pnl.get(t["strategy"], 0.0) + t["pnl"]
        best_strategy = max(strategy_pnl, key=strategy_pnl.get) if strategy_pnl else "N/A"

        # Day trades used last week
        day_trades_used = sum(1 for t in trades if t.get("is_day_trade"))

        sign = "+" if bankroll_change >= 0 else ""
        await channel.send(
            f"**Weekly Summary** ({prev_week_key} → {prev_sunday_str})\n"
            f"Trades taken: {len(trades)} ({len(wins)}W / {len(losses)}L) — "
            f"Win rate: {win_rate:.0f}%\n"
            f"Weekly P&L: {'+' if total_pnl >= 0 else ''}${total_pnl:.2f}\n"
            f"Bankroll change: {sign}${bankroll_change:.2f} "
            f"(${week_start_eq:.2f} → ${equity_now:.2f})\n"
            f"Best strategy: {best_strategy}\n"
            f"Day trades used: {day_trades_used}"
        )


# ------------------------------------------------------------------ #
#  Synchronous scan worker (runs in asyncio.to_thread)               #
# ------------------------------------------------------------------ #

def _run_scan(equity: float, today_str: str,
              protection: dict, pdt_remaining: int) -> list[dict]:
    """
    Pure synchronous scan.  Must NOT create event loops or call async methods.
    All async data (equity, pdt_remaining, protection) is passed in as arguments.
    """
    logger.info("_run_scan: building universe…")
    tickers = build_daily_universe()
    if not tickers:
        logger.warning("_run_scan: empty universe")
        return []

    # Fetch sector scores first (fast, only ~11 ETFs)
    sector_scores = fetch_sector_relative_strength()

    # Build ticker→sector mapping from universe seed
    from universe import load_seed_universe
    import json, os
    seed_file = os.path.join(os.path.dirname(__file__), "seed_universe.json")
    try:
        with open(seed_file) as f:
            seed_data = json.load(f)
        # seed_universe.json may be a list of tickers or list of {ticker, sector} dicts
        ticker_sector: dict[str, str] = {}
        if seed_data and isinstance(seed_data[0], dict):
            for item in seed_data:
                ticker_sector[item.get("ticker", "")] = item.get("sector", "")
    except Exception:
        ticker_sector = {}

    # Fetch OHLCV in one batch
    logger.info("_run_scan: fetching OHLCV for %d tickers…", len(tickers))
    ohlcv = fetch_daily_ohlcv(tickers, period="3mo")

    # Fetch pre-market data
    logger.info("_run_scan: fetching pre-market data…")
    premarket = fetch_premarket_data(tickers)

    budget = calc_debit_budget(equity)

    raw_setups: list[dict] = []

    for ticker in tickers:
        df = ohlcv.get(ticker)
        if df is None or df.empty:
            continue

        # Earnings days until next report
        try:
            earnings_date = get_earnings_date(ticker)
            if earnings_date is not None:
                if hasattr(earnings_date, "date"):
                    ed = earnings_date.date()
                else:
                    from datetime import date
                    ed = earnings_date
                from datetime import date as date_cls
                earnings_days = (ed - date_cls.today()).days
            else:
                earnings_days = None
        except Exception:
            earnings_days = None

        sector = ticker_sector.get(ticker)

        # Swing strategy
        swing = score_swing(
            df=df,
            ticker=ticker,
            sector_scores=sector_scores,
            earnings_days=earnings_days,
            ticker_sector=sector,
        )
        if swing:
            raw_setups.append(swing)

        # Gap strategy
        pre = premarket.get(ticker)
        gap = score_gap(
            df=df,
            ticker=ticker,
            premarket=pre,
            pdt_remaining=pdt_remaining,
        )
        if gap:
            raw_setups.append(gap)

    if not raw_setups:
        return []

    # Sort by score descending, take top 15 for options chain lookup
    raw_setups.sort(key=lambda s: s["score"], reverse=True)
    top_setups = raw_setups[:15]

    logger.info("_run_scan: fetching options chains for %d top setups…", len(top_setups))
    final_setups: list[dict] = []

    for setup in top_setups:
        ticker = setup["ticker"]
        spot = setup["entry"]
        direction = setup["direction"]

        chain = fetch_options_chain(ticker, max_dte=14)
        contract = pick_contract(chain, spot_price=spot, direction=direction, max_debit=budget)

        if contract is None:
            # Skip setups with no valid contract — don't post noise
            continue

        setup["contract"] = contract
        final_setups.append(setup)

        if len(final_setups) >= 9:
            break

    logger.info("_run_scan: returning %d final setups", len(final_setups))
    return final_setups


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

def run_bot():
    logging.basicConfig(level=logging.INFO)
    bot = ScannerBot()
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run_bot()
