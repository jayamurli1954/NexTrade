"""Equity intraday round-trip cost model for ORB research (approximate)."""

from __future__ import annotations

from dataclasses import dataclass

from research.orb.definition import OrbParams


@dataclass(frozen=True)
class RoundTripCost:
    brokerage: float
    exchange_txn: float
    stt: float
    gst: float
    sebi: float
    stamp: float
    slippage: float

    @property
    def total(self) -> float:
        return (
            self.brokerage
            + self.exchange_txn
            + self.stt
            + self.gst
            + self.sebi
            + self.stamp
            + self.slippage
        )


def estimate_equity_round_trip_cost(
    *,
    entry: float,
    exit: float,
    qty: int,
    params: OrbParams,
) -> RoundTripCost:
    buy_notional = float(entry) * int(qty)
    sell_notional = float(exit) * int(qty)
    turnover = buy_notional + sell_notional

    brokerage = 2.0 * float(params.brokerage_per_order)
    gst = brokerage * (float(params.gst_on_brokerage_pct) / 100.0)
    exchange_txn = turnover * (float(params.exchange_txn_bps) / 10_000.0)
    sebi = turnover * (float(params.sebi_bps) / 10_000.0)
    stt = sell_notional * (float(params.stt_sell_bps) / 10_000.0)
    stamp = buy_notional * (float(params.stamp_buy_bps) / 10_000.0)
    slip = (buy_notional + sell_notional) * (float(params.slippage_bps_per_side) / 10_000.0)

    return RoundTripCost(
        brokerage=brokerage,
        exchange_txn=exchange_txn,
        stt=stt,
        gst=gst,
        sebi=sebi,
        stamp=stamp,
        slippage=slip,
    )
