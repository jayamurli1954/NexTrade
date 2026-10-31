"""Symbol alias map for fundamentals fetch (corporate actions / NSE ticker changes)."""

from __future__ import annotations

from typing import Dict

# Watchlist symbol -> NSE / Screener fetch symbol
FETCH_SYMBOL_ALIASES: Dict[str, str] = {
    # Tata Motors passenger vehicles demerger (watchlist still uses legacy label)
    "TATAMOTORS": "TMPV",
}


def resolve_fetch_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    return FETCH_SYMBOL_ALIASES.get(sym, sym)
