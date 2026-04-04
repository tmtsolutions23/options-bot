from config import (
    RISK_TIERS, WEEKLY_DRAWDOWN_HALT_PCT, CONSECUTIVE_LOSS_PAUSE,
)


def get_tier(equity: float) -> dict:
    for tier in RISK_TIERS:
        if equity < tier["equity_max"]:
            return tier
    return RISK_TIERS[-1]


def calc_debit_budget(equity: float) -> float:
    tier = get_tier(equity)
    suggested = equity * tier["risk_pct"]
    return round(max(tier["min_debit"], min(tier["max_debit"], suggested)), 2)


def should_halt(equity: float, week_start_equity: float,
                consecutive_losses: int, daily_pnl: float) -> tuple[bool, str]:
    if week_start_equity > 0:
        drawdown = (week_start_equity - equity) / week_start_equity
        if drawdown >= WEEKLY_DRAWDOWN_HALT_PCT:
            return True, (
                f"Weekly drawdown halt: bankroll dropped {drawdown:.1%} from "
                f"${week_start_equity:.2f} to ${equity:.2f}. Sit this week out."
            )
    if consecutive_losses >= CONSECUTIVE_LOSS_PAUSE:
        return True, (
            f"Consecutive loss cooldown: {consecutive_losses} losses in a row. "
            f"Taking a 1-day pause to reset."
        )
    return False, ""


def check_loss_protection(equity: float, daily_pnl: float) -> dict:
    tier = get_tier(equity)
    cap = equity * tier["daily_loss_cap_pct"]
    daily_cap_hit = daily_pnl <= -cap
    return {
        "daily_cap_hit": daily_cap_hit,
        "reduce_concurrent": daily_cap_hit,
        "daily_pnl": daily_pnl,
        "daily_cap": -cap,
    }
