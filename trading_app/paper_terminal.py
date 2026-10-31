"""
Paper-only trading terminal helpers (T2/T3).

Serves the /terminal shell and overlays tariff V2/V3 on Trade Plans.
Does not place live orders, change strategies, or write broker_charges.py defaults.
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_app.paper_capital_policy import PAPER_PER_SCRIP_CAPITAL, qty_for_scrip_allocation
from trading_app.tariff_catalog import (
    AUTHORITY,
    DEFAULT_PROFILE_ID,
    DEFAULT_SLIPPAGE_PCT,
    catalog_manifest,
    preview_round_trip,
)

logger = logging.getLogger("PaperTerminal")

_ROOT = Path(__file__).resolve().parents[1]
_HTML_PATH = Path(__file__).with_name("paper_terminal.html")
_OHLC_DIR = _ROOT / "research" / "data" / "feature_store" / "ohlc_cache"


def render_terminal_html() -> str:
    return _HTML_PATH.read_text(encoding="utf-8")


def load_daily_ohlc(symbol: str, bars: int = 80) -> Dict[str, Any]:
    """Read-only local daily OHLC. Never calls Angel REST."""
    sym = str(symbol or "").strip().upper()
    path = _OHLC_DIR / f"{sym}.csv"
    if not sym or not path.is_file():
        return {
            "success": False,
            "symbol": sym,
            "bars": [],
            "error": "No local daily OHLC cache for this symbol.",
            "source": "feature_store_ohlc_cache",
        }
    take = max(int(bars or 80), 10)
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                try:
                    rows.append({
                        "date": str(raw.get("date") or ""),
                        "open": float(raw.get("open") or 0),
                        "high": float(raw.get("high") or 0),
                        "low": float(raw.get("low") or 0),
                        "close": float(raw.get("close") or 0),
                        "volume": float(raw.get("volume") or 0),
                    })
                except (TypeError, ValueError):
                    continue
    except Exception as exc:
        logger.warning("OHLC read failed for %s: %s", sym, exc)
        return {
            "success": False,
            "symbol": sym,
            "bars": [],
            "error": str(exc),
            "source": "feature_store_ohlc_cache",
        }
    rows = [r for r in rows if r["close"] > 0]
    return {
        "success": True,
        "symbol": sym,
        "bars": rows[-take:],
        "source": "feature_store_ohlc_cache",
        "path": os.path.relpath(path, _ROOT).replace("\\", "/"),
    }


def preview_ticket_charges(
    *,
    entry: float,
    exit_px: float,
    qty: int,
    direction: str = "BUY",
    segment: Optional[str] = None,
    trading_style: str = "INTRADAY",
    profile_id: Optional[str] = None,
    include_v3: bool = False,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> Dict[str, Any]:
    """Ticket qty preview plus the ₹1L-allocation qty the paper fill will actually use."""
    ticket = preview_round_trip(
        entry=entry,
        exit_px=exit_px,
        qty=qty,
        direction=direction,
        segment=segment,
        trading_style=trading_style,
        profile_id=profile_id,
        include_v3=include_v3,
        slippage_pct=slippage_pct,
    )
    fill_qty = qty_for_scrip_allocation(entry)
    fill = preview_round_trip(
        entry=entry,
        exit_px=exit_px,
        qty=fill_qty,
        direction=direction,
        segment=segment,
        trading_style=trading_style,
        profile_id=profile_id,
        include_v3=include_v3,
        slippage_pct=slippage_pct,
    )
    qty_note = (
        f"Paper fill qty is floor(₹{PAPER_PER_SCRIP_CAPITAL:,.0f} / LTP) = {fill_qty}, "
        f"not the ticket qty {int(qty or 0)}."
        if int(qty or 0) != int(fill_qty)
        else f"Paper fill qty matches ticket ({fill_qty} = ₹{PAPER_PER_SCRIP_CAPITAL:,.0f} / LTP)."
    )
    return {
        "authority": AUTHORITY,
        "manifest": catalog_manifest(),
        "ticket": ticket.to_dict(),
        "fill": fill.to_dict(),
        "fill_qty": int(fill_qty),
        "qty_note": qty_note,
        "v2_line": (
            f"V2 charges (ticket qty {ticket.qty}): ₹{ticket.v2_charges:,.2f} · "
            f"at fill qty {fill_qty}: ₹{fill.v2_charges:,.2f}"
        ),
        "v3_line": (
            f"V3 +{float(slippage_pct):g}% slip scenario: ₹{fill.v3_charges:,.2f} at fill qty"
            if include_v3
            else "V3 slippage off (not a tariff line)."
        ),
    }


def preview_from_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = payload or {}
    include_v3 = bool(raw.get("include_v3") or raw.get("v3"))
    try:
        slip = float(raw.get("slippage_pct") if raw.get("slippage_pct") is not None else DEFAULT_SLIPPAGE_PCT)
    except (TypeError, ValueError):
        slip = DEFAULT_SLIPPAGE_PCT
    return preview_ticket_charges(
        entry=float(raw.get("entry_price") or raw.get("entry") or 0),
        exit_px=float(raw.get("exit_price") or raw.get("exit_px") or raw.get("target_price") or 0),
        qty=int(raw.get("quantity") or raw.get("qty") or 0),
        direction=str(raw.get("direction") or "BUY"),
        segment=raw.get("segment"),
        trading_style=str(raw.get("trading_style") or "INTRADAY"),
        profile_id=str(raw.get("profile_id") or DEFAULT_PROFILE_ID),
        include_v3=include_v3,
        slippage_pct=slip,
    )


def attach_plan_charge_preview(plan: Any, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw = dict(payload or {})
    raw.setdefault("entry_price", getattr(plan, "entry_price", 0))
    raw.setdefault("target_price", getattr(plan, "target_price", 0))
    raw.setdefault("quantity", getattr(plan, "quantity", 0))
    raw.setdefault("direction", getattr(plan, "direction", "BUY"))
    raw.setdefault("trading_style", getattr(plan, "trading_style", "INTRADAY"))
    return preview_from_payload(raw)
