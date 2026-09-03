"""Entry differential helpers for CAL-2 (research)."""

from __future__ import annotations

from typing import Literal, Tuple

DiffMode = Literal["far_minus_near", "next_minus_near"]


def premium_differential(
    *,
    near: float,
    nxt: float,
    far: float,
    mode: DiffMode = "far_minus_near",
) -> float:
    """
    far_minus_near: monthly vs near weekly debit (typically ~200–300 pts on NIFTY ATM).
    next_minus_near: weekly-roll gap (closer to classic 70–80 pts scale).
    """
    n = float(near)
    x = float(nxt)
    f = float(far)
    if mode == "next_minus_near":
        return x - n
    return f - n


def parse_diff_mode(raw: str) -> DiffMode:
    key = str(raw or "far_minus_near").strip().lower().replace("-", "_")
    if key in ("next_minus_near", "weekly_roll", "next_near"):
        return "next_minus_near"
    return "far_minus_near"


def band_for_mode(mode: DiffMode) -> Tuple[float, float, float]:
    """
    Return (pts_band_lo, pts_band_hi, exit_diff_below) research defaults.
    CAL-0 v1 claimed [70,80] on far−near; 2026-08-25 evidence amended far−near to [200,300].
    next−near keeps [70,80] as Chirag-scale weekly-roll hypothesis.
    """
    if mode == "next_minus_near":
        return 70.0, 80.0, 40.0
    return 200.0, 300.0, 150.0
