import pytest
from datetime import datetime, date

pytest_plugins = ['pytest_asyncio']


@pytest.mark.asyncio
async def test_init_creates_tables(tmp_db):
    from state import StateDB
    db = StateDB(tmp_db)
    await db.init()
    equity = await db.get_equity()
    assert equity == 250.0
    await db.close()


@pytest.mark.asyncio
async def test_update_equity(tmp_db):
    from state import StateDB
    db = StateDB(tmp_db)
    await db.init()
    await db.update_equity(300.0)
    assert await db.get_equity() == 300.0
    await db.close()


@pytest.mark.asyncio
async def test_log_trade_and_history(tmp_db):
    from state import StateDB
    db = StateDB(tmp_db)
    await db.init()
    await db.log_trade(
        date="2026-04-04",
        setup_number=1,
        ticker="SOFI",
        strategy="Breakout",
        direction="CALL",
        is_day_trade=False,
        pnl=25.0,
    )
    trades = await db.get_trades_since("2026-04-01")
    assert len(trades) == 1
    assert trades[0]["ticker"] == "SOFI"
    assert trades[0]["pnl"] == 25.0
    await db.close()


@pytest.mark.asyncio
async def test_pdt_tracking(tmp_db):
    from state import StateDB
    db = StateDB(tmp_db)
    await db.init()
    await db.record_day_trade("2026-04-04")
    await db.record_day_trade("2026-04-04")
    count = await db.get_day_trades_in_window("2026-04-04")
    assert count == 2
    remaining = await db.get_remaining_day_trades("2026-04-04")
    assert remaining == 1  # 3 - 2
    await db.close()


@pytest.mark.asyncio
async def test_weekly_stats(tmp_db):
    from state import StateDB
    db = StateDB(tmp_db)
    await db.init()
    await db.update_equity(250.0)
    await db.save_week_start_equity("2026-W14", 250.0)
    start = await db.get_week_start_equity("2026-W14")
    assert start == 250.0
    await db.close()


@pytest.mark.asyncio
async def test_open_positions(tmp_db):
    from state import StateDB
    db = StateDB(tmp_db)
    await db.init()
    await db.open_position(
        scan_date="2026-04-04",
        setup_number=1,
        ticker="PLTR",
        strategy="Pullback",
        direction="CALL",
        is_day_trade=False,
    )
    positions = await db.get_open_positions()
    assert len(positions) == 1
    assert positions[0]["ticker"] == "PLTR"
    await db.close_position(positions[0]["id"], pnl=15.0)
    positions = await db.get_open_positions()
    assert len(positions) == 0
    await db.close()
