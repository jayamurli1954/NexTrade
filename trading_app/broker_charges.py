"""
Broker charge estimates for paper journal / day-risk net projections.

Angel One equity intraday defaults — user may override in paper_day_risk_policy.json
to match their contract. Not fetched live from Angel API yet (broker-specific).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, field
from typing import Any, Dict, Optional


@dataclass
class AngelOneEquityIntradayCharges:
    """
    Published-style Angel One equity intraday charge template (research / paper).
    Verify against your Angel contract & tariff page before live use.
    """

    broker: str = "ANGEL_ONE"
    brokerage_per_order_inr: float = 20.0  # flat per executed order (typical retail)
    stt_sell_pct: float = 0.025  # STT on sell leg notional (%)
    exchange_txn_pct: float = 0.00345  # NSE equity intraday txn charge proxy (%)
    gst_on_brokerage_pct: float = 18.0
    sebi_turnover_pct: float = 0.0001
    stamp_duty_buy_pct: float = 0.003  # buy-side stamp proxy (%)
    slippage_pct: float = 0.05  # optional adverse slip on turnover (%)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "AngelOneEquityIntradayCharges":
        if not raw:
            return cls()
        fields_set = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in fields_set})


@dataclass(frozen=True)
class ChargeBreakdown:
    brokerage: float
    gst: float
    stt: float
    exchange: float
    sebi: float
    stamp: float
    slippage: float

    @property
    def total(self) -> float:
        return self.brokerage + self.gst + self.stt + self.exchange + self.sebi + self.stamp + self.slippage

    def to_dict(self) -> Dict[str, float]:
        return {
            "brokerage": round(self.brokerage, 2),
            "gst": round(self.gst, 2),
            "stt": round(self.stt, 2),
            "exchange": round(self.exchange, 2),
            "sebi": round(self.sebi, 2),
            "stamp": round(self.stamp, 2),
            "slippage": round(self.slippage, 2),
            "total": round(self.total, 2),
        }


def estimate_equity_intraday_round_trip(
    *,
    entry: float,
    exit_px: float,
    qty: int,
    model: Optional[AngelOneEquityIntradayCharges] = None,
    include_slippage: bool = True,
) -> ChargeBreakdown:
    """Buy + sell round trip (2 orders). Used for paper net P&L projection."""
    m = model or AngelOneEquityIntradayCharges()
    try:
        q = max(int(qty), 0)
        e = float(entry)
        x = float(exit_px)
    except (TypeError, ValueError):
        return ChargeBreakdown(0, 0, 0, 0, 0, 0, 0)
    if q <= 0 or e <= 0 or x <= 0:
        brokerage = float(m.brokerage_per_order_inr) * 2.0
        gst = brokerage * (float(m.gst_on_brokerage_pct) / 100.0)
        return ChargeBreakdown(brokerage, gst, 0, 0, 0, 0, 0)

    buy_notional = e * q
    sell_notional = x * q
    turnover = buy_notional + sell_notional
    brokerage = float(m.brokerage_per_order_inr) * 2.0
    exchange = turnover * (float(m.exchange_txn_pct) / 100.0)
    gst = (brokerage + exchange) * (float(m.gst_on_brokerage_pct) / 100.0)
    stt = sell_notional * (float(m.stt_sell_pct) / 100.0)
    sebi = turnover * (float(m.sebi_turnover_pct) / 100.0)
    stamp = buy_notional * (float(m.stamp_duty_buy_pct) / 100.0)
    slip = turnover * (float(m.slippage_pct) / 100.0) if include_slippage else 0.0
    return ChargeBreakdown(brokerage, gst, stt, exchange, sebi, stamp, slip)


def estimate_round_trip_total(
    *,
    entry: float,
    exit_px: float,
    qty: int,
    model: Optional[AngelOneEquityIntradayCharges] = None,
) -> float:
    return estimate_equity_intraday_round_trip(
        entry=entry, exit_px=exit_px, qty=qty, model=model
    ).total
