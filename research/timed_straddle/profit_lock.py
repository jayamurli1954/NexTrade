"""
Position-level MTM profit lock (trailing profit), shared by the backtest engines and the paper lane.

Once MTM reaches ``trigger``, at least ``lock`` rupees are locked in. For every further ``step``
rupees of MTM above the trigger, the locked amount rises by ``increment``. If MTM later falls to or
below the locked amount, the whole position is closed. The lock never moves down.

Example (trigger 2000, lock 500, step 500, increment 250):
  MTM 1999 -> no lock; MTM 2000 -> lock 500; MTM 3100 -> lock 1000; MTM falls to 1000 -> exit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProfitLockRule:
    trigger: float
    lock: float
    step: float
    increment: float

    def __post_init__(self):
        if self.trigger <= 0 or self.lock < 0 or self.lock > self.trigger or self.step < 0 or self.increment < 0:
            raise ValueError(f"Invalid profit lock {self}: need trigger>0, 0<=lock<=trigger, step>=0, increment>=0")

    @classmethod
    def parse(cls, value) -> Optional["ProfitLockRule"]:
        """From 'trigger,lock,step,increment', a dict with those keys, or None."""
        if value in (None, "", False):
            return None
        if isinstance(value, ProfitLockRule):
            return value
        if isinstance(value, dict):
            return cls(float(value["trigger"]), float(value["lock"]),
                       float(value.get("step", 0.0)), float(value.get("increment", 0.0)))
        parts = [float(x) for x in str(value).split(",")]
        if len(parts) != 4:
            raise ValueError("profit lock must be 'trigger,lock,step,increment'")
        return cls(*parts)

    def locked_for(self, peak_mtm: float) -> Optional[float]:
        """Locked amount implied by the highest MTM reached so far (None = not active)."""
        if peak_mtm < self.trigger:
            return None
        raises = math.floor((peak_mtm - self.trigger) / self.step) if self.step > 0 else 0
        return min(self.lock + raises * self.increment, peak_mtm)


class ProfitLockTracker:
    """Per-position state: tracks peak MTM; ``should_exit(mtm)`` is True when MTM <= locked level."""

    def __init__(self, rule: Optional[ProfitLockRule], peak: float = float("-inf")):
        self.rule = rule
        self.peak = peak

    @property
    def locked(self) -> Optional[float]:
        return self.rule.locked_for(self.peak) if self.rule is not None else None

    def should_exit(self, mtm: float) -> bool:
        if self.rule is None:
            return False
        self.peak = max(self.peak, mtm)
        lk = self.locked
        return lk is not None and mtm <= lk


def mtm_exit_reason(params, mtm: float, tracker: "ProfitLockTracker") -> Optional[str]:
    """Position-level exit check shared by engines and paper strategies (max loss > profit lock > target)."""
    if params.max_loss_rupees is not None and mtm < -params.max_loss_rupees:
        return "max_loss"
    if tracker.should_exit(mtm):
        return "profit_lock"
    if params.target_rupees is not None and mtm > params.target_rupees:
        return "target"
    return None


def needs_mtm(params) -> bool:
    return (params.target_rupees is not None or params.max_loss_rupees is not None
            or getattr(params, "profit_lock", None) is not None)
