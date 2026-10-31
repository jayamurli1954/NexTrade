"""ORB–VWAP equity research strategy definition (research-only, not live)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class OrbParams:
    """Long-only Opening Range Breakout with VWAP / volume / Nifty filter."""

    strategy_id: str = "ORB_VWAP_EQ"
    version: str = "1.0.0"
    timeframe: str = "5m"
    side: str = "LONG_ONLY"

    # Session (IST wall-clock on bar timestamps)
    or_start_hm: Tuple[int, int] = (9, 15)
    or_end_hm: Tuple[int, int] = (9, 30)  # exclusive of 09:30 bar as entry
    entry_start_hm: Tuple[int, int] = (9, 30)
    entry_end_hm: Tuple[int, int] = (14, 0)  # no late-session entries
    flat_hm: Tuple[int, int] = (15, 15)

    # Entry filters
    volume_sma_bars: int = 20
    volume_mult: float = 1.5
    max_or_width_pct: float = 1.5  # skip if OR range / open > this %
    max_breakout_range_pct: float = 1.2  # skip overextended breakout candle
    require_nifty_above_vwap: bool = True

    # Risk
    risk_pct_capital: float = 0.5
    reward_risk: float = 1.5
    max_trades_per_day: int = 3
    max_consecutive_losses: int = 2
    daily_loss_limit_pct: float = 1.0
    initial_capital: float = 200_000.0

    # Costs (INR equity intraday approx — research, not invoice)
    brokerage_per_order: float = 20.0
    slippage_bps_per_side: float = 5.0
    stt_sell_bps: float = 2.5  # ~0.025% sell side intraday proxy
    exchange_txn_bps: float = 0.297
    sebi_bps: float = 0.1
    stamp_buy_bps: float = 1.5
    gst_on_brokerage_pct: float = 18.0

    extras: Dict[str, Any] = field(default_factory=dict)


ORB_PARAMS = OrbParams()
