"""NSE F&O round-trip cost model for ARASS research (approximate, not broker invoice)."""

from __future__ import annotations

from dataclasses import dataclass

from research.arass.definition import ArassParams


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


def estimate_straddle_round_trip_cost(
    *,
    entry_ce: float,
    entry_pe: float,
    exit_ce: float,
    exit_pe: float,
    qty: int,
    params: ArassParams,
) -> RoundTripCost:
    """
    Short straddle: sell CE+PE at entry, buy back at exit.
    4 executed orders (2 entry sells + 2 exit buys).
    """
    orders = 4
    brokerage = orders * float(params.brokerage_per_order)
    gst = brokerage * (float(params.gst_on_brokerage_pct) / 100.0)

    entry_premium_notional = (entry_ce + entry_pe) * qty
    exit_premium_notional = (exit_ce + exit_pe) * qty
    turnover = entry_premium_notional + exit_premium_notional

    exchange_txn = turnover * (float(params.exchange_txn_bps) / 10_000.0)
    # STT typically on sell side of options (premium); apply to both entry sells.
    stt = entry_premium_notional * (float(params.stt_sell_bps) / 10_000.0)
    sebi = turnover * (float(params.sebi_bps) / 10_000.0)
    # Stamp duty proxy on buy notional (exit cover)
    stamp = exit_premium_notional * (float(params.stamp_duty_bps) / 10_000.0)

    slip_pct = float(params.slippage_premium_pct) / 100.0
    # Adverse: sell lower / buy higher
    slippage = (entry_premium_notional + exit_premium_notional) * slip_pct

    return RoundTripCost(
        brokerage=brokerage,
        exchange_txn=exchange_txn,
        stt=stt,
        gst=gst,
        sebi=sebi,
        stamp=stamp,
        slippage=slippage,
    )
