"""Parameters for the timed intraday short straddle/strangle research backtest."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple

STRIKE_STEP = {"NIFTY": 50.0, "BANKNIFTY": 100.0}


@dataclass(frozen=True)
class TimedStraddleParams:
    """
    Timed short straddle/strangle with per-leg % stop-loss.

    Mirrors a common retail intraday options-selling template:
      * enter once at ``entry_hm`` on the current weekly expiry,
      * per-leg SL at entry x (1 + sl_pct/100),
      * optional "trail SL to cost" on the surviving leg after one SL hits,
      * optional protective wings (iron fly / condor),
      * position-level MTM target / max loss, hard time exit.
    """

    symbol: str = "NIFTY"
    entry_hm: Tuple[int, int] = (9, 20)
    exit_hm: Tuple[int, int] = (15, 15)

    points_from_atm: float = 0.0      # 0 = straddle; >0 = strangle (CE at ATM+pts, PE at ATM-pts)
    buy_wings: bool = False           # buy protective OTM options first
    wing_points: float = 500.0        # wing distance beyond the short strikes

    sl_pct: float = 25.0              # per-leg stop as % of leg entry premium
    trail_sl_to_cost: bool = True     # after one leg stops out, move other leg SL to its entry
    target_rupees: Optional[float] = None    # exit all when MTM > target (None = off)
    max_loss_rupees: Optional[float] = None  # exit all when MTM < -max_loss (None = off)

    lots: int = 1
    lot_size: Optional[int] = None    # None = symbol default below

    # Execution realism
    slippage_points: Optional[float] = None  # per leg per fill, adverse (None = symbol default)
    brokerage_per_order: float = 20.0

    # Pricing
    risk_free_rate: float = 0.065
    trade_weekdays: Tuple[int, ...] = (0, 1, 2, 3, 4)  # Mon=0..Fri=4
    max_dte: Optional[int] = None     # skip days with calendar DTE above this (None = all)

    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def strike_step(self) -> float:
        return STRIKE_STEP[self.symbol]

    @property
    def qty(self) -> int:
        size = self.lot_size if self.lot_size is not None else DEFAULT_LOT_SIZE[self.symbol]
        return int(self.lots * size)

    @property
    def slip(self) -> float:
        if self.slippage_points is not None:
            return float(self.slippage_points)
        return DEFAULT_SLIPPAGE_POINTS[self.symbol]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["qty"] = self.qty
        d["slip"] = self.slip
        return d


# Current (2026) lot sizes. Results are reported per this fixed size so years are comparable;
# historical lot-size changes are deliberately not replayed.
DEFAULT_LOT_SIZE = {"NIFTY": 65, "BANKNIFTY": 30}

# Adverse fill per leg per order, in index points of premium. ATM weekly Nifty spreads are
# ~0.05-0.5 pts but SL-limit fills in fast markets are worse; 0.5/1.5 is a middle assumption.
DEFAULT_SLIPPAGE_POINTS = {"NIFTY": 0.5, "BANKNIFTY": 1.5}
