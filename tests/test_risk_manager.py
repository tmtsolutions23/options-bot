import pytest
from risk_manager import get_tier, calc_debit_budget, should_halt, check_loss_protection


def test_tier_250():
    tier = get_tier(250.0)
    assert tier["risk_pct"] == 0.04
    assert tier["max_concurrent"] == 2


def test_tier_800():
    tier = get_tier(800.0)
    assert tier["risk_pct"] == 0.03


def test_tier_2000():
    tier = get_tier(2000.0)
    assert tier["risk_pct"] == 0.025


def test_tier_5000():
    tier = get_tier(5000.0)
    assert tier["risk_pct"] == 0.02


def test_debit_budget_250():
    budget = calc_debit_budget(250.0)
    assert budget == 10.0


def test_debit_budget_500():
    budget = calc_debit_budget(500.0)
    assert budget == 15.0


def test_debit_budget_large():
    budget = calc_debit_budget(10000.0)
    assert budget == 120.0


def test_should_halt_weekly_drawdown():
    halted, reason = should_halt(
        equity=200.0, week_start_equity=250.0, consecutive_losses=0, daily_pnl=0.0
    )
    assert halted is True
    assert "drawdown" in reason.lower()


def test_should_halt_consecutive_losses():
    halted, reason = should_halt(
        equity=250.0, week_start_equity=250.0, consecutive_losses=3, daily_pnl=0.0
    )
    assert halted is True
    assert "consecutive" in reason.lower()


def test_should_not_halt_normal():
    halted, reason = should_halt(
        equity=260.0, week_start_equity=250.0, consecutive_losses=1, daily_pnl=5.0
    )
    assert halted is False


def test_loss_protection_daily_cap():
    result = check_loss_protection(equity=250.0, daily_pnl=-20.5)
    assert result["daily_cap_hit"] is True
    assert result["reduce_concurrent"] is True


def test_loss_protection_normal():
    result = check_loss_protection(equity=250.0, daily_pnl=-5.0)
    assert result["daily_cap_hit"] is False
