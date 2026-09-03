"""
Canonical Market Data contracts (GS Quant borrow P1 / OIE-001).

Defines quote provenance, consumer purpose, and data-authority vocabulary.
Does not change risk limits, strategy scoring, or execution decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class QuotePurpose(str, Enum):
    """What a caller is allowed to use a quote for."""

    EXECUTION = "EXECUTION"   # Paper/live fills — WS live only
    DISPLAY = "DISPLAY"       # UI / cockpit — WS preferred, REST OK
    RESEARCH = "RESEARCH"     # Analytics / history — non-execution sources OK


class DataAuthority(str, Enum):
    ANGEL_WS_LIVE = "ANGEL_WS_LIVE"
    ANGEL_WS_STALE = "ANGEL_WS_STALE"
    ANGEL_WS_DISCONNECTED = "ANGEL_WS_DISCONNECTED"
    ANGEL_REST_REFERENCE = "ANGEL_REST_REFERENCE"
    NO_VALID_MARKET_DATA = "NO_VALID_MARKET_DATA"
    RESEARCH_REFERENCE = "RESEARCH_REFERENCE"  # yfinance / historical — never fill


# Purposes that may never consume RESEARCH_REFERENCE or REST as fill authority
_EXECUTION_AUTHORITIES = frozenset({DataAuthority.ANGEL_WS_LIVE.value, "ANGEL_WS_LIVE"})


@dataclass(frozen=True)
class CanonicalQuote:
    """Single-instrument quote with provenance — institutional-style data object."""

    symbol: str
    exchange: str
    ltp: float
    source: str
    data_authority: str
    purpose: str
    age_sec: Optional[float] = None
    quote_ts: Optional[float] = None
    quote_timestamp: Optional[str] = None
    received_timestamp: Optional[str] = None
    instrument_token: Optional[str] = None
    change_pct: float = 0.0
    data_quality: str = "UNKNOWN"
    live: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_execution_grade(self) -> bool:
        return (
            self.data_authority in _EXECUTION_AUTHORITIES
            and self.ltp > 0
            and self.data_quality in ("VALID", "UNKNOWN", "")
        )

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Bridge to existing Angel dict consumers without breaking call sites."""
        out: Dict[str, Any] = {
            "ltp": self.ltp,
            "change_pct": self.change_pct,
            "source": self.source,
            "price_source": self.source,
            "exchange": self.exchange,
            "data_authority": self.data_authority,
            "age_sec": self.age_sec,
            "quote_ts": self.quote_ts,
            "quote_timestamp": self.quote_timestamp,
            "received_timestamp": self.received_timestamp,
            "instrument_token": self.instrument_token,
            "data_quality": self.data_quality,
            "live": self.live,
            "purpose": self.purpose,
        }
        out.update(self.extras)
        return out


@dataclass(frozen=True)
class MarketDataResolution:
    """Result of a MarketDataService resolve call."""

    ok: bool
    quote: Optional[CanonicalQuote]
    error: str = ""
    paper_execution_allowed: bool = False
