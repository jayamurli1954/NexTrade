"""
Bulk-download historical fundamentals for NexTrade watchlist stocks.

Primary: Screener.in (quarterly P&L, annual P&L/BS/CF, ratios, shareholding).
Fallback / supplement: NSE Integrated Filing XBRL via nse-xbrl when Screener fails
or when --with-xbrl is set.

Resume-safe: skips symbols already saved under research/data/fundamentals/by_symbol/.

Examples:
  python -m research.download_watchlist_fundamentals
  python -m research.download_watchlist_fundamentals --with-xbrl
  python -m research.download_watchlist_fundamentals --xbrl-backfill-failures
  python -m research.download_watchlist_fundamentals --symbols RELIANCE --force
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.fundamentals_aliases import resolve_fetch_symbol
from research.fundamentals_store import FundamentalsStore, default_fundamentals_dir
from research.nse_xbrl_adapter import build_xbrl_payload, fetch_xbrl_filings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_fundamentals")


def load_watchlist(path: Path) -> List[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Watchlist must be JSON array: {path}")
    return [str(x).strip().upper() for x in raw if str(x).strip()]


def fetch_screener_payload(symbol: str, *, view: str = "consolidated", no_cache: bool = True) -> Dict[str, Any]:
    from screener_cli.parsers import balance_sheet, cash_flow, peers, profit_loss, pros_cons, quarterly, ratios, shareholding
    from screener_cli.scraper import fetch_page_with_fallback

    fetch_sym = resolve_fetch_symbol(symbol)
    soup, actual_view = fetch_page_with_fallback(fetch_sym, view, no_cache=no_cache)

    def _safe(fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            if result is None:
                return None
            if dataclasses.is_dataclass(result):
                return dataclasses.asdict(result)
            if isinstance(result, dict):
                out = {}
                for k, v in result.items():
                    if dataclasses.is_dataclass(v):
                        out[k] = dataclasses.asdict(v)
                    elif isinstance(v, list) and v and dataclasses.is_dataclass(v[0]):
                        out[k] = [dataclasses.asdict(x) for x in v]
                    else:
                        out[k] = v
                return out
            return result
        except Exception as exc:
            logger.warning("Section parse failed %s: %s", fn.__name__, exc)
            return None

    pl_result = profit_loss.parse(soup)
    pl_table = dataclasses.asdict(pl_result["table"]) if pl_result else None
    pl_growth = [dataclasses.asdict(g) for g in pl_result["growth_tables"]] if pl_result else []

    return {
        "symbol": symbol.upper(),
        "fetch_symbol": fetch_sym,
        "source": "screener.in",
        "view": actual_view,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": f"https://www.screener.in/company/{symbol.upper()}/{actual_view}/",
        "sections": {
            "quarterly_results": _safe(quarterly.parse, soup),
            "profit_loss": {"table": pl_table, "growth_tables": pl_growth},
            "balance_sheet": _safe(balance_sheet.parse, soup),
            "cash_flow": _safe(cash_flow.parse, soup),
            "ratios": _safe(ratios.parse, soup),
            "shareholding": _safe(shareholding.parse, soup),
            "pros_cons": _safe(pros_cons.parse, soup),
            "peer_comparison": _safe(peers.parse, soup, no_cache=no_cache),
        },
        "xbrl_filings": [],
    }


def attach_xbrl(payload: Dict[str, Any], *, max_filings: int = 24) -> Dict[str, Any]:
    sym = str(payload.get("symbol") or "").upper()
    fetch_sym = resolve_fetch_symbol(sym)
    filings = fetch_xbrl_filings(fetch_sym, max_filings=max_filings)
    payload["xbrl_filings"] = filings
    payload["xbrl_filing_count"] = len(filings)
    if payload.get("source") == "screener.in":
        payload["source"] = "screener.in+nse_xbrl"
    return payload


def fetch_symbol_payload(
    symbol: str,
    *,
    view: str = "consolidated",
    with_xbrl: bool = False,
    xbrl_only: bool = False,
    max_xbrl_filings: int = 24,
) -> Dict[str, Any]:
    if xbrl_only:
        fetch_sym = resolve_fetch_symbol(symbol)
        filings = fetch_xbrl_filings(fetch_sym, max_filings=max_xbrl_filings)
        payload = build_xbrl_payload(symbol, filings)
        payload["fetch_symbol"] = fetch_sym
        return payload

    payload = fetch_screener_payload(symbol, view=view, no_cache=True)
    if with_xbrl:
        try:
            payload = attach_xbrl(payload, max_filings=max_xbrl_filings)
        except Exception as exc:
            logger.warning("XBRL supplement failed for %s: %s", symbol, exc)
            payload["xbrl_error"] = str(exc)
    return payload


def run_download(
    *,
    symbols: List[str],
    store: FundamentalsStore,
    sleep_sec: float,
    force: bool,
    view: str,
    with_xbrl: bool,
    xbrl_backfill_failures: bool,
    max_xbrl_filings: int,
) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    ok = skip = fail = xbrl_fallback = 0

    for i, sym in enumerate(symbols, 1):
        if store.has_symbol(sym) and not force and not xbrl_backfill_failures:
            skip += 1
            logger.info("[%s/%s] SKIP cached %s", i, len(symbols), sym)
            continue

        # Backfill XBRL onto existing screener payload
        if xbrl_backfill_failures and store.has_symbol(sym):
            existing = store.load_symbol_payload(sym) or {}
            if existing.get("xbrl_filings"):
                skip += 1
                logger.info("[%s/%s] SKIP xbrl already present %s", i, len(symbols), sym)
                continue
            try:
                existing = attach_xbrl(existing, max_filings=max_xbrl_filings)
                store.save_symbol_payload(existing)
                ok += 1
                logger.info("[%s/%s] XBRL backfill OK %s filings=%s", i, len(symbols), sym, existing.get("xbrl_filing_count"))
            except Exception as exc:
                fail += 1
                errors.append({"symbol": sym, "error": f"xbrl_backfill: {exc}"})
                logger.warning("[%s/%s] XBRL backfill FAIL %s: %s", i, len(symbols), sym, exc)
            time.sleep(max(0.0, sleep_sec))
            continue

        try:
            payload = fetch_symbol_payload(
                sym,
                view=view,
                with_xbrl=with_xbrl,
                max_xbrl_filings=max_xbrl_filings,
            )
            store.save_symbol_payload(payload)
            ok += 1
            logger.info(
                "[%s/%s] OK %s source=%s xbrl=%s",
                i,
                len(symbols),
                sym,
                payload.get("source"),
                payload.get("xbrl_filing_count", 0),
            )
        except Exception as exc:
            # Screener failed — try NSE XBRL fallback
            try:
                fetch_sym = resolve_fetch_symbol(sym)
                filings = fetch_xbrl_filings(fetch_sym, max_filings=max_xbrl_filings)
                payload = build_xbrl_payload(sym, filings)
                payload["fetch_symbol"] = fetch_sym
                payload["screener_error"] = str(exc)
                store.save_symbol_payload(payload)
                xbrl_fallback += 1
                ok += 1
                logger.info(
                    "[%s/%s] XBRL FALLBACK OK %s filings=%s (screener: %s)",
                    i,
                    len(symbols),
                    sym,
                    len(filings),
                    exc,
                )
            except Exception as xexc:
                fail += 1
                msg = f"screener={exc}; xbrl={xexc}"
                errors.append({"symbol": sym, "error": msg})
                logger.warning("[%s/%s] FAIL %s: %s", i, len(symbols), sym, msg)
        time.sleep(max(0.0, sleep_sec))

    counts = store.rebuild_long_csvs()
    err_path = store.root / "errors.json"
    err_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")
    summary = {
        "ok": ok,
        "skip": skip,
        "fail": fail,
        "xbrl_fallback": xbrl_fallback,
        "errors": errors,
        "row_counts": counts,
    }
    logger.info("Done fundamentals download: %s", summary)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download watchlist fundamentals (Screener + NSE XBRL fallback)")
    ap.add_argument("--watchlist", default=str(ROOT / "watchlist.json"))
    ap.add_argument("--symbols", default=None, help="Comma-separated override list")
    ap.add_argument("--out", default=None, help="Fundamentals store root directory")
    ap.add_argument("--view", default="consolidated", choices=["consolidated", "standalone"])
    ap.add_argument("--sleep", type=float, default=4.0, help="Seconds between symbols (rate limit)")
    ap.add_argument("--force", action="store_true", help="Re-download even if cached")
    ap.add_argument("--with-xbrl", action="store_true", help="Attach NSE XBRL filings to every symbol (slower)")
    ap.add_argument(
        "--xbrl-backfill-failures",
        action="store_true",
        help="Add XBRL to cached symbols that do not yet have xbrl_filings",
    )
    ap.add_argument("--max-xbrl-filings", type=int, default=24, help="Max NSE filings per symbol")
    args = ap.parse_args(argv)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = load_watchlist(Path(args.watchlist))

    store = FundamentalsStore(Path(args.out) if args.out else default_fundamentals_dir())
    logger.info("Downloading fundamentals for %s symbols -> %s", len(symbols), store.root)
    run_download(
        symbols=symbols,
        store=store,
        sleep_sec=float(args.sleep),
        force=bool(args.force),
        view=args.view,
        with_xbrl=bool(args.with_xbrl),
        xbrl_backfill_failures=bool(args.xbrl_backfill_failures),
        max_xbrl_filings=int(args.max_xbrl_filings),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
