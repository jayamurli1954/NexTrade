"""
Local options OHLC store for ARASS research (jugaad-data / NSE daily).

Schema (long table):
  date, expiry, strike, option_type, open, high, low, close, volume, oi, symbol
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger("ArassOptionsStore")

REQUIRED_COLS = ("date", "expiry", "strike", "option_type", "open", "high", "low", "close")


def default_store_dir(root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[2]
    return base / "research" / "data" / "options"


def normalize_options_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize jugaad / CSV columns into the store schema."""
    if df is None or df.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLS) + ["volume", "oi", "symbol"])

    rename = {
        "DATE": "date",
        "Date": "date",
        "EXPIRY": "expiry",
        "Expiry": "expiry",
        "OPTION TYPE": "option_type",
        "Option Type": "option_type",
        "optionType": "option_type",
        "STRIKE PRICE": "strike",
        "Strike Price": "strike",
        "strikePrice": "strike",
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "TOTAL TRADED QUANTITY": "volume",
        "Volume": "volume",
        "OPEN INTEREST": "oi",
        "Open Interest": "oi",
        "SYMBOL": "symbol",
        "Symbol": "symbol",
    }
    out = df.rename(columns={k: v for k, v in rename.items() if k in df.columns}).copy()
    for c in REQUIRED_COLS:
        if c not in out.columns:
            raise ValueError(f"Options frame missing column: {c}")
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.normalize()
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["option_type"] = out["option_type"].astype(str).str.upper().str.strip()
    out["option_type"] = out["option_type"].replace({"CALL": "CE", "PUT": "PE"})
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    if "oi" not in out.columns:
        out["oi"] = 0.0
    if "symbol" not in out.columns:
        out["symbol"] = "NIFTY"
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out = out.dropna(subset=["date", "expiry", "strike", "option_type", "close"])
    out = out.sort_values(["symbol", "expiry", "strike", "option_type", "date"])
    out = out.drop_duplicates(["symbol", "date", "expiry", "strike", "option_type"], keep="last")
    return out.reset_index(drop=True)


@dataclass
class OptionsStore:
    path: Path
    df: pd.DataFrame

    @classmethod
    def empty(cls, path: Path) -> "OptionsStore":
        return cls(path=path, df=normalize_options_df(pd.DataFrame()))

    @classmethod
    def load(cls, path: Path | str) -> "OptionsStore":
        path = Path(path)
        if not path.exists():
            return cls.empty(path)
        if path.suffix.lower() == ".parquet":
            raw = pd.read_parquet(path)
        else:
            raw = pd.read_csv(path)
        return cls(path=path, df=normalize_options_df(raw))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.df = normalize_options_df(self.df)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        if self.path.suffix.lower() == ".parquet":
            self.df.to_parquet(tmp, index=False)
        else:
            self.df.to_csv(tmp, index=False)
        tmp.replace(self.path)
        meta = {
            "rows": int(len(self.df)),
            "symbols": sorted(self.df["symbol"].unique().tolist()) if len(self.df) else [],
            "date_min": str(self.df["date"].min().date()) if len(self.df) else None,
            "date_max": str(self.df["date"].max().date()) if len(self.df) else None,
        }
        meta_path = self.path.parent / f"{self.path.stem}_manifest.json"
        meta_tmp = meta_path.with_suffix(".json.tmp")
        meta_tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        meta_tmp.replace(meta_path)

    def merge(self, other: pd.DataFrame) -> int:
        before = len(self.df)
        self.df = normalize_options_df(pd.concat([self.df, normalize_options_df(other)], ignore_index=True))
        return int(len(self.df) - before)

    def has_contract(self, *, symbol: str, expiry: pd.Timestamp, strike: float, option_type: str) -> bool:
        if self.df.empty:
            return False
        exp = pd.Timestamp(expiry).normalize()
        mask = (
            (self.df["symbol"] == symbol.upper())
            & (self.df["expiry"] == exp)
            & (self.df["strike"] == float(strike))
            & (self.df["option_type"] == option_type.upper())
        )
        return bool(mask.any())

    def lookup(
        self,
        *,
        symbol: str,
        asof: pd.Timestamp,
        expiry: pd.Timestamp,
        strike: float,
        option_type: str,
        field: str = "close",
        strike_step: float = 50.0,
        allow_nearest_strike: bool = True,
        allow_nearest_expiry: bool = True,
        asof_policy: str = "on_or_before",
    ) -> Optional[float]:
        """
        Return option premium field for research marks.

        Policies (MDW-1):
        - asof normalized to calendar day (daily OHLC store)
        - asof_policy: exact | on_or_before (last available premium ≤ asof for contract)
        - nearest strike within ±strike_step*2 when exact ATM missing
        - nearest expiry on/after asof day when exact expiry missing (weekly holiday shifts)
        """
        if self.df.empty:
            return None
        day = pd.Timestamp(asof).tz_localize(None) if getattr(asof, "tzinfo", None) else pd.Timestamp(asof)
        day = day.normalize()
        exp = pd.Timestamp(expiry).tz_localize(None) if getattr(expiry, "tzinfo", None) else pd.Timestamp(expiry)
        exp = exp.normalize()
        field = field.lower()
        if field not in ("open", "high", "low", "close"):
            field = "close"
        sym = symbol.upper()
        otype = option_type.upper()
        strike_f = float(strike)

        sub = self.df[(self.df["symbol"] == sym) & (self.df["option_type"] == otype)]
        if sub.empty:
            return None

        # --- expiry soft match ---
        exp_exact = sub[sub["expiry"] == exp]
        if exp_exact.empty and allow_nearest_expiry:
            # prefer expiry on/after trade day, else nearest absolute
            future = sub[sub["expiry"] >= day]
            if not future.empty:
                # among expiries, pick closest to requested exp, else soonest
                uniq = future["expiry"].drop_duplicates()
                exp = min(uniq, key=lambda e: (abs((e - exp).days), (e - day).days))
                exp_exact = sub[sub["expiry"] == exp]
            else:
                return None
        if exp_exact.empty:
            return None

        # --- strike soft match ---
        strike_exact = exp_exact[exp_exact["strike"] == strike_f]
        if strike_exact.empty and allow_nearest_strike:
            strikes = exp_exact["strike"].drop_duplicates()
            if strikes.empty:
                return None
            nearest = min(strikes, key=lambda s: abs(float(s) - strike_f))
            if abs(float(nearest) - strike_f) > max(strike_step * 2.0, 100.0):
                return None
            strike_f = float(nearest)
            strike_exact = exp_exact[exp_exact["strike"] == strike_f]
        if strike_exact.empty:
            return None

        # --- asof date policy ---
        if asof_policy == "exact":
            hit = strike_exact[strike_exact["date"] == day]
        else:
            # on_or_before: last bar ≤ day for this contract
            hist = strike_exact[strike_exact["date"] <= day].sort_values("date")
            hit = hist.iloc[-1:] if not hist.empty else strike_exact.iloc[0:0]

        if hit.empty:
            return None
        val = float(hit.iloc[-1][field])
        return val if val == val else None

    def straddle(
        self,
        *,
        symbol: str,
        asof: pd.Timestamp,
        expiry: pd.Timestamp,
        strike: float,
        field: str = "close",
        strike_step: float = 50.0,
        allow_nearest_strike: bool = True,
        allow_nearest_expiry: bool = True,
        asof_policy: str = "on_or_before",
    ) -> Optional[Tuple[float, float]]:
        kwargs = dict(
            symbol=symbol,
            asof=asof,
            expiry=expiry,
            strike=strike,
            field=field,
            strike_step=strike_step,
            allow_nearest_strike=allow_nearest_strike,
            allow_nearest_expiry=allow_nearest_expiry,
            asof_policy=asof_policy,
        )
        ce = self.lookup(option_type="CE", **kwargs)
        pe = self.lookup(option_type="PE", **kwargs)
        if ce is None or pe is None:
            return None
        return ce, pe

    def diagnose_straddle_coverage(
        self,
        *,
        symbol: str,
        samples: list,
        strike_step: float = 50.0,
    ) -> Dict[str, Any]:
        """
        samples: list of dicts with asof, expiry, strike
        Returns hit/miss counts under soft vs exact policies.
        """
        exact_hits = soft_hits = 0
        n = len(samples)
        for s in samples:
            exact = self.straddle(
                symbol=symbol,
                asof=s["asof"],
                expiry=s["expiry"],
                strike=float(s["strike"]),
                allow_nearest_strike=False,
                allow_nearest_expiry=False,
                asof_policy="exact",
            )
            soft = self.straddle(
                symbol=symbol,
                asof=s["asof"],
                expiry=s["expiry"],
                strike=float(s["strike"]),
                strike_step=strike_step,
                allow_nearest_strike=True,
                allow_nearest_expiry=True,
                asof_policy="on_or_before",
            )
            if exact is not None:
                exact_hits += 1
            if soft is not None:
                soft_hits += 1
        return {
            "samples": n,
            "exact_hits": exact_hits,
            "exact_hit_rate_pct": (exact_hits / n * 100.0) if n else 0.0,
            "soft_hits": soft_hits,
            "soft_hit_rate_pct": (soft_hits / n * 100.0) if n else 0.0,
        }


def contract_key(symbol: str, expiry: Any, strike: float, option_type: str) -> str:
    exp = pd.Timestamp(expiry).strftime("%Y-%m-%d")
    return f"{symbol.upper()}_{exp}_{int(float(strike))}_{option_type.upper()}"
