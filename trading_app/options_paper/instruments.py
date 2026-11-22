"""Index option contract lookup from the Angel scrip-master token map (``NFO:NIFTY24NOV2624000CE``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

INDEX_TOKENS = {"NIFTY": "99926000", "BANKNIFTY": "99926009", "INDIAVIX": "99926017"}

_SYM_RE = re.compile(r"^NFO:(NIFTY|BANKNIFTY)(\d{2}[A-Z]{3}\d{2})(\d+(?:\.\d+)?)(CE|PE)$")


@dataclass(frozen=True)
class OptionContract:
    underlying: str
    expiry: date
    strike: float
    opt: str          # CE / PE
    symbol: str       # Angel trading symbol (without exchange prefix)
    token: str


class OptionChainIndex:
    def __init__(self, contracts: List[OptionContract]):
        self._by_key: Dict[tuple, OptionContract] = {(c.underlying, c.expiry, c.strike, c.opt): c for c in contracts}
        self._expiries: Dict[str, List[date]] = {}
        for c in contracts:
            self._expiries.setdefault(c.underlying, [])
        for u in self._expiries:
            self._expiries[u] = sorted({c.expiry for c in contracts if c.underlying == u})

    @classmethod
    def from_token_map(cls, token_map: Dict[str, str]) -> "OptionChainIndex":
        out = []
        for key, token in token_map.items():
            m = _SYM_RE.match(key)
            if not m:
                continue
            und, exp, strike, opt = m.groups()
            try:
                exp_d = datetime.strptime(exp, "%d%b%y").date()
            except ValueError:
                continue
            out.append(OptionContract(und, exp_d, float(strike), opt, key.split(":", 1)[1], str(token)))
        return cls(out)

    def __len__(self) -> int:
        return len(self._by_key)

    def expiries(self, underlying: str) -> List[date]:
        return list(self._expiries.get(underlying, []))

    def nearest_expiry(self, underlying: str, today: date) -> Optional[date]:
        for e in self._expiries.get(underlying, []):
            if e >= today:
                return e
        return None

    def get(self, underlying: str, expiry: date, strike: float, opt: str) -> Optional[OptionContract]:
        return self._by_key.get((underlying, expiry, float(strike), opt))
