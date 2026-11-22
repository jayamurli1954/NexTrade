"""Quote sources for the options paper lane. Read-only market data; no order endpoints are used."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Protocol


@dataclass(frozen=True)
class Quote:
    token: str
    ltp: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    feed_time: Optional[datetime] = None   # exchange feed timestamp (detects stale/holiday data)

    @property
    def buy_price(self) -> float:
        """Price we would pay to buy now (ask, else LTP)."""
        return self.ask if self.ask and self.ask > 0 else self.ltp

    @property
    def sell_price(self) -> float:
        """Price we would receive selling now (bid, else LTP)."""
        return self.bid if self.bid and self.bid > 0 else self.ltp


class QuoteSource(Protocol):
    def fetch(self, nse_tokens: Iterable[str], nfo_tokens: Iterable[str]) -> Dict[str, Quote]: ...


def _best(levels) -> Optional[float]:
    for lv in levels or []:
        try:
            px = float(lv.get("price") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if px > 0:
            return px
    return None


def _parse_time(v) -> Optional[datetime]:
    if not v:
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(v).strip(), fmt)
        except ValueError:
            continue
    return None


def parse_market_data(resp: dict) -> Dict[str, Quote]:
    """Parse SmartAPI getMarketData('FULL', ...) response into {token: Quote}."""
    if not isinstance(resp, dict) or not resp.get("status"):
        msg = resp.get("message") if isinstance(resp, dict) else resp
        raise RuntimeError(f"getMarketData failed: {msg}")
    out: Dict[str, Quote] = {}
    for row in (resp.get("data") or {}).get("fetched") or []:
        tok = str(row.get("symbolToken"))
        depth = row.get("depth") or {}
        out[tok] = Quote(tok, float(row.get("ltp") or 0.0), _best(depth.get("buy")), _best(depth.get("sell")),
                         _parse_time(row.get("exchFeedTime") or row.get("exchTradeTime")))
    return out


class AngelQuoteSource:
    """One FULL-mode REST call per poll for index + all legs, via the shared Angel REST limiter."""

    def __init__(self, smart_api, rest_call: Optional[Callable] = None):
        self.api = smart_api
        if rest_call is None:
            from trading_app.angel_rest_limiter import angel_rest_call

            rest_call = angel_rest_call
        self._call = rest_call

    MAX_TOKENS_PER_CALL = 50  # Angel market-data limit per request

    def fetch(self, nse_tokens: Iterable[str], nfo_tokens: Iterable[str]) -> Dict[str, Quote]:
        items = [("NSE", str(t)) for t in dict.fromkeys(nse_tokens)] + [("NFO", str(t)) for t in dict.fromkeys(nfo_tokens)]
        out: Dict[str, Quote] = {}
        for i in range(0, len(items), self.MAX_TOKENS_PER_CALL):
            req: Dict[str, List[str]] = {}
            for exch, tok in items[i:i + self.MAX_TOKENS_PER_CALL]:
                req.setdefault(exch, []).append(tok)
            resp = self._call("options_paper.getMarketData", lambda r=req: self.api.getMarketData("FULL", r))
            out.update(parse_market_data(resp))
        return out
