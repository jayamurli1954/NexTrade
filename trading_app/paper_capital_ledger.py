"""
Paper ledger display: ₹10L base (plus manual ±₹10k) + today's net after charges.

Overall / all-time P&L is journal-only and is never mixed into displayed capital.
V2 charges only (no assumed slippage). Day-halt still uses gross P&L.
"""

from __future__ import annotations

from typing import Any, Dict

from trading_app.broker_charges import estimate_equity_intraday_round_trip


def net_after_charges(
    *,
    gross_pnl: float,
    entry: float,
    exit_px: float,
    qty: int,
) -> Dict[str, Any]:
    """Gross − Angel equity-intraday charges (brokerage, GST, STT, exchange, SEBI, stamp)."""
    breakdown = estimate_equity_intraday_round_trip(
        entry=entry,
        exit_px=exit_px,
        qty=qty,
        include_slippage=False,
    )
    charges = round(float(breakdown.total), 2)
    gross = round(float(gross_pnl or 0.0), 2)
    return {
        "gross_pnl": gross,
        "est_charges": charges,
        "net_pnl": round(gross - charges, 2),
        "charges_breakdown": breakdown.to_dict(),
    }


def displayed_paper_capital(
    ledger_base: float,
    todays_net_pnl: float,
    unrealized_pnl: float = 0.0,
) -> float:
    """Capital shown on the dashboard: base + today's realized net + live open P&L (not overall)."""
    return round(
        max(
            0.0,
            float(ledger_base or 0.0)
            + float(todays_net_pnl or 0.0)
            + float(unrealized_pnl or 0.0),
        ),
        2,
    )


def infer_ledger_base_from_legacy_total(stored_total: float, step: float = 10_000.0) -> float:
    """
    Older saves stored display capital (base + today's net) as total_capital.
    Snap to nearest ₹10,000 so today's P&L is not baked into the ledger base.
    """
    try:
        value = float(stored_total)
    except (TypeError, ValueError):
        return 1_000_000.0
    if step <= 0:
        return round(max(0.0, value), 2)
    return max(0.0, round(round(value / step) * step, 2))


def annotate_closed_trade_charges(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp gross / charges / net on a closed trade. Does not change ledger base."""
    row = trade
    if str(row.get("status") or "").upper() == "OPEN":
        return row
    info = net_after_charges(
        gross_pnl=float(row.get("pnl") or 0.0),
        entry=float(row.get("entry_price") or 0.0),
        exit_px=float(row.get("exit_price") or 0.0),
        qty=int(row.get("quantity") or 0),
    )
    row.update(info)
    return row
