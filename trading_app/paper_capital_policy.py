"""
Paper sandbox capital allocation (Angel MIS-style, no leverage).

Ledger: ₹10,00,000. Deployable for intraday paper: ₹5,00,000 across max 5 scrips
(₹1,00,000 notional each). Quantity = floor(₹1,00,000 / LTP).
"""

from __future__ import annotations

from typing import Tuple

PAPER_LEDGER_CAPITAL = 1_000_000.0
PAPER_DEPLOYABLE_CAPITAL = 500_000.0
PAPER_MAX_OPEN_SCRIPS = 5
PAPER_PER_SCRIP_CAPITAL = PAPER_DEPLOYABLE_CAPITAL / PAPER_MAX_OPEN_SCRIPS  # ₹1,00,000


def qty_for_scrip_allocation(ltp: float) -> int:
    """Shares to buy/sell: floor(₹1,00,000 / LTP), minimum 1."""
    try:
        price = float(ltp)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return 1
    return max(1, int(PAPER_PER_SCRIP_CAPITAL // price))


def deployable_remaining(utilized_margin: float) -> float:
    return max(0.0, float(PAPER_DEPLOYABLE_CAPITAL) - float(utilized_margin or 0.0))


def can_open_paper_position(
    open_count: int,
    utilized_margin: float,
    new_notional: float,
) -> Tuple[bool, str]:
    """Gate new paper fills against deployable + per-scrip caps."""
    if int(open_count) >= PAPER_MAX_OPEN_SCRIPS:
        return False, (
            f"Max {PAPER_MAX_OPEN_SCRIPS} open paper positions reached "
            f"(₹{PAPER_PER_SCRIP_CAPITAL:,.0f} per scrip)."
        )
    try:
        notional = float(new_notional)
    except (TypeError, ValueError):
        notional = 0.0
    if notional > float(PAPER_PER_SCRIP_CAPITAL) + 0.01:
        return False, (
            f"Per-scrip cap is ₹{PAPER_PER_SCRIP_CAPITAL:,.0f} "
            f"(qty = ₹{PAPER_PER_SCRIP_CAPITAL:,.0f} / LTP, no margin)."
        )
    if float(utilized_margin or 0.0) + notional > float(PAPER_DEPLOYABLE_CAPITAL) + 0.01:
        remaining = deployable_remaining(utilized_margin)
        return False, (
            f"Deployable paper capital exceeded. "
            f"₹{remaining:,.0f} remaining of ₹{PAPER_DEPLOYABLE_CAPITAL:,.0f} deployable."
        )
    return True, "OK"
