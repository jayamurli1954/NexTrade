"""
User-configurable paper day flatten limits + Angel charge profile (persisted).

Defaults: profit +₹1,500 / loss −₹2,000 (gross combined day PnL triggers).
Net projections subtract/add estimated statutory charges (Angel One template).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from trading_app.broker_charges import AngelOneEquityIntradayCharges, estimate_round_trip_total
from trading_app.journal_analytics import enrich_trade_with_net, filter_trades_for_day

logger = logging.getLogger("PaperDayRiskPolicy")

DEFAULT_PROFIT_TARGET_INR = 1500.0
DEFAULT_LOSS_LIMIT_INR = 2000.0

_lock = threading.RLock()
_policy_path: Optional[str] = None


@dataclass
class PaperDayRiskPolicy:
    profit_target_inr: float = DEFAULT_PROFIT_TARGET_INR  # gross + trigger
    loss_limit_inr: float = DEFAULT_LOSS_LIMIT_INR  # gross − trigger (stored positive)
    charges: AngelOneEquityIntradayCharges = field(default_factory=AngelOneEquityIntradayCharges)
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profit_target_inr": float(self.profit_target_inr),
            "loss_limit_inr": float(self.loss_limit_inr),
            "charges": self.charges.to_dict(),
            "updated_at": self.updated_at or datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "PaperDayRiskPolicy":
        if not raw:
            return cls()
        return cls(
            profit_target_inr=float(raw.get("profit_target_inr") or DEFAULT_PROFIT_TARGET_INR),
            loss_limit_inr=float(raw.get("loss_limit_inr") or DEFAULT_LOSS_LIMIT_INR),
            charges=AngelOneEquityIntradayCharges.from_dict(raw.get("charges")),
            updated_at=str(raw.get("updated_at") or ""),
        )


def configure_policy_path(path: str) -> None:
    global _policy_path
    _policy_path = path


def _default_path() -> str:
    if _policy_path:
        return _policy_path
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "storage", "paper_day_risk_policy.json")


def load_policy() -> PaperDayRiskPolicy:
    path = _default_path()
    with _lock:
        if not os.path.exists(path):
            return PaperDayRiskPolicy()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return PaperDayRiskPolicy.from_dict(json.load(f))
        except Exception as exc:
            logger.warning("Failed to load day risk policy: %s", exc)
            return PaperDayRiskPolicy()


def save_policy(policy: PaperDayRiskPolicy) -> PaperDayRiskPolicy:
    path = _default_path()
    policy = PaperDayRiskPolicy(
        profit_target_inr=max(0.0, float(policy.profit_target_inr)),
        loss_limit_inr=max(0.0, float(policy.loss_limit_inr)),
        charges=policy.charges,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(policy.to_dict(), f, indent=2)
    return policy


def parse_policy_update(payload: Dict[str, Any]) -> PaperDayRiskPolicy:
    """Merge user form/API values onto current policy."""
    cur = load_policy()
    profit = payload.get("profit_target_inr", cur.profit_target_inr)
    loss = payload.get("loss_limit_inr", cur.loss_limit_inr)
    try:
        profit_f = abs(float(profit))
    except (TypeError, ValueError):
        profit_f = cur.profit_target_inr
    try:
        loss_f = abs(float(loss))
    except (TypeError, ValueError):
        loss_f = cur.loss_limit_inr

    charges_raw = dict(cur.charges.to_dict())
    if isinstance(payload.get("charges"), dict):
        charges_raw.update(payload["charges"])
    for key in (
        "brokerage_per_order_inr",
        "stt_sell_pct",
        "exchange_txn_pct",
        "gst_on_brokerage_pct",
        "sebi_turnover_pct",
        "stamp_duty_buy_pct",
        "slippage_pct",
    ):
        if key in payload:
            charges_raw[key] = payload[key]

    return PaperDayRiskPolicy(
        profit_target_inr=profit_f,
        loss_limit_inr=loss_f,
        charges=AngelOneEquityIntradayCharges.from_dict(charges_raw),
    )


def _charges_for_closed_today(trades_today: List[Dict[str, Any]], model: AngelOneEquityIntradayCharges) -> float:
    total = 0.0
    for t in trades_today:
        e = enrich_trade_with_net(t)
        # Recompute with user's charge model if stored charges missing
        if e.get("entry_price") and e.get("exit_price") and e.get("quantity"):
            total += estimate_round_trip_total(
                entry=float(e["entry_price"]),
                exit_px=float(e["exit_price"]),
                qty=int(e["quantity"]),
                model=model,
            )
        else:
            total += float(e.get("est_charges") or 0.0)
    return total


def _charges_for_open_on_flatten(open_positions: List[Dict[str, Any]], model: AngelOneEquityIntradayCharges) -> float:
    """Exit leg charges proxy: full round trip minus already-paid entry leg approx = one order + sell-side statutory."""
    total = 0.0
    for p in open_positions:
        try:
            entry = float(p.get("entry_price_raw") or p.get("entry_price") or 0)
            exit_px = float(p.get("ltp") or p.get("entry_price_raw") or entry)
            qty = int(p.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if entry <= 0 or qty <= 0:
            continue
        total += estimate_round_trip_total(entry=entry, exit_px=exit_px, qty=qty, model=model)
    return total


def build_day_limit_projection(
    *,
    policy: Optional[PaperDayRiskPolicy] = None,
    trades: Optional[List[Dict[str, Any]]] = None,
    open_positions: Optional[List[Dict[str, Any]]] = None,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Show gross limits vs estimated net after Angel-style charges.
    User example: +1500 gross → ~1200 net; −2000 gross → ~2300 net loss.
    """
    pol = policy or load_policy()
    today = today or datetime.now().strftime("%Y-%m-%d")
    closed_today = filter_trades_for_day(trades or [], today)
    open_pos = list(open_positions or [])

    charges_closed = _charges_for_closed_today(closed_today, pol.charges)
    charges_on_flatten = _charges_for_open_on_flatten(open_pos, pol.charges)
    # Avoid double-counting: closed trades already paid; open positions pay full round trip on flatten
    est_total_charges = charges_closed + charges_on_flatten

    profit_gross = float(pol.profit_target_inr)
    loss_gross = float(pol.loss_limit_inr)
    net_profit = profit_gross - est_total_charges
    net_loss = -(loss_gross + est_total_charges)

    return {
        "profit_target_gross_inr": round(profit_gross, 2),
        "loss_limit_gross_inr": round(loss_gross, 2),
        "est_charges_closed_today_inr": round(charges_closed, 2),
        "est_charges_if_flatten_open_inr": round(charges_on_flatten, 2),
        "est_total_charges_inr": round(est_total_charges, 2),
        "net_profit_if_target_hit_inr": round(net_profit, 2),
        "net_loss_if_limit_hit_inr": round(net_loss, 2),
        "charges_broker": pol.charges.broker,
        "charges_profile": pol.charges.to_dict(),
        "charges_note": (
            "Estimated from Angel One equity intraday tariff template. "
            "Adjust fields to match your Angel contract; live API fetch not wired yet."
        ),
        "policy_updated_at": pol.updated_at,
    }
