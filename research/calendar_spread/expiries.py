"""Near / next-weekly / far-monthly expiry selection from the options store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import pandas as pd

from research.calendar_spread.definition import CalendarSpreadParams


@dataclass(frozen=True)
class ExpiryTriplet:
    near: pd.Timestamp
    next_weekly: pd.Timestamp
    far: pd.Timestamp
    near_dte: int
    next_dte: int
    far_dte: int


def _dte(asof: pd.Timestamp, expiry: pd.Timestamp) -> int:
    a = pd.Timestamp(asof).normalize()
    e = pd.Timestamp(expiry).normalize()
    return int((e - a).days)


def expiries_on_or_after(store_df: pd.DataFrame, *, symbol: str, asof: pd.Timestamp) -> List[pd.Timestamp]:
    """Unique expiries that still have bars on/before asof and expiry ≥ asof."""
    if store_df is None or store_df.empty:
        return []
    day = pd.Timestamp(asof).normalize()
    sub = store_df[
        (store_df["symbol"] == str(symbol).upper())
        & (store_df["date"] <= day)
        & (store_df["expiry"] >= day)
    ]
    if sub.empty:
        return []
    return sorted(pd.Timestamp(x).normalize() for x in sub["expiry"].drop_duplicates().tolist())


def pick_expiry_triplet(
    expiries: Sequence[pd.Timestamp],
    *,
    asof: pd.Timestamp,
    params: CalendarSpreadParams,
) -> Optional[ExpiryTriplet]:
    """
    near: soonest with 1..near_max_dte
    next: next expiry with next_min_dte..next_max_dte and > near
    far: earliest with far_min_dte..far_max_dte and > next
    """
    day = pd.Timestamp(asof).normalize()
    scored = [(_dte(day, e), pd.Timestamp(e).normalize()) for e in expiries]
    scored = [(d, e) for d, e in scored if d >= 1]
    if not scored:
        return None

    near_cands = [(d, e) for d, e in scored if d <= int(params.near_max_dte)]
    if not near_cands:
        return None
    near_dte, near = min(near_cands, key=lambda x: x[0])

    next_cands = [
        (d, e)
        for d, e in scored
        if e > near and int(params.next_min_dte) <= d <= int(params.next_max_dte)
    ]
    if not next_cands:
        return None
    next_dte, nxt = min(next_cands, key=lambda x: x[0])

    far_cands = [
        (d, e)
        for d, e in scored
        if e > nxt and int(params.far_min_dte) <= d <= int(params.far_max_dte)
    ]
    if not far_cands:
        return None
    far_dte, far = min(far_cands, key=lambda x: x[0])

    return ExpiryTriplet(
        near=near,
        next_weekly=nxt,
        far=far,
        near_dte=near_dte,
        next_dte=next_dte,
        far_dte=far_dte,
    )
