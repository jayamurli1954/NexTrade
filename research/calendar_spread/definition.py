"""CAL-0 research defaults for NIFTY calendar / rollover spreads (amended 2026-08-25)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from research.calendar_spread.signals import DiffMode


@dataclass(frozen=True)
class CalendarSpreadParams:
    """Research defaults — not live/paper mandates."""

    version: str = "CAL-2-V1.1"
    symbol: str = "NIFTY"
    strike_step: float = 50.0
    zone_lookback: int = 20
    # Differential used for entry band / mean-revert exit
    diff_mode: DiffMode = "far_minus_near"
    # CAL-0 v1 claimed [70,80] on far−near; evidence (med≈245) → amended [200,300]
    pts_band_lo: float = 200.0
    pts_band_hi: float = 300.0
    # Skip if abs(open − prior_close) / prior_close ≥ this percent
    gap_skip_pct: float = 0.80
    # Exit when active differential mean-reverts below this
    exit_diff_below: float = 150.0
    # Stop when lot-equivalent calendar P&L ≤ this (pts)
    stop_pts_lot_equiv: float = -40.0
    # Structure 3:1:1
    far_lots: int = 3
    near_lots: int = 1
    next_lots: int = 1
    near_max_dte: int = 10
    next_min_dte: int = 8
    next_max_dte: int = 21
    far_min_dte: int = 28
    far_max_dte: int = 60
    zone_strike_offset: bool = True
    initial_capital: float = 1_000_000.0
    brokerage_per_order: float = 20.0
    gst_on_brokerage_pct: float = 18.0
    exchange_txn_bps: float = 3.5
    stt_sell_bps: float = 6.25
    sebi_bps: float = 0.1
    stamp_duty_bps: float = 0.03
    slippage_premium_pct: float = 0.0
    lot_default: int = 65
    max_concurrent: int = 1


CAL_PARAMS = CalendarSpreadParams()


def params_to_dict(params: CalendarSpreadParams = CAL_PARAMS) -> Dict[str, Any]:
    return asdict(params)
