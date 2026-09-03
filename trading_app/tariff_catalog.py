"""
Broker-agnostic Indian cash / F&O tariff catalog.

Preview / research authority only — does not replace trading_app.broker_charges
(Angel paper ledger defaults stay frozen). Brokerage is a named profile;
statutory rows are shared.

Source: Arrow Trade pricing (https://arrow.trade/pricing) retrieved 2026-08-22,
which already uses STT w.e.f. 1 Apr 2026. NSE txn / stamp / SEBI / IPFT / GST
are statutory and apply at every broker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


CATALOG_ID = "NEXTRADE_TARIFF_CATALOG_V1"
RATE_EFFECTIVE = "2026-04-01"
SOURCE = "arrow.trade/pricing (retrieved 2026-08-22); STT w.e.f. 2026-04-01"
AUTHORITY = "PREVIEW_ONLY"

GST_PCT = 18.0
SEBI_TURNOVER_PCT = 0.0001  # 0.0001% = ₹10 / crore
IPFT_NSE_PCT = 0.0000001  # ₹0.01 / crore


class Segment(str, Enum):
    EQUITY_DELIVERY = "EQUITY_DELIVERY"
    EQUITY_INTRADAY = "EQUITY_INTRADAY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


def _r2(value: float) -> float:
    return round(float(value) + 0.0, 2)


@dataclass(frozen=True)
class BrokerageRule:
    """Per-executed-order brokerage.

    If flat_inr == 0 and not use_min_flat_or_pct → free.
    If use_min_flat_or_pct → min(flat_inr, pct% of order notional).
    Else → flat_inr.
    """

    flat_inr: float = 20.0
    pct: float = 0.03
    use_min_flat_or_pct: bool = False


@dataclass(frozen=True)
class BrokerageProfile:
    profile_id: str
    label: str
    equity_delivery: BrokerageRule
    equity_intraday: BrokerageRule
    futures: BrokerageRule
    options: BrokerageRule

    def rule_for(self, segment: Segment) -> BrokerageRule:
        return {
            Segment.EQUITY_DELIVERY: self.equity_delivery,
            Segment.EQUITY_INTRADAY: self.equity_intraday,
            Segment.FUTURES: self.futures,
            Segment.OPTIONS: self.options,
        }[segment]


# Arrow: delivery free; MIS/FUT min(₹20, 0.03%); options ₹20 flat.
PROFILE_ARROW = BrokerageProfile(
    profile_id="ARROW",
    label="Arrow Trade (₹20 / 0.03% MIS·FUT, ₹20 options, ₹0 delivery)",
    equity_delivery=BrokerageRule(flat_inr=0.0, pct=0.0, use_min_flat_or_pct=False),
    equity_intraday=BrokerageRule(flat_inr=20.0, pct=0.03, use_min_flat_or_pct=True),
    futures=BrokerageRule(flat_inr=20.0, pct=0.03, use_min_flat_or_pct=True),
    options=BrokerageRule(flat_inr=20.0, pct=0.0, use_min_flat_or_pct=False),
)

# Matches NexTrade paper ledger today: always ₹20 / executed order.
PROFILE_FLAT20 = BrokerageProfile(
    profile_id="FLAT20",
    label="Flat ₹20 / executed order (Angel-style retail)",
    equity_delivery=BrokerageRule(flat_inr=20.0, pct=0.0, use_min_flat_or_pct=False),
    equity_intraday=BrokerageRule(flat_inr=20.0, pct=0.0, use_min_flat_or_pct=False),
    futures=BrokerageRule(flat_inr=20.0, pct=0.0, use_min_flat_or_pct=False),
    options=BrokerageRule(flat_inr=20.0, pct=0.0, use_min_flat_or_pct=False),
)

PROFILES: Dict[str, BrokerageProfile] = {
    PROFILE_ARROW.profile_id: PROFILE_ARROW,
    PROFILE_FLAT20.profile_id: PROFILE_FLAT20,
}

DEFAULT_PROFILE_ID = PROFILE_ARROW.profile_id


@dataclass(frozen=True)
class StatutoryRates:
    """Percent figures are percent-of-notional (0.025 → 0.025%)."""

    stt_delivery_pct: float = 0.1  # buy and sell
    stt_intraday_sell_pct: float = 0.025
    stt_futures_sell_pct: float = 0.05
    stt_options_sell_pct: float = 0.15  # on premium
    stamp_delivery_buy_pct: float = 0.015
    stamp_intraday_buy_pct: float = 0.003
    stamp_futures_buy_pct: float = 0.002
    stamp_options_buy_pct: float = 0.003
    nse_equity_txn_pct: float = 0.0030699
    nse_futures_txn_pct: float = 0.0018299
    nse_options_txn_pct: float = 0.0355299  # on premium
    sebi_turnover_pct: float = SEBI_TURNOVER_PCT
    ipft_nse_pct: float = IPFT_NSE_PCT
    gst_pct: float = GST_PCT


DEFAULT_RATES = StatutoryRates()
DEFAULT_SLIPPAGE_PCT = 0.05  # V3 scenario only — not a tariff line


@dataclass
class LegBreakdown:
    side: str
    notional: float
    brokerage: float
    stt: float
    stamp: float
    exchange: float
    sebi: float
    ipft: float
    gst: float

    @property
    def total(self) -> float:
        return _r2(
            self.brokerage
            + self.stt
            + self.stamp
            + self.exchange
            + self.sebi
            + self.ipft
            + self.gst
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "notional": _r2(self.notional),
            "brokerage": self.brokerage,
            "stt": self.stt,
            "stamp": self.stamp,
            "exchange": self.exchange,
            "sebi": self.sebi,
            "ipft": self.ipft,
            "gst": self.gst,
            "total": self.total,
        }


@dataclass
class ChargePreview:
    authority: str = AUTHORITY
    catalog_id: str = CATALOG_ID
    rate_effective: str = RATE_EFFECTIVE
    source: str = SOURCE
    profile_id: str = DEFAULT_PROFILE_ID
    segment: str = Segment.EQUITY_INTRADAY.value
    direction: str = "BUY"
    qty: int = 0
    entry: float = 0.0
    exit_px: float = 0.0
    buy_notional: float = 0.0
    sell_notional: float = 0.0
    turnover: float = 0.0
    legs: List[LegBreakdown] = field(default_factory=list)
    brokerage: float = 0.0
    stt: float = 0.0
    stamp: float = 0.0
    exchange: float = 0.0
    sebi: float = 0.0
    ipft: float = 0.0
    gst: float = 0.0
    v2_charges: float = 0.0
    v3_slippage: float = 0.0
    v3_charges: float = 0.0
    include_v3: bool = False
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authority": self.authority,
            "catalog_id": self.catalog_id,
            "rate_effective": self.rate_effective,
            "source": self.source,
            "profile_id": self.profile_id,
            "segment": self.segment,
            "direction": self.direction,
            "qty": int(self.qty),
            "entry": _r2(self.entry),
            "exit_px": _r2(self.exit_px),
            "buy_notional": _r2(self.buy_notional),
            "sell_notional": _r2(self.sell_notional),
            "turnover": _r2(self.turnover),
            "legs": [leg.to_dict() for leg in self.legs],
            "brokerage": self.brokerage,
            "stt": self.stt,
            "stamp": self.stamp,
            "exchange": self.exchange,
            "sebi": self.sebi,
            "ipft": self.ipft,
            "gst": self.gst,
            "v2_charges": self.v2_charges,
            "v3_slippage": self.v3_slippage,
            "v3_charges": self.v3_charges,
            "include_v3": bool(self.include_v3),
            "slippage_pct": float(self.slippage_pct),
            "notes": list(self.notes),
        }


def resolve_profile(profile_id: Optional[str]) -> BrokerageProfile:
    key = str(profile_id or DEFAULT_PROFILE_ID).strip().upper()
    if key not in PROFILES:
        raise ValueError(f"Unknown brokerage profile: {profile_id}")
    return PROFILES[key]


def resolve_segment(raw: Optional[str], trading_style: str = "") -> Segment:
    text = str(raw or "").strip().upper().replace(" ", "_")
    try:
        return Segment(text)
    except ValueError:
        pass
    aliases = {
        "MIS": Segment.EQUITY_INTRADAY,
        "INTRADAY": Segment.EQUITY_INTRADAY,
        "CNC": Segment.EQUITY_DELIVERY,
        "DELIVERY": Segment.EQUITY_DELIVERY,
        "NRML": Segment.FUTURES,
        "FUT": Segment.FUTURES,
        "OPT": Segment.OPTIONS,
        "OPTION": Segment.OPTIONS,
    }
    if text in aliases:
        return aliases[text]
    style = str(trading_style or "").strip().upper()
    if "OPTION" in style:
        return Segment.OPTIONS
    if "FUT" in style:
        return Segment.FUTURES
    return Segment.EQUITY_INTRADAY


def brokerage_for_order(rule: BrokerageRule, notional: float) -> float:
    n = max(float(notional), 0.0)
    if rule.use_min_flat_or_pct:
        pct_amt = n * (float(rule.pct) / 100.0)
        return _r2(min(float(rule.flat_inr), pct_amt))
    return _r2(float(rule.flat_inr))


def _txn_pct(segment: Segment, rates: StatutoryRates) -> float:
    if segment in (Segment.EQUITY_DELIVERY, Segment.EQUITY_INTRADAY):
        return rates.nse_equity_txn_pct
    if segment == Segment.FUTURES:
        return rates.nse_futures_txn_pct
    return rates.nse_options_txn_pct


def _stt_pct(segment: Segment, side: Side, rates: StatutoryRates) -> float:
    if segment == Segment.EQUITY_DELIVERY:
        return rates.stt_delivery_pct
    if side != Side.SELL:
        return 0.0
    if segment == Segment.EQUITY_INTRADAY:
        return rates.stt_intraday_sell_pct
    if segment == Segment.FUTURES:
        return rates.stt_futures_sell_pct
    return rates.stt_options_sell_pct


def _stamp_pct(segment: Segment, side: Side, rates: StatutoryRates) -> float:
    if side != Side.BUY:
        return 0.0
    if segment == Segment.EQUITY_DELIVERY:
        return rates.stamp_delivery_buy_pct
    if segment == Segment.EQUITY_INTRADAY:
        return rates.stamp_intraday_buy_pct
    if segment == Segment.FUTURES:
        return rates.stamp_futures_buy_pct
    return rates.stamp_options_buy_pct


def estimate_leg(
    *,
    segment: Segment,
    side: Side,
    notional: float,
    profile: BrokerageProfile,
    rates: StatutoryRates = DEFAULT_RATES,
) -> LegBreakdown:
    n = max(float(notional), 0.0)
    brokerage = brokerage_for_order(profile.rule_for(segment), n)
    stt = _r2(n * (_stt_pct(segment, side, rates) / 100.0))
    stamp = _r2(n * (_stamp_pct(segment, side, rates) / 100.0))
    exchange = _r2(n * (_txn_pct(segment, rates) / 100.0))
    sebi = _r2(n * (rates.sebi_turnover_pct / 100.0))
    ipft = _r2(n * (rates.ipft_nse_pct / 100.0))
    gst = _r2((brokerage + sebi + exchange) * (rates.gst_pct / 100.0))
    return LegBreakdown(
        side=side.value,
        notional=_r2(n),
        brokerage=brokerage,
        stt=stt,
        stamp=stamp,
        exchange=exchange,
        sebi=sebi,
        ipft=ipft,
        gst=gst,
    )


def preview_round_trip(
    *,
    entry: float,
    exit_px: float,
    qty: int,
    direction: str = "BUY",
    segment: Optional[str] = None,
    trading_style: str = "INTRADAY",
    profile_id: Optional[str] = None,
    include_v3: bool = False,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
    rates: StatutoryRates = DEFAULT_RATES,
) -> ChargePreview:
    """Direction-aware round trip. Long: buy entry / sell exit. Short: sell entry / buy exit."""
    profile = resolve_profile(profile_id)
    seg = resolve_segment(segment, trading_style)
    notes: List[str] = [
        "V2 = statutory + brokerage (no slippage).",
        "V3 slippage is a scenario, not a tariff line.",
        "Does not write the paper ledger (broker_charges.py remains authority there).",
        "GST is 18% of (brokerage + SEBI + exchange txn); not charged on STT or stamp.",
    ]
    try:
        q = max(int(qty), 0)
        e = float(entry)
        x = float(exit_px)
    except (TypeError, ValueError):
        q, e, x = 0, 0.0, 0.0
    if q <= 0 or e <= 0 or x <= 0:
        empty = ChargePreview(
            profile_id=profile.profile_id,
            segment=seg.value,
            direction=str(direction or "BUY").upper(),
            notes=notes + ["Insufficient price/qty — no charge computed."],
        )
        return empty

    d = str(direction or "BUY").strip().upper()
    if d not in ("BUY", "SELL"):
        d = "BUY"
    entry_side = Side.BUY if d == "BUY" else Side.SELL
    exit_side = Side.SELL if d == "BUY" else Side.BUY
    entry_notional = e * q
    exit_notional = x * q
    buy_notional = entry_notional if entry_side == Side.BUY else exit_notional
    sell_notional = entry_notional if entry_side == Side.SELL else exit_notional
    turnover = entry_notional + exit_notional

    legs = [
        estimate_leg(segment=seg, side=entry_side, notional=entry_notional, profile=profile, rates=rates),
        estimate_leg(segment=seg, side=exit_side, notional=exit_notional, profile=profile, rates=rates),
    ]
    brokerage = _r2(sum(leg.brokerage for leg in legs))
    stt = _r2(sum(leg.stt for leg in legs))
    stamp = _r2(sum(leg.stamp for leg in legs))
    exchange = _r2(sum(leg.exchange for leg in legs))
    sebi = _r2(sum(leg.sebi for leg in legs))
    ipft = _r2(sum(leg.ipft for leg in legs))
    gst = _r2(sum(leg.gst for leg in legs))
    v2 = _r2(brokerage + stt + stamp + exchange + sebi + ipft + gst)
    slip = _r2(turnover * (float(slippage_pct) / 100.0)) if include_v3 else 0.0
    v3 = _r2(v2 + slip) if include_v3 else v2
    if seg == Segment.EQUITY_DELIVERY:
        notes.append("Delivery sells also attract DP (depository) charges — not in this catalog yet.")
    return ChargePreview(
        profile_id=profile.profile_id,
        segment=seg.value,
        direction=d,
        qty=q,
        entry=e,
        exit_px=x,
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        turnover=turnover,
        legs=legs,
        brokerage=brokerage,
        stt=stt,
        stamp=stamp,
        exchange=exchange,
        sebi=sebi,
        ipft=ipft,
        gst=gst,
        v2_charges=v2,
        v3_slippage=slip,
        v3_charges=v3,
        include_v3=bool(include_v3),
        slippage_pct=float(slippage_pct),
        notes=notes,
    )


def catalog_manifest() -> Dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "catalog_id": CATALOG_ID,
        "rate_effective": RATE_EFFECTIVE,
        "source": SOURCE,
        "default_profile_id": DEFAULT_PROFILE_ID,
        "profiles": [
            {"profile_id": p.profile_id, "label": p.label} for p in PROFILES.values()
        ],
        "segments": [s.value for s in Segment],
        "statutory": asdict(DEFAULT_RATES),
        "default_slippage_pct": DEFAULT_SLIPPAGE_PCT,
        "gst_base": "brokerage + SEBI + exchange txn",
    }
