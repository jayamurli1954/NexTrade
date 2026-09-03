"""FO multi-leg cost model for calendar 3:1:1 research (approximate)."""

from __future__ import annotations

from dataclasses import dataclass

from research.calendar_spread.definition import CAL_PARAMS, CalendarSpreadParams


@dataclass(frozen=True)
class CalendarRoundTripCost:
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

    def to_dict(self) -> dict:
        return {
            "brokerage": round(self.brokerage, 2),
            "exchange_txn": round(self.exchange_txn, 2),
            "stt": round(self.stt, 2),
            "gst": round(self.gst, 2),
            "sebi": round(self.sebi, 2),
            "stamp": round(self.stamp, 2),
            "slippage": round(self.slippage, 2),
            "total": round(self.total, 2),
        }


def estimate_calendar_311_round_trip_cost(
    *,
    entry_near: float,
    entry_next: float,
    entry_far: float,
    exit_near: float,
    exit_next: float,
    exit_far: float,
    lot_size: int,
    params: CalendarSpreadParams = CAL_PARAMS,
) -> CalendarRoundTripCost:
    """
    3:1:1 = buy 3 far + sell 1 near + sell 1 next; unwind reverses.
    Orders: 3 legs × 2 sides = 6 orders (each lot is one order for brokerage).
    Far uses 3 lots → count as 3 entry buys + 3 exit sells = 6 far orders,
    near/next: 1 sell + 1 buy each → 4, total 10 order charges.
    """
    far_lots = int(params.far_lots)
    near_lots = int(params.near_lots)
    next_lots = int(params.next_lots)
    # brokerage per lot-side
    orders = 2 * (far_lots + near_lots + next_lots)
    brokerage = orders * float(params.brokerage_per_order)
    gst = brokerage * (float(params.gst_on_brokerage_pct) / 100.0)

    qty_near = near_lots * int(lot_size)
    qty_next = next_lots * int(lot_size)
    qty_far = far_lots * int(lot_size)

    # Sell notional (STT): entry shorts near+next + exit sell of long far
    sell_notional = (
        entry_near * qty_near
        + entry_next * qty_next
        + exit_far * qty_far
    )
    # Buy notional (stamp): entry long far + exit covers near+next
    buy_notional = (
        entry_far * qty_far
        + exit_near * qty_near
        + exit_next * qty_next
    )
    turnover = sell_notional + buy_notional

    exchange_txn = turnover * (float(params.exchange_txn_bps) / 10_000.0)
    stt = sell_notional * (float(params.stt_sell_bps) / 10_000.0)
    sebi = turnover * (float(params.sebi_bps) / 10_000.0)
    stamp = buy_notional * (float(params.stamp_duty_bps) / 10_000.0)

    slip_pct = float(params.slippage_premium_pct) / 100.0
    slippage = turnover * slip_pct

    return CalendarRoundTripCost(
        brokerage=brokerage,
        exchange_txn=exchange_txn,
        stt=stt,
        gst=gst,
        sebi=sebi,
        stamp=stamp,
        slippage=slippage,
    )


def calendar_pnl_pts(
    *,
    entry_near: float,
    entry_next: float,
    entry_far: float,
    mark_near: float,
    mark_next: float,
    mark_far: float,
    far_lots: int = 3,
    near_lots: int = 1,
    next_lots: int = 1,
) -> float:
    """Lot-equivalent pts: long far + short near + short next."""
    return (
        float(far_lots) * (float(mark_far) - float(entry_far))
        + float(near_lots) * (float(entry_near) - float(mark_near))
        + float(next_lots) * (float(entry_next) - float(mark_next))
    )
