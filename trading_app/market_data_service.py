"""
NexTrade Canonical Market Data Service (GS Quant borrow P1 / OIE-001).

Single facade over Angel market-data bridge so EXECUTION / DISPLAY / RESEARCH
consumers share one authority model. Does not alter risk, strategy, or order logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from contracts.market_data import (
    CanonicalQuote,
    DataAuthority,
    MarketDataResolution,
    QuotePurpose,
)

logger = logging.getLogger("MarketDataService")


def _bridge():
    from trading_app import angel_market_data_bridge as bridge
    return bridge


def _quote_from_dict(
    symbol: str,
    exchange: str,
    raw: Dict[str, Any],
    purpose: QuotePurpose,
    *,
    data_quality: str = "VALID",
) -> CanonicalQuote:
    authority = str(raw.get("data_authority") or "")
    source = str(raw.get("source") or raw.get("price_source") or "")
    if not authority:
        if source in ("ANGEL_WEBSOCKET",):
            authority = DataAuthority.ANGEL_WS_LIVE.value
        elif "REST" in source.upper():
            authority = DataAuthority.ANGEL_REST_REFERENCE.value
        else:
            authority = DataAuthority.NO_VALID_MARKET_DATA.value

    reserved = {
        "ltp", "change_pct", "source", "price_source", "exchange", "data_authority",
        "age_sec", "quote_ts", "quote_timestamp", "received_timestamp",
        "instrument_token", "data_quality", "live", "purpose",
    }
    extras = {k: v for k, v in raw.items() if k not in reserved}

    return CanonicalQuote(
        symbol=symbol.upper(),
        exchange=(exchange or raw.get("exchange") or "NSE").upper(),
        ltp=float(raw.get("ltp") or 0),
        source=source,
        data_authority=authority,
        purpose=purpose.value,
        age_sec=raw.get("age_sec"),
        quote_ts=raw.get("quote_ts"),
        quote_timestamp=raw.get("quote_timestamp"),
        received_timestamp=raw.get("received_timestamp"),
        instrument_token=str(raw["instrument_token"]) if raw.get("instrument_token") else None,
        change_pct=float(raw.get("change_pct") or 0.0),
        data_quality=str(raw.get("data_quality") or data_quality),
        live=bool(raw.get("live", False)),
        extras=extras,
    )


class MarketDataService:
    """
    Canonical market-data entry point.

    EXECUTION → require_ltp (WS live fail-closed)
    DISPLAY   → get_ltp_quote (WS then REST reference)
    RESEARCH  → same display path today; historical adapters may attach later
    """

    def resolve(
        self,
        symbol: str,
        exchange: str = "NSE",
        purpose: QuotePurpose = QuotePurpose.DISPLAY,
    ) -> MarketDataResolution:
        sym = symbol.upper().strip()
        exch = exchange.upper().strip() or "NSE"
        bridge = _bridge()

        if purpose == QuotePurpose.EXECUTION:
            ok, raw, err = bridge.require_ltp(sym, exch)
            if not ok or not raw:
                return MarketDataResolution(
                    ok=False,
                    quote=None,
                    error=err or f"No execution-grade quote for {sym}",
                    paper_execution_allowed=False,
                )
            quote = _quote_from_dict(sym, exch, raw, purpose, data_quality="VALID")
            return MarketDataResolution(
                ok=True,
                quote=quote,
                error="",
                paper_execution_allowed=quote.is_execution_grade,
            )

        # DISPLAY / RESEARCH — never elevate REST to execution
        raw = bridge.get_ltp_quote(sym, exch)
        if not raw or float(raw.get("ltp") or 0) <= 0:
            auth = bridge.resolve_data_authority(sym)
            return MarketDataResolution(
                ok=False,
                quote=None,
                error=f"No display quote for {sym} [authority={auth.get('data_authority')}]",
                paper_execution_allowed=False,
            )
        quote = _quote_from_dict(sym, exch, raw, purpose)
        auth = bridge.resolve_data_authority(sym)
        return MarketDataResolution(
            ok=True,
            quote=quote,
            error="",
            paper_execution_allowed=bool(auth.get("paper_execution_allowed")),
        )

    def require_execution_quote(
        self, symbol: str, exchange: str = "NSE"
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Fail-closed paper/live fill gate — legacy tuple shape for existing callers."""
        res = self.resolve(symbol, exchange, QuotePurpose.EXECUTION)
        if not res.ok or not res.quote:
            return False, None, res.error
        return True, res.quote.to_legacy_dict(), ""

    def get_display_quote(
        self, symbol: str, exchange: str = "NSE"
    ) -> Optional[Dict[str, Any]]:
        res = self.resolve(symbol, exchange, QuotePurpose.DISPLAY)
        return res.quote.to_legacy_dict() if res.ok and res.quote else None

    def get_ltp_map(
        self, symbols: List[str], exchange: str = "NSE"
    ) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for sym in symbols:
            q = self.get_display_quote(sym, exchange)
            if q:
                out[sym.upper()] = q
        return out

    def resolve_authority(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        return _bridge().resolve_data_authority(symbol)

    def get_status(self) -> Dict[str, Any]:
        return _bridge().get_market_data_status()

    def get_index_inputs(self) -> Dict[str, Any]:
        """NIFTY / BANKNIFTY / VIX cockpit inputs — Angel authority."""
        return _bridge().get_cockpit_index_inputs()


_SERVICE: Optional[MarketDataService] = None


def get_market_data_service() -> MarketDataService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MarketDataService()
    return _SERVICE
