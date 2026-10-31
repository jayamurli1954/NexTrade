"""
NSE Integrated Filing XBRL adapter (nse-xbrl) — fallback when Screener.in fails.

Requires NSE session cookies for reliable access (optional):
  set NSE_COOKIE env var to browser Cookie header from nseindia.com

Issuer name resolved via jugaad-data NSELive quote metadata.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("NseXbrlAdapter")

# Metrics exported per filing into long-table research store (values in INR absolute)
XBRL_METRIC_GROUPS: Dict[str, List[str]] = {
    "quarterly_pnl": [
        "q_revenue",
        "q_total_income",
        "q_ebit",
        "q_pbt",
        "q_pat",
        "q_basic_eps",
        "q_diluted_eps",
    ],
    "ytd_pnl": [
        "ytd_revenue",
        "ytd_total_income",
        "ytd_ebit",
        "ytd_pbt",
        "ytd_pat",
        "ytd_basic_eps",
        "ytd_diluted_eps",
    ],
    "balance_sheet": [
        "bs_total_assets",
        "bs_total_liabilities",
        "bs_equity",
        "bs_current_assets",
        "bs_current_liabilities",
        "bs_noncurrent_assets",
        "bs_noncurrent_liabilities",
        "bs_inventories",
        "bs_trade_receivables",
        "bs_trade_payables",
    ],
    "cash_flow": [
        "cf_capex",
        "cf_dividends_paid",
        "cf_tax_paid",
        "cf_net_change_in_cash",
    ],
}


def resolve_nse_company_name(symbol: str) -> str:
    """Resolve NSE registered issuer name for integrated filing API."""
    from research.fundamentals_aliases import resolve_fetch_symbol

    sym = resolve_fetch_symbol(symbol)
    try:
        from jugaad_data.nse import NSELive

        quote = NSELive().stock_quote(sym)
        meta = quote.get("info") or quote.get("metaData") or quote.get("metadata") or {}
        name = meta.get("companyName") or quote.get("companyName")
        if name:
            return str(name).strip()
    except Exception as exc:
        logger.warning("NSELive company name lookup failed for %s: %s", sym, exc)
    raise RuntimeError(f"Could not resolve NSE issuer name for {sym} (from {symbol.upper()})")


def _filing_to_dict(filing: Any) -> Dict[str, Any]:
    if dataclasses.is_dataclass(filing):
        return dataclasses.asdict(filing)
    if isinstance(filing, dict):
        return filing
    raise TypeError(f"Unsupported filing type: {type(filing)}")


def fetch_xbrl_filings(
    symbol: str,
    *,
    issuer: Optional[str] = None,
    max_filings: Optional[int] = 24,
    cookie_string: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch parsed NSE Integrated Filing XBRL results for symbol.
    Returns list of filing dicts (newest first from NSE listing).
    """
    from nse_xbrl import NSEClient

    from research.fundamentals_aliases import resolve_fetch_symbol

    fetch_sym = resolve_fetch_symbol(symbol)
    sym = fetch_sym.upper().strip()
    issuer_name = issuer or resolve_nse_company_name(symbol)
    cookie = cookie_string or os.environ.get("NSE_COOKIE") or None
    client = NSEClient(cookie_string=cookie)

    filings = client.fetch_financials(sym, issuer_name, max_filings=max_filings)
    if not filings:
        raise RuntimeError(
            f"No NSE XBRL filings returned for {sym} ({issuer_name}). "
            "Set NSE_COOKIE from browser if blocked."
        )
    return [_filing_to_dict(f) for f in filings]


def xbrl_filings_to_long_rows(symbol: str, filings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten XBRL filings to long rows (value_inr + value_cr)."""
    sym = symbol.upper()
    rows: List[Dict[str, Any]] = []
    for filing in filings or []:
        period_end = filing.get("period_end")
        period_label = period_end.isoformat() if isinstance(period_end, date) else str(period_end or "")
        seq_id = str(filing.get("seq_id") or "")
        consolidated = bool(filing.get("is_consolidated"))
        for section, metrics in XBRL_METRIC_GROUPS.items():
            for metric in metrics:
                val = filing.get(metric)
                if val is None:
                    continue
                try:
                    val_f = float(val)
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "source": "nse_xbrl",
                        "section": section,
                        "period": period_label,
                        "period_type": "quarterly" if section == "quarterly_pnl" else "annual",
                        "metric": metric,
                        "value_inr": val_f,
                        "value_cr": round(val_f / 1e7, 4),
                        "unit": "INR_absolute",
                        "seq_id": seq_id,
                        "is_consolidated": consolidated,
                        "company_name": filing.get("company_name"),
                    }
                )
        # Computed ratios when possible
        try:
            from nse_xbrl.models import FilingResult

            fr = FilingResult(**{k: v for k, v in filing.items() if k in {f.name for f in dataclasses.fields(FilingResult)}})
            for metric, val in (
                ("debt_equity_ratio", fr.debt_equity_ratio),
                ("book_value_per_share", fr.book_value_per_share),
                ("q_ebitda", fr.q_ebitda),
                ("ytd_ebitda", fr.ytd_ebitda),
            ):
                if val is None:
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "source": "nse_xbrl",
                        "section": "computed_ratios",
                        "period": period_label,
                        "period_type": "point_in_time",
                        "metric": metric,
                        "value_inr": float(val),
                        "value_cr": None,
                        "unit": "ratio_or_inr",
                        "seq_id": seq_id,
                        "is_consolidated": consolidated,
                        "company_name": filing.get("company_name"),
                    }
                )
        except Exception:
            pass
    return rows


def build_xbrl_payload(symbol: str, filings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Minimal symbol payload when Screener is unavailable."""
    from datetime import datetime, timezone

    return {
        "symbol": symbol.upper(),
        "source": "nse_xbrl",
        "view": "consolidated" if any(f.get("is_consolidated") for f in filings) else "standalone",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://www.nseindia.com/companies-listing/corporate-integrated-filing",
        "sections": {},
        "xbrl_filings": filings,
        "xbrl_filing_count": len(filings),
    }
