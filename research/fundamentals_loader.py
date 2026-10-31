"""
Load normalized fundamentals for analyzer / opportunity cards from local research store.

Primary: per-symbol JSON under research/data/fundamentals/by_symbol/
Fallback symbols: research.fundamentals_aliases.resolve_fetch_symbol
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from research.fundamentals_aliases import resolve_fetch_symbol
from research.fundamentals_store import FundamentalsStore, default_fundamentals_dir

_MONTH_ORDER = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "—"}:
        return None
    text = text.replace(",", "").replace("₹", "").replace("Cr.", "").replace("Cr", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_pct(value: Any) -> Optional[float]:
    """Return percentage as a number (e.g. 10.3 for 10.3%)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v * 100.0 if 0 < v <= 1.0 else v
    text = str(value).strip().replace("%", "")
    return _parse_number(text)


def _period_sort_key(period: str) -> Tuple[int, int]:
    parts = str(period).strip().split()
    if len(parts) != 2:
        return (0, 0)
    month, year_s = parts[0], parts[1]
    try:
        year = int(year_s)
    except ValueError:
        year = 0
    return (year, _MONTH_ORDER.get(month, 0))


def _table_row_map(table: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    if not table:
        return {}
    headers = list(table.get("headers") or [])
    out: Dict[str, Dict[str, float]] = {}
    for row in table.get("rows") or []:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        values = list(row.get("values") or [])
        period_map: Dict[str, float] = {}
        for i, period in enumerate(headers):
            if i >= len(values):
                continue
            val = _parse_number(values[i])
            if val is not None:
                period_map[str(period)] = val
        if period_map:
            out[label] = period_map
    return out


def _latest_two_periods(period_map: Dict[str, float]) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    if not period_map:
        return None, None, None
    ordered = sorted(period_map.items(), key=lambda kv: _period_sort_key(kv[0]))
    if len(ordered) == 1:
        period, val = ordered[-1]
        return period, val, None
    p2, v2 = ordered[-1]
    _, v1 = ordered[-2]
    return p2, v2, v1


def _yoy_growth(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior)


def _payload_to_fundamentals(payload: Dict[str, Any]) -> Dict[str, Any]:
    sections = payload.get("sections") or {}
    km = ((sections.get("pros_cons") or {}).get("key_metrics") or {})

    pe = _parse_number(km.get("Stock P/E"))
    roe = _parse_pct(km.get("ROE"))
    roce = _parse_pct(km.get("ROCE"))
    dividend_yield = _parse_pct(km.get("Dividend Yield"))
    if dividend_yield is not None:
        dividend_yield = dividend_yield / 100.0

    pl_table = ((sections.get("profit_loss") or {}).get("table") if isinstance(sections.get("profit_loss"), dict) else None)
    pl_rows = _table_row_map(pl_table)
    sales_map = pl_rows.get("Sales") or pl_rows.get("Revenue") or {}
    profit_map = pl_rows.get("Net Profit") or pl_rows.get("Profit after tax") or {}

    _, sales_latest, sales_prior = _latest_two_periods(sales_map)
    sales_period, pat_latest, pat_prior = _latest_two_periods(profit_map)
    revenue_growth = _yoy_growth(sales_latest, sales_prior)
    profit_growth = _yoy_growth(pat_latest, pat_prior)

    profit_margin = None
    if pat_latest is not None and sales_latest and sales_latest > 0:
        profit_margin = pat_latest / sales_latest

    bs_rows = _table_row_map(sections.get("balance_sheet"))
    borrow_map = bs_rows.get("Borrowings") or {}
    equity_cap_map = bs_rows.get("Equity Capital") or {}
    reserves_map = bs_rows.get("Reserves") or {}

    debt_to_equity = None
    if borrow_map:
        bs_period, borrowings, _ = _latest_two_periods(borrow_map)
        equity_cap = equity_cap_map.get(bs_period) if bs_period else None
        reserves = reserves_map.get(bs_period) if bs_period else None
        if borrowings is not None and equity_cap is not None and reserves is not None:
            equity = equity_cap + reserves
            if equity > 0:
                debt_to_equity = borrowings / equity

    return {
        "pe_ratio": pe,
        "pb_ratio": None,
        "debt_to_equity": debt_to_equity,
        "roe": (roe / 100.0) if roe is not None else None,
        "roce_pct": roce,
        "profit_margin": profit_margin,
        "revenue_growth": revenue_growth,
        "profit_growth": profit_growth,
        "dividend_yield": dividend_yield,
        "market_cap": None,
        "current_ratio": None,
        "quick_ratio": None,
        "sales_period": sales_period,
        "pat_latest_cr": pat_latest,
        "sales_latest_cr": sales_latest,
        "_source": "local",
    }


def build_fundamentals_highlights(fundamentals: Dict[str, Any], source: str = "local") -> List[str]:
    """Short bullets for NexTrade opportunity cards."""
    if not fundamentals:
        return []

    lines: List[str] = []
    pe = fundamentals.get("pe_ratio")
    roce = fundamentals.get("roce_pct")
    if roce is None:
        roe_raw = fundamentals.get("roe")
        roce = (roe_raw * 100.0) if roe_raw is not None and roe_raw <= 1 else roe_raw
    roe = fundamentals.get("roe")
    roe_pct = (roe * 100.0) if roe is not None and roe <= 1 else roe

    metric_bits: List[str] = []
    if pe is not None:
        metric_bits.append(f"P/E {pe:.1f}")
    if roce is not None:
        metric_bits.append(f"ROCE {roce:.1f}%")
    if roe_pct is not None:
        metric_bits.append(f"ROE {roe_pct:.1f}%")
    if metric_bits:
        tag = "Fundamentals" if source == "local" else "Fundamentals (Yahoo)"
        lines.append(f"{tag}: {', '.join(metric_bits)}")

    rg = fundamentals.get("revenue_growth")
    if rg is not None:
        period = fundamentals.get("sales_period") or "latest FY"
        lines.append(f"Sales growth {rg * 100:+.1f}% YoY ({period})")

    pg = fundamentals.get("profit_growth")
    if pg is not None:
        lines.append(f"PAT growth {pg * 100:+.1f}% YoY")

    dte = fundamentals.get("debt_to_equity")
    if dte is not None:
        if dte <= 0.5:
            lines.append(f"Low leverage (D/E {dte:.2f})")
        elif dte >= 2.0:
            lines.append(f"High leverage (D/E {dte:.2f})")

    dy = fundamentals.get("dividend_yield")
    if dy is not None and dy >= 0.02:
        lines.append(f"Dividend yield {dy * 100:.1f}%")

    return lines[:3]


def load_fundamentals_from_store(symbol: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    store = FundamentalsStore(default_fundamentals_dir(root))
    candidates = [symbol.upper().strip()]
    alt = resolve_fetch_symbol(symbol)
    if alt not in candidates:
        candidates.append(alt)

    for sym in candidates:
        payload = store.load_symbol_payload(sym)
        if payload:
            return _payload_to_fundamentals(payload)
    return None
