"""
Feature Store — unified date×symbol research features.

SanMitra Research Platform. Research-only. Not execution authority.
B1b: fundamental point-in-time backfill from factor historical/current stores.
B1c: technical backfill deferred.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from research.data_validation import DataValidationEngine
from research.feature_registry import FeatureRegistry, bootstrap_registry, default_registry_path
from research.factor_score_store import FactorScoreStore


def default_feature_store_dir(root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / "research" / "data" / "feature_store"


TECHNICAL_COLS = ("rsi", "ema20", "ema50", "atr", "adx")
FUNDAMENTAL_COLS = (
    "quality",
    "growth",
    "value",
    "financial_health",
    "consistency",
    "overall_fundamental",
)
MARKET_COLS = ("vix", "pcr", "oi")


@dataclass
class FeatureRow:
    date: str
    symbol: str
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = {"date": self.date, "symbol": self.symbol}
        out.update(self.features)
        return out


class FeatureStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else default_feature_store_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.panel_path = self.root / "features_daily.csv"
        self.manifest_path = self.root / "manifests" / "feature_build.json"
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "registry.json"
        # VAL-H: mtime-based cache so feature_panel() stays under perf targets
        self._panel_cache: Optional[pd.DataFrame] = None
        self._panel_mtime: Optional[float] = None

    def save_panel(self, df: pd.DataFrame) -> Path:
        if df is None or df.empty:
            empty = pd.DataFrame(columns=["date", "symbol"])
            empty.to_csv(self.panel_path, index=False)
            rows = 0
        else:
            out = df.copy()
            if "date" in out.columns:
                out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
            out["symbol"] = out["symbol"].astype(str).str.upper()
            out = out.drop_duplicates(["date", "symbol"], keep="last")
            out.to_csv(self.panel_path, index=False)
            rows = int(len(out))
        self._panel_cache = None
        self._panel_mtime = None
        return self.panel_path

    def load_panel(self) -> pd.DataFrame:
        if not self.panel_path.exists():
            return pd.DataFrame(columns=["date", "symbol"])
        try:
            mtime = self.panel_path.stat().st_mtime
        except OSError:
            mtime = None
        if self._panel_cache is not None and mtime is not None and mtime == self._panel_mtime:
            return self._panel_cache
        df = pd.read_csv(self.panel_path)
        self._panel_cache = df
        self._panel_mtime = mtime
        return df

    def write_manifest(self, payload: Dict[str, Any]) -> Path:
        payload = dict(payload)
        payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        payload.setdefault("platform", "SanMitra Research Platform")
        payload.setdefault("note", "Research-only Feature Store. Not execution authority.")
        self.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.manifest_path

    def upsert_factor_snapshot(self, as_of_date: str, scores_by_symbol: Dict[str, Dict[str, Any]]) -> Path:
        rows: List[Dict[str, Any]] = []
        for sym, scores in sorted(scores_by_symbol.items()):
            row: Dict[str, Any] = {"date": as_of_date, "symbol": sym.upper()}
            for k in FUNDAMENTAL_COLS:
                row[k] = (scores or {}).get(k)
            for k in TECHNICAL_COLS + MARKET_COLS:
                row.setdefault(k, None)
            rows.append(row)
        new_df = pd.DataFrame(rows)
        existing = self.load_panel()
        if existing.empty:
            self.save_panel(new_df)
        else:
            existing = existing[existing["date"].astype(str) != str(as_of_date)]
            self.save_panel(pd.concat([existing, new_df], ignore_index=True))
        return self.panel_path

    def _factor_series_by_symbol(self, factor_store: FactorScoreStore) -> Dict[str, List[tuple]]:
        years = factor_store.list_historical_years()
        by_symbol: Dict[str, List[tuple]] = {}
        for year in years:
            path = factor_store.historical_path(year)
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            for sym, rec in (payload.get("symbols") or {}).items():
                scores = (rec or {}).get("scores") or {}
                by_symbol.setdefault(sym.upper(), []).append((int(year), scores))

        current = factor_store.load_current() or {}
        for sym, rec in (current.get("symbols") or {}).items():
            fy = int(rec.get("fiscal_year") or (years[-1] if years else 0))
            scores = (rec or {}).get("scores") or {}
            hist = by_symbol.setdefault(sym.upper(), [])
            hist = [(y, s) for y, s in hist if y != fy]
            hist.append((fy, scores))
            by_symbol[sym.upper()] = sorted(hist, key=lambda t: t[0])
        return by_symbol

    @staticmethod
    def _pit_scores(series: List[tuple], as_of: str) -> Optional[Dict[str, Any]]:
        as_of_ts = pd.Timestamp(as_of)
        chosen = None
        for fy, scores in series:
            fy_end = pd.Timestamp(f"{fy}-03-31")
            if fy_end <= as_of_ts:
                chosen = scores
        return chosen

    def backfill_fundamentals_pit(
        self,
        *,
        factor_store: Optional[FactorScoreStore] = None,
        as_of_dates: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Point-in-time fundamental features on FY-end dates (+ current build date).
        Prefer backfill_technicals_and_fundamentals for daily research panels.
        """
        fs = factor_store or FactorScoreStore()
        by_symbol = self._factor_series_by_symbol(fs)
        years = fs.list_historical_years()
        if not by_symbol:
            return {"rows_written": 0, "reason": "no_factor_data"}

        current = fs.load_current() or {}
        current_built = str(current.get("built_at") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if as_of_dates is None:
            as_of_dates = [f"{y}-03-31" for y in years] + [current_built]
        as_of_dates = sorted(set(str(d) for d in as_of_dates))

        rows: List[Dict[str, Any]] = []
        for as_of in as_of_dates:
            for sym, series in by_symbol.items():
                chosen = self._pit_scores(series, as_of)
                if chosen is None:
                    continue
                row: Dict[str, Any] = {"date": as_of, "symbol": sym}
                for k in FUNDAMENTAL_COLS:
                    row[k] = chosen.get(k)
                for k in TECHNICAL_COLS + MARKET_COLS:
                    row[k] = None
                rows.append(row)

        new_df = pd.DataFrame(rows)
        existing = self.load_panel()
        if not existing.empty:
            existing = existing[~existing["date"].astype(str).isin(as_of_dates)]
            merged = pd.concat([existing, new_df], ignore_index=True)
        else:
            merged = new_df
        self.save_panel(merged)

        dve = DataValidationEngine()
        report = dve.validate_feature_panel(merged)
        dve.save_report(report, self.root / "manifests" / "validation_latest.json")
        coverage = (report.stats or {}).get("coverage_pct") or {}
        manifest = {
            "mode": "fundamentals_pit_b1b",
            "as_of_dates": as_of_dates,
            "rows": int(len(merged)),
            "symbols": int(merged["symbol"].nunique()) if len(merged) else 0,
            "coverage_pct": coverage,
            "validation_ok": report.ok,
            "lookahead_safe": True,
            "feature_store_version": "1.0",
        }
        self.write_manifest(manifest)
        return manifest

    def backfill_technicals_and_fundamentals(
        self,
        *,
        symbols: Optional[Sequence[str]] = None,
        factor_store: Optional[FactorScoreStore] = None,
        lookback_calendar_days: int = 730,
        sleep_s: float = 0.35,
        max_symbols: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        B1c: daily technical features + PIT fundamentals + VIX broadcast.
        """
        from research.technical_features import (
            build_technical_rows_for_symbol,
            compute_technical_frame,
            load_feature_config,
            load_or_download_daily_ohlc,
            load_vix_series,
            load_watchlist,
            ohlc_cache_dir,
        )

        cfg = load_feature_config()
        lookback = int(cfg.get("lookback_calendar_days") or lookback_calendar_days)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=lookback + 120)  # warmup for EMA/ADX
        start_s = start.isoformat()
        end_s = (end + timedelta(days=1)).isoformat()
        panel_start = (end - timedelta(days=lookback)).isoformat()

        syms = list(symbols) if symbols else load_watchlist()
        if max_symbols is not None:
            syms = syms[: int(max_symbols)]

        cache = ohlc_cache_dir(self.root)
        vix_map = load_vix_series(start=start_s, end=end_s, cache_dir=cache, sleep_s=sleep_s)

        fs = factor_store or FactorScoreStore()
        by_symbol = self._factor_series_by_symbol(fs)

        all_rows: List[Dict[str, Any]] = []
        ok_syms = 0
        fail_syms: List[str] = []
        for i, sym in enumerate(syms):
            try:
                ohlc = load_or_download_daily_ohlc(
                    sym, start=start_s, end=end_s, cache_dir=cache, sleep_s=sleep_s
                )
                tech = compute_technical_frame(
                    ohlc,
                    rsi_period=int(cfg.get("rsi_period", 14)),
                    ema_short=int(cfg.get("ema_short", 20)),
                    ema_long=int(cfg.get("ema_long", 50)),
                    atr_period=int(cfg.get("atr_period", 14)),
                    adx_period=int(cfg.get("adx_period", 14)),
                )
                rows = build_technical_rows_for_symbol(
                    sym, tech, vix_by_date=vix_map, start_date=panel_start
                )
                # Prefer watchlist symbol factors; fall back to fetch-alias key (e.g. TMPV)
                from research.fundamentals_aliases import resolve_fetch_symbol

                series = by_symbol.get(sym.upper()) or by_symbol.get(resolve_fetch_symbol(sym), [])
                for row in rows:
                    pit = self._pit_scores(series, row["date"]) if series else None
                    for k in FUNDAMENTAL_COLS:
                        row[k] = (pit or {}).get(k)
                    all_rows.append(row)
                if rows:
                    ok_syms += 1
                else:
                    fail_syms.append(sym)
            except Exception as e:
                logger = __import__("logging").getLogger("FeatureStore")
                logger.warning("Technical backfill failed for %s: %s", sym, e)
                fail_syms.append(sym)
            if (i + 1) % 10 == 0:
                __import__("logging").getLogger("FeatureStore").info(
                    "B1c progress %s/%s symbols…", i + 1, len(syms)
                )

        new_df = pd.DataFrame(all_rows)
        # Incremental merge when a subset of symbols is requested
        if symbols is not None:
            existing = self.load_panel()
            if not existing.empty:
                drop_syms = {s.upper() for s in syms}
                existing = existing[~existing["symbol"].astype(str).str.upper().isin(drop_syms)]
                merged = pd.concat([existing, new_df], ignore_index=True)
            else:
                merged = new_df
        else:
            merged = new_df
        self.save_panel(merged)

        dve = DataValidationEngine()
        report = dve.validate_feature_panel(merged if not merged.empty else pd.DataFrame())
        dve.save_report(report, self.root / "manifests" / "validation_latest.json")
        coverage = (report.stats or {}).get("coverage_pct") or {}
        manifest = {
            "mode": "technicals_and_fundamentals_b1c",
            "rows": int(len(merged)),
            "symbols_ok": ok_syms,
            "symbols_failed": fail_syms,
            "panel_start": panel_start,
            "panel_end": end.isoformat(),
            "coverage_pct": coverage,
            "validation_ok": report.ok,
            "lookahead_safe": True,
            "feature_store_version": "1.0",
            "technical_source": "yfinance_research_cache",
        }
        self.write_manifest(manifest)
        return manifest

    def get_row(self, symbol: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        panel = self.load_panel()
        if panel.empty:
            return None
        sym = symbol.upper()
        # exact date first
        mask = (panel["symbol"].astype(str).str.upper() == sym) & (panel["date"].astype(str) == str(as_of_date))
        hit = panel.loc[mask]
        if not hit.empty:
            return hit.iloc[-1].to_dict()
        # on_or_before for PIT
        sub = panel[panel["symbol"].astype(str).str.upper() == sym].copy()
        if sub.empty:
            return None
        sub["_d"] = pd.to_datetime(sub["date"], errors="coerce")
        as_ts = pd.Timestamp(as_of_date)
        sub = sub[sub["_d"] <= as_ts].sort_values("_d")
        if sub.empty:
            return None
        return sub.iloc[-1].drop(labels=["_d"], errors="ignore").to_dict()
