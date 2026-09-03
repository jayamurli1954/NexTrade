"""
NexTrade Phase 7 — Intelligent Opportunity Engine.

Converts EnhancedAnalyzer signals into actionable trade cards with live Angel LTP.
Hardcoded RELIANCE/HDFCBANK/TCS sample cards are disabled.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from trading_app.journal_analytics import allow_momentum_breakdown_signal
from .trade_ticket_engine import TradePlan, TradeTicketEngine

logger = logging.getLogger("OpportunityEngine")


@dataclass
class TradeOpportunity:
    opportunity_id: str
    symbol: str
    exchange: str = "NSE"
    currency: str = "INR (₹)"
    trading_style: str = "INTRADAY"
    strategy: str = "Technical Scan"
    direction: str = "BUY"
    signal_strength_pct: float = 0.0
    suggested_entry: float = 0.0
    suggested_stop_loss: float = 0.0
    suggested_target: float = 0.0
    suggested_quantity: int = 0
    risk_reward_ratio: float = 0.0
    price_source: str = "UNAVAILABLE"
    why_this_trade: List[str] = field(default_factory=list)
    invalidation_rules: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    rsi: Optional[float] = None
    volume_ratio: Optional[float] = None
    # FI-2 display-only fundamental intelligence
    investment_thesis: List[str] = field(default_factory=list)
    factor_scores: Optional[Dict[str, Any]] = None
    factor_badges: Optional[Dict[str, Any]] = None
    factor_trends: Optional[Dict[str, Any]] = None
    valuation_relatives: Optional[Dict[str, Any]] = None
    fundamentals_meta: Optional[Dict[str, Any]] = None
    ai_summary: Optional[str] = None
    opportunity_strength: Optional[Dict[str, Any]] = None


def _split_reason(reason: str) -> List[str]:
    text = (reason or "").strip()
    if not text:
        return ["Technical scan matched multi-factor score"]
    parts = [p.strip() for p in text.replace(" + ", "|").split("|") if p.strip()]
    return parts[:5] if parts else [text]


def _qty_for_entry(entry: float, notional: Optional[float] = None) -> int:
    from trading_app.paper_capital_policy import qty_for_scrip_allocation

    if notional is not None:
        if entry <= 0:
            return 1
        return max(1, int(float(notional) // entry))
    return qty_for_scrip_allocation(entry)


def _style_for_action(action: str) -> str:
    return "INTRADAY"


def _strategy_label(action: str, rsi: Optional[float]) -> str:
    act = (action or "BUY").upper()
    if act == "SELL":
        return "Momentum Breakdown"
    if rsi is not None and rsi < 35:
        return "Oversold Bounce"
    if rsi is not None and rsi > 65:
        return "Momentum Continuation"
    return "Golden Ratio Scan"


class OpportunityEngine:
    """
    Builds opportunities from analyzer signals + Angel live LTP (fail closed).
    """

    SAMPLE_OPPORTUNITIES = []  # deprecated

    def __init__(self) -> None:
        self.ticket_engine = TradeTicketEngine()
        # No hardcoded symbol templates — analyzer drives selection
        self.templates: List[Any] = []

    def signals_to_opportunities(
        self,
        signals: List[Dict[str, Any]],
        live_ltp_map: Optional[Dict[str, Dict[str, Any]]] = None,
        top_n: int = 10,
        min_confidence: float = 0.55,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> List[TradeOpportunity]:
        """
        Map EnhancedAnalyzer signal dicts → TradeOpportunity cards.

        Entry/SL/Target use Angel live LTP when available; analyzer SL/target
        are scaled to the live entry so geometry stays consistent.

        market_context (optional): india_vix, nifty_change_pct — used to gate
        Momentum Breakdown / SELL paper opportunities after journal review.
        """
        live_ltp_map = live_ltp_map or {}
        market_context = market_context or {}
        out: List[TradeOpportunity] = []

        ranked = sorted(
            [s for s in signals if s and float(s.get("confidence") or 0) >= min_confidence],
            key=lambda s: float(s.get("confidence") or 0),
            reverse=True,
        )

        for sig in ranked:
            action = str(sig.get("action") or "HOLD").upper()
            if action not in ("BUY", "SELL"):
                continue
            symbol = str(sig.get("symbol") or "").upper().strip()
            if not symbol:
                continue

            # Paper experiment: tighten Momentum Breakdown (all SELLs)
            if action == "SELL":
                ok_mb, mb_reason = allow_momentum_breakdown_signal(sig, market_context)
                if not ok_mb:
                    logger.info("Skip %s SELL: %s", symbol, mb_reason)
                    continue

            q = live_ltp_map.get(symbol) or {}
            src = str(q.get("source") or "")
            try:
                angel_ltp = float(q.get("ltp") or 0)
            except (TypeError, ValueError):
                angel_ltp = 0.0

            # Fail closed: require Angel quote for displayable entry
            if angel_ltp <= 0 or not src.startswith("ANGEL"):
                continue

            try:
                ana_entry = float(sig.get("current_price") or angel_ltp)
                ana_sl = float(sig.get("stop_loss") or 0)
                ana_tp = float(sig.get("target") or 0)
            except (TypeError, ValueError):
                continue

            entry = round(angel_ltp, 2)
            # Scale analyzer SL/TP from analyzer price to live Angel entry
            if ana_entry > 0 and ana_sl > 0 and ana_tp > 0:
                scale = entry / ana_entry
                sl = round(ana_sl * scale, 2)
                tp = round(ana_tp * scale, 2)
            else:
                # Fallback geometry if analyzer omitted stops
                if action == "BUY":
                    sl = round(entry * 0.98, 2)
                    tp = round(entry * 1.04, 2)
                else:
                    sl = round(entry * 1.02, 2)
                    tp = round(entry * 0.96, 2)

            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = round(reward / risk, 2) if risk > 0 else 0.0
            conf = float(sig.get("confidence") or 0)
            strength = round(conf * 100.0, 1)
            rsi_v = sig.get("rsi")
            try:
                rsi_f = float(rsi_v) if rsi_v is not None else None
            except (TypeError, ValueError):
                rsi_f = None

            why = _split_reason(str(sig.get("reason") or ""))
            # FI-2: keep why_this_trade technical-only (do not append raw fund highlights)
            vol = sig.get("volume_ratio")
            if vol is not None:
                try:
                    why.append(f"Volume ratio {float(vol):.2f}x vs average")
                except (TypeError, ValueError):
                    pass
            if rsi_f is not None:
                why.append(f"RSI {rsi_f:.1f}")
            if action == "SELL":
                why.append("MB gate: conf>=0.70, RSI>=45, VIX>=13, NIFTY day<=+0.35%")

            thesis = list(sig.get("investment_thesis") or [])
            factor_scores = sig.get("factor_scores")
            factor_badges = sig.get("factor_badges")
            factor_trends = sig.get("factor_trends")
            valuation_relatives = sig.get("valuation_relatives")
            fundamentals_meta = sig.get("fundamentals_meta")

            # Fallback: load via Fundamental Service if analyzer omitted display fields
            if not thesis and not factor_scores:
                try:
                    from research.fundamental_service import get_fundamental_service

                    intel = get_fundamental_service().get_symbol_intelligence(symbol)
                    if intel:
                        thesis = list(intel.get("investment_thesis") or [])
                        factor_scores = intel.get("factor_scores")
                        factor_badges = intel.get("factor_badges")
                        factor_trends = intel.get("factor_trends")
                        valuation_relatives = intel.get("valuation_relatives")
                        fundamentals_meta = {
                            "source": "factor_store",
                            "factor_version": intel.get("factor_version"),
                            "generated_at": intel.get("generated_at"),
                            "fiscal_year": intel.get("fiscal_year"),
                            "as_of_label": intel.get("as_of_label"),
                        }
                except Exception as e:
                    logger.debug("FI-2 factor attach skipped for %s: %s", symbol, e)

            from research.fundamental_service import build_ai_summary

            ai_summary = build_ai_summary(
                direction=action,
                why_technical=why,
                factor_scores=factor_scores,
                thesis=thesis,
            )

            # Display-only opportunity strength (does NOT affect ranking / gates)
            fund_overall = None
            if isinstance(factor_scores, dict):
                try:
                    fund_overall = float(factor_scores.get("overall_fundamental"))
                except (TypeError, ValueError):
                    fund_overall = None
            if fund_overall is not None:
                overall_opp = round(0.60 * strength + 0.40 * fund_overall, 1)
            else:
                overall_opp = strength
            opportunity_strength = {
                "technical": strength,
                "fundamental": round(fund_overall, 1) if fund_overall is not None else None,
                "overall_opportunity": overall_opp,
                "note": "Display only — does not change BUY/SELL gates",
            }

            sl_fmt = f"{sl:,.2f}"
            if action == "BUY":
                inv = [
                    f"Price closes below ₹{sl_fmt} stop",
                    "Signal confidence collapses on next scan",
                    "Index regime turns strongly adverse",
                ]
            else:
                inv = [
                    f"Price closes above ₹{sl_fmt} stop",
                    "Short thesis invalidated on next scan",
                    "Index regime turns strongly adverse",
                ]

            out.append(
                TradeOpportunity(
                    opportunity_id=f"scan_{symbol.lower()}_{action.lower()}",
                    symbol=symbol,
                    trading_style=_style_for_action(action),
                    strategy=_strategy_label(action, rsi_f),
                    direction=action,
                    signal_strength_pct=strength,
                    suggested_entry=entry,
                    suggested_stop_loss=sl,
                    suggested_target=tp,
                    suggested_quantity=_qty_for_entry(entry),
                    risk_reward_ratio=rr,
                    price_source=src,
                    why_this_trade=why[:6],
                    invalidation_rules=inv,
                    rsi=rsi_f,
                    volume_ratio=float(vol) if vol is not None else None,
                    investment_thesis=thesis[:6],
                    factor_scores=factor_scores,
                    factor_badges=factor_badges,
                    factor_trends=factor_trends,
                    valuation_relatives=valuation_relatives,
                    fundamentals_meta=fundamentals_meta,
                    ai_summary=ai_summary,
                    opportunity_strength=opportunity_strength,
                )
            )
            if len(out) >= top_n:
                break

        return out

    def get_top_opportunities(
        self,
        live_ltp_map: Optional[Dict[str, Dict[str, Any]]] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
        top_n: int = 10,
        min_confidence: float = 0.55,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> List[TradeOpportunity]:
        """
        Analyzer-driven opportunities only. Empty signals → empty list (no hardcoded cards).
        """
        if not signals:
            return []
        return self.signals_to_opportunities(
            signals=signals,
            live_ltp_map=live_ltp_map,
            top_n=top_n,
            min_confidence=min_confidence,
            market_context=market_context,
        )

    def convert_opportunity_to_trade_plan(
        self, opp: TradeOpportunity, quantity: Optional[int] = None
    ) -> TradePlan:
        if float(opp.suggested_entry or 0) <= 0:
            raise ValueError(f"Opportunity {opp.symbol} has no live Angel entry price")
        qty = quantity or opp.suggested_quantity
        return self.ticket_engine.create_trade_plan(
            symbol=opp.symbol,
            trading_style=opp.trading_style,
            strategy=opp.strategy,
            direction=opp.direction or "BUY",
            entry_price=opp.suggested_entry,
            quantity=qty,
            stop_loss_price=opp.suggested_stop_loss,
            target_price=opp.suggested_target,
            trailing_stop_amount=20.0,
            execution_mode="PAPER_TRADING",
        )
