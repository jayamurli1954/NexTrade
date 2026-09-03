"""
Normalize and persist watchlist fundamental data (Screener.in + NSE XBRL fallback).

Long-table CSVs for research joins; per-symbol JSON for full payload replay.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger("FundamentalsStore")


def default_fundamentals_dir(root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / "research" / "data" / "fundamentals"


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


def financial_table_to_long_rows(
    *,
    symbol: str,
    view: str,
    section: str,
    table: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not table:
        return []
    headers = list(table.get("headers") or [])
    unit = table.get("unit")
    period_type = table.get("period_type")
    out: List[Dict[str, Any]] = []
    for row in table.get("rows") or []:
        label = str(row.get("label") or "").strip()
        values = list(row.get("values") or [])
        row_unit = row.get("unit") or unit
        for i, period in enumerate(headers):
            val = values[i] if i < len(values) else None
            out.append(
                {
                    "symbol": symbol.upper(),
                    "view": view,
                    "section": section,
                    "period_type": period_type,
                    "period": str(period),
                    "metric": label,
                    "value": val,
                    "unit": row_unit,
                }
            )
    return out


def shareholding_to_long_rows(*, symbol: str, view: str, sh: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not sh:
        return []
    headers = list(sh.get("headers") or [])
    out: List[Dict[str, Any]] = []
    for row in sh.get("rows") or []:
        label = str(row.get("label") or "").strip()
        values = list(row.get("values") or [])
        for i, period in enumerate(headers):
            val = values[i] if i < len(values) else None
            out.append(
                {
                    "symbol": symbol.upper(),
                    "view": view,
                    "section": "shareholding",
                    "period_type": sh.get("period_type") or "quarterly",
                    "period": str(period),
                    "metric": label,
                    "value": val,
                    "unit": "%",
                }
            )
    return out


def key_metrics_row(*, symbol: str, view: str, pros_cons: Optional[Dict[str, Any]], scraped_at: str) -> Dict[str, Any]:
    km = (pros_cons or {}).get("key_metrics") or {}
    row: Dict[str, Any] = {
        "symbol": symbol.upper(),
        "view": view,
        "scraped_at": scraped_at,
    }
    row.update(km)
    return row


def payload_to_long_frames(payload: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    symbol = str(payload.get("symbol") or "").upper()
    view = str(payload.get("view") or "consolidated")
    sections = payload.get("sections") or {}
    scraped_at = str(payload.get("scraped_at") or "")

    quarterly_rows = financial_table_to_long_rows(
        symbol=symbol, view=view, section="quarterly_results", table=sections.get("quarterly_results")
    )
    pl = sections.get("profit_loss") or {}
    pnl_rows = financial_table_to_long_rows(
        symbol=symbol, view=view, section="profit_loss", table=(pl.get("table") if isinstance(pl, dict) else None)
    )
    bs_rows = financial_table_to_long_rows(
        symbol=symbol, view=view, section="balance_sheet", table=sections.get("balance_sheet")
    )
    cf_rows = financial_table_to_long_rows(
        symbol=symbol, view=view, section="cash_flow", table=sections.get("cash_flow")
    )
    ratio_rows = financial_table_to_long_rows(
        symbol=symbol, view=view, section="ratios", table=sections.get("ratios")
    )
    sh_rows = shareholding_to_long_rows(symbol=symbol, view=view, sh=sections.get("shareholding"))

    km = key_metrics_row(
        symbol=symbol,
        view=view,
        pros_cons=sections.get("pros_cons"),
        scraped_at=scraped_at,
    )

    xbrl_rows: List[Dict[str, Any]] = []
    if payload.get("xbrl_filings"):
        from research.nse_xbrl_adapter import xbrl_filings_to_long_rows

        xbrl_rows = xbrl_filings_to_long_rows(symbol, payload.get("xbrl_filings") or [])

    return {
        "quarterly_pnl": pd.DataFrame(quarterly_rows),
        "pnl_annual": pd.DataFrame(pnl_rows),
        "balance_sheet_annual": pd.DataFrame(bs_rows),
        "cash_flow_annual": pd.DataFrame(cf_rows),
        "ratios_annual": pd.DataFrame(ratio_rows),
        "shareholding_quarterly": pd.DataFrame(sh_rows),
        "key_metrics": pd.DataFrame([km]) if km else pd.DataFrame(),
        "nse_xbrl_fundamentals": pd.DataFrame(xbrl_rows),
    }


class FundamentalsStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.by_symbol = self.root / "by_symbol"
        self.long_dir = self.root / "long"
        self.by_symbol.mkdir(parents=True, exist_ok=True)
        self.long_dir.mkdir(parents=True, exist_ok=True)

    def symbol_path(self, symbol: str) -> Path:
        return self.by_symbol / f"{symbol.upper()}.json"

    def has_symbol(self, symbol: str) -> bool:
        return self.symbol_path(symbol).exists()

    def save_symbol_payload(self, payload: Dict[str, Any]) -> None:
        sym = str(payload.get("symbol") or "").upper()
        path = self.symbol_path(sym)
        path.write_text(json.dumps(payload, default=_json_default, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_symbol_payload(self, symbol: str) -> Optional[Dict[str, Any]]:
        path = self.symbol_path(symbol)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def rebuild_long_csvs(self) -> Dict[str, int]:
        """Rebuild combined long CSVs from all per-symbol JSON files."""
        frames: Dict[str, List[pd.DataFrame]] = {
            "quarterly_pnl": [],
            "pnl_annual": [],
            "balance_sheet_annual": [],
            "cash_flow_annual": [],
            "ratios_annual": [],
            "shareholding_quarterly": [],
            "key_metrics": [],
            "nse_xbrl_fundamentals": [],
        }
        symbols: List[str] = []
        sources: Dict[str, str] = {}
        for path in sorted(self.by_symbol.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sym = path.stem.upper()
            symbols.append(sym)
            sources[sym] = str(payload.get("source") or "screener.in")
            parts = payload_to_long_frames(payload)
            for key, df in parts.items():
                if df is not None and not df.empty:
                    frames[key].append(df)

        counts: Dict[str, int] = {}
        for key, parts in frames.items():
            if parts:
                merged = pd.concat(parts, ignore_index=True)
            else:
                merged = pd.DataFrame()
            out = self.long_dir / f"{key}.csv"
            merged.to_csv(out, index=False)
            counts[key] = int(len(merged))

        manifest = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": sorted(symbols),
            "symbol_count": len(symbols),
            "sources_by_symbol": sources,
            "row_counts": counts,
            "source_note": "Primary: screener.in via screenercli. Fallback/supplement: nse-xbrl (NSE Integrated Filing XBRL).",
            "note": "Research-only. Respect rate limits; not for live trading authority.",
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return counts
