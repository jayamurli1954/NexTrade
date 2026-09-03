"""
Download NIFTY/BANKNIFTY options daily OHLC via jugaad-data into a local options store.

Research-only. Rate-limited; resume-safe (skips contracts already in the store).

Modes:
  atm       — nearest weekly ATM CE+PE (legacy ARASS path)
  calendar  — CAL-1: weekly + next-weekly + monthly (far DTE≥28), ATM±N strike grid

Examples:
  python -m research.download_nifty_options --start 2026-07-01 --end 2026-07-31 --max-contracts 8
  python -m research.download_nifty_options --mode calendar --start 2020-01-01 --end 2026-07-31
  python -m research.download_nifty_options --mode calendar --report-only
  python -m research.download_nifty_options --excel "D:/Download/Historical Data_Nifty50-BankNifty_IndiaVix.xlsx"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from research.arass.excel_index_loader import DEFAULT_INDEX_EXCEL, load_index_workbook
from research.arass.indicators import atm_strike
from research.arass.options_store import OptionsStore, contract_key, default_store_dir, normalize_options_df

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_options")

Job = Tuple[date, date, date, float, str]  # from, to, expiry, strike, CE|PE


def _parse_date(s: str) -> date:
    return pd.Timestamp(s).date()


def _business_days(start: date, end: date) -> List[date]:
    return [d.date() for d in pd.bdate_range(start=start, end=end)]


def _week_mondays(start: date, end: date) -> List[date]:
    """One planning anchor per ISO week overlapping [start, end]."""
    out: List[date] = []
    cursor = start - timedelta(days=start.weekday())
    stop = end
    while cursor <= stop:
        if cursor + timedelta(days=4) >= start:  # week overlaps range
            out.append(cursor)
        cursor += timedelta(days=7)
    return out


def _candidate_weekly_expiries(start: date, end: date) -> List[date]:
    """
    Fallback when FO bhavcopy expiry list is unavailable.
    NSE weekly often lands on Thursday; holiday shifts to Wed/Tue — include nearby weekdays.
    """
    out: Set[date] = set()
    cursor = start - timedelta(days=7)
    stop = end + timedelta(days=60)
    while cursor <= stop:
        if cursor.weekday() == 3:  # Thursday
            out.add(cursor)
            out.add(cursor - timedelta(days=1))  # Wed
            out.add(cursor - timedelta(days=2))  # Tue
        cursor += timedelta(days=1)
    return sorted(out)


def _pick_nearest_expiry(expiries: Iterable[date], asof: date) -> Optional[date]:
    future = sorted(e for e in expiries if e >= asof)
    return future[0] if future else None


def discover_expiries(asof: date, symbol: str = "NIFTY") -> List[date]:
    from jugaad_data.nse import expiry_dates

    try:
        found = sorted(
            expiry_dates(asof, instrument_type="OPTIDX", symbol=symbol.upper(), contracts=0)
        )
        if found:
            return found
    except Exception as exc:
        logger.warning("expiry_dates failed for %s: %s", asof, exc)
    return []


def fetch_contract(
    *,
    symbol: str,
    from_d: date,
    to_d: date,
    expiry: date,
    strike: float,
    option_type: str,
) -> pd.DataFrame:
    from jugaad_data.nse import derivatives_df

    df = derivatives_df(
        symbol=symbol.upper(),
        from_date=from_d,
        to_date=to_d,
        expiry_date=expiry,
        instrument_type="OPTIDX",
        strike_price=float(strike),
        option_type=option_type.upper(),
    )
    if df is None or df.empty:
        return pd.DataFrame()
    out = normalize_options_df(df)
    out["symbol"] = symbol.upper()
    return out


def _probe_valid_expiry(
    *,
    symbol: str,
    asof: date,
    candidates: List[date],
    strike: float,
    cache: dict,
) -> Optional[date]:
    """Try CE probe for candidate expiries; cache successes/failures."""
    for exp in candidates:
        if exp < asof:
            continue
        key = (symbol, exp, float(strike))
        if key in cache:
            if cache[key]:
                return exp
            continue
        try:
            df = fetch_contract(
                symbol=symbol,
                from_d=max(asof - timedelta(days=5), exp - timedelta(days=14)),
                to_d=min(asof, exp),
                expiry=exp,
                strike=strike,
                option_type="CE",
            )
            ok = not df.empty
        except Exception:
            ok = False
        cache[key] = ok
        if ok:
            return exp
    return None


def select_calendar_expiries(
    asof: date,
    candidates: Sequence[date],
    *,
    min_far_dte: int = 28,
    max_far_dte: int = 60,
) -> List[date]:
    """
    Near weekly, next weekly, and far monthly-ish (DTE >= min_far_dte).
    Returns unique sorted expiries (1–3).
    """
    future = sorted({e for e in candidates if e >= asof})
    if not future:
        return []

    near = future[0]
    mid: Optional[date] = None
    for e in future[1:]:
        dte = (e - asof).days
        if 1 <= dte <= 14 and e != near:
            mid = e
            break

    far: Optional[date] = None
    # Prefer true monthly window: first expiry with DTE in [min_far_dte, max_far_dte]
    band = [e for e in future if min_far_dte <= (e - asof).days <= max_far_dte]
    if band:
        # Prefer last Thursday-of-month style: latest in band that is a Thu/Wed/Tue
        thu_like = [e for e in band if e.weekday() <= 3]
        far = (thu_like or band)[-1]
    else:
        farther = [e for e in future if (e - asof).days >= min_far_dte]
        if farther:
            far = farther[0]

    out: List[date] = []
    for e in (near, mid, far):
        if e is not None and e not in out:
            out.append(e)
    return out


def strike_grid(atm: float, strike_step: float, width_steps: int) -> List[float]:
    w = max(0, int(width_steps))
    return [float(atm + i * strike_step) for i in range(-w, w + 1)]


def build_contract_plan(
    spot_daily: pd.DataFrame,
    *,
    symbol: str,
    start: date,
    end: date,
    strike_step: float,
    lookback_days: int = 21,
    sleep_sec: float = 0.8,
) -> List[Job]:
    """
    Legacy ATM plan: ATM from each day's close; nearest OPTIDX expiry (bhavcopy or calendar+probe).
    """
    days = _business_days(start, end)
    jobs: List[Job] = []
    seen: Set[str] = set()
    week_expiry: dict[date, Optional[date]] = {}
    calendar_fallback = _candidate_weekly_expiries(start, end)
    probe_cache: dict = {}

    for d in days:
        ts = pd.Timestamp(d)
        matches = spot_daily.index[spot_daily.index.normalize() == ts.normalize()]
        if len(matches) == 0:
            continue
        close = float(spot_daily.loc[matches[0], "close"])
        strike = float(atm_strike(close, strike_step))
        week_key = d - timedelta(days=d.weekday())

        if week_key not in week_expiry:
            exps = discover_expiries(d, symbol=symbol)
            if not exps:
                for back in range(1, 6):
                    exps = discover_expiries(d - timedelta(days=back), symbol=symbol)
                    if exps:
                        break
            candidates = exps if exps else calendar_fallback
            if not exps:
                logger.info("Using calendar expiry fallback for week of %s", week_key)
            near = [c for c in candidates if d <= c <= d + timedelta(days=10)]
            if not near:
                near = [c for c in candidates if c >= d][:4]
            exp = _probe_valid_expiry(
                symbol=symbol,
                asof=d,
                candidates=near,
                strike=strike,
                cache=probe_cache,
            )
            week_expiry[week_key] = exp
            time.sleep(max(0.0, sleep_sec))
        exp = week_expiry.get(week_key)
        if exp is None:
            continue

        from_d = max(start, exp - timedelta(days=lookback_days))
        to_d = min(end, exp)
        if from_d > to_d:
            continue
        for ot in ("CE", "PE"):
            key = contract_key(symbol, exp, strike, ot)
            if key in seen:
                continue
            seen.add(key)
            jobs.append((from_d, to_d, exp, strike, ot))
    return jobs


def build_calendar_contract_plan(
    spot_daily: pd.DataFrame,
    *,
    symbol: str,
    start: date,
    end: date,
    strike_step: float,
    strike_width_steps: int = 4,
    min_far_dte: int = 28,
    max_far_dte: int = 60,
    lookback_days: int = 45,
    sleep_sec: float = 0.8,
) -> List[Job]:
    """
    CAL-1 plan: one anchor per week → near + next weekly + far (DTE≥min_far_dte),
    ATM ± strike_width_steps for CE and PE.
    """
    jobs: List[Job] = []
    seen: Set[str] = set()
    calendar_fallback = _candidate_weekly_expiries(start, end)
    probe_cache: dict = {}

    for monday in _week_mondays(start, end):
        # Prefer Wednesday spot (mid-week); fall back across the week
        asof: Optional[date] = None
        close: Optional[float] = None
        for offset in (2, 1, 3, 0, 4):
            d = monday + timedelta(days=offset)
            if d < start or d > end:
                continue
            ts = pd.Timestamp(d)
            matches = spot_daily.index[spot_daily.index.normalize() == ts.normalize()]
            if len(matches) == 0:
                continue
            asof = d
            close = float(spot_daily.loc[matches[0], "close"])
            break
        if asof is None or close is None:
            continue

        atm = float(atm_strike(close, strike_step))
        strikes = strike_grid(atm, strike_step, strike_width_steps)

        exps = discover_expiries(asof, symbol=symbol)
        if not exps:
            for back in range(1, 6):
                exps = discover_expiries(asof - timedelta(days=back), symbol=symbol)
                if exps:
                    break
        candidates = exps if exps else calendar_fallback
        if not exps:
            logger.info("Using calendar expiry fallback for week of %s", monday)

        selected = select_calendar_expiries(
            asof, candidates, min_far_dte=min_far_dte, max_far_dte=max_far_dte
        )
        # Light probe if discovery returned nothing usable
        if not selected and candidates:
            near = [c for c in candidates if asof <= c <= asof + timedelta(days=10)][:4]
            probed = _probe_valid_expiry(
                symbol=symbol,
                asof=asof,
                candidates=near or list(candidates[:6]),
                strike=atm,
                cache=probe_cache,
            )
            if probed:
                selected = [probed]
            time.sleep(max(0.0, sleep_sec))

        if not selected:
            continue

        # Confirm far leg exists when we claim calendar coverage
        has_far = any((e - asof).days >= min_far_dte for e in selected)
        if not has_far:
            logger.debug("Week %s: no far DTE>=%s in %s", monday, min_far_dte, selected)

        for exp in selected:
            from_d = max(start, exp - timedelta(days=lookback_days))
            to_d = min(end, exp)
            if from_d > to_d:
                continue
            for strike in strikes:
                for ot in ("CE", "PE"):
                    key = contract_key(symbol, exp, strike, ot)
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append((from_d, to_d, exp, float(strike), ot))

        time.sleep(max(0.0, min(sleep_sec, 0.35)))

    return jobs


def coverage_stats(store: OptionsStore, *, symbol: str = "NIFTY", min_far_dte: int = 28) -> dict:
    """Summarize store depth for CAL-1 acceptance."""
    df = store.df
    if df is None or df.empty:
        return {
            "rows": 0,
            "symbol": symbol,
            "date_min": None,
            "date_max": None,
            "unique_strikes": 0,
            "unique_expiries": 0,
            "max_dte": None,
            "days_max_dte_ge_min_far": 0,
            "strike_days_near10_far21": 0,
        }

    sub = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    if sub.empty:
        return coverage_stats(OptionsStore.empty(store.path), symbol=symbol, min_far_dte=min_far_dte)

    sub["dte"] = (sub["expiry"] - sub["date"]).dt.days
    by_day = sub.groupby("date")["dte"]
    max_dte_by_day = by_day.max()
    days_far = int((max_dte_by_day >= min_far_dte).sum())

    # Same strike-day with near≤10 and far≥21
    strike_days = 0
    for (dt, strike), g in sub.groupby(["date", "strike"]):
        dtes = set(int(x) for x in g["dte"].tolist())
        if any(d <= 10 for d in dtes) and any(d >= 21 for d in dtes):
            strike_days += 1

    return {
        "rows": int(len(sub)),
        "symbol": symbol.upper(),
        "date_min": str(sub["date"].min().date()),
        "date_max": str(sub["date"].max().date()),
        "unique_strikes": int(sub["strike"].nunique()),
        "unique_expiries": int(sub["expiry"].nunique()),
        "max_dte": int(sub["dte"].max()) if len(sub) else None,
        "median_max_dte_per_day": float(max_dte_by_day.median()) if len(max_dte_by_day) else None,
        "days_max_dte_ge_min_far": days_far,
        "min_far_dte": min_far_dte,
        "strike_days_near10_far21": strike_days,
        "trade_days": int(sub["date"].nunique()),
    }


def run_download(
    *,
    excel_path: Path,
    symbol: str,
    start: date,
    end: date,
    store_path: Path,
    strike_step: float,
    sleep_sec: float,
    max_contracts: Optional[int],
    mode: str = "atm",
    strike_width_steps: int = 4,
    min_far_dte: int = 28,
    max_far_dte: int = 60,
    lookback_days: Optional[int] = None,
) -> OptionsStore:
    frames = load_index_workbook(excel_path, start=str(start), end=str(end))
    spot = frames[symbol.upper()]
    store = OptionsStore.load(store_path)

    if mode == "calendar":
        lb = 45 if lookback_days is None else int(lookback_days)
        jobs = build_calendar_contract_plan(
            spot,
            symbol=symbol,
            start=start,
            end=end,
            strike_step=strike_step,
            strike_width_steps=strike_width_steps,
            min_far_dte=min_far_dte,
            max_far_dte=max_far_dte,
            lookback_days=lb,
            sleep_sec=sleep_sec,
        )
    else:
        lb = 21 if lookback_days is None else int(lookback_days)
        jobs = build_contract_plan(
            spot,
            symbol=symbol,
            start=start,
            end=end,
            strike_step=strike_step,
            lookback_days=lb,
            sleep_sec=sleep_sec,
        )

    if max_contracts is not None:
        jobs = jobs[: max(0, int(max_contracts))]

    logger.info(
        "Planned %s CE/PE contract downloads (mode=%s %s %s..%s)",
        len(jobs),
        mode,
        symbol,
        start,
        end,
    )
    ok = fail = skip = 0
    dirty = 0
    save_every = 25
    for i, (from_d, to_d, exp, strike, ot) in enumerate(jobs, 1):
        if store.has_contract(symbol=symbol, expiry=pd.Timestamp(exp), strike=strike, option_type=ot):
            skip += 1
            if i % 100 == 0 or skip <= 3:
                logger.info("[%s/%s] SKIP cached %s", i, len(jobs), contract_key(symbol, exp, strike, ot))
            continue
        try:
            df = fetch_contract(
                symbol=symbol,
                from_d=from_d,
                to_d=to_d,
                expiry=exp,
                strike=strike,
                option_type=ot,
            )
            if df.empty:
                fail += 1
                logger.warning("[%s/%s] EMPTY %s", i, len(jobs), contract_key(symbol, exp, strike, ot))
            else:
                added = store.merge(df)
                dirty += 1
                ok += 1
                logger.info(
                    "[%s/%s] OK %s rows=%s added~%s",
                    i,
                    len(jobs),
                    contract_key(symbol, exp, strike, ot),
                    len(df),
                    added,
                )
                if dirty >= save_every:
                    store.save()
                    dirty = 0
                    logger.info("Checkpoint save rows=%s", len(store.df))
        except Exception as exc:
            fail += 1
            logger.warning(
                "[%s/%s] FAIL %s: %s",
                i,
                len(jobs),
                contract_key(symbol, exp, strike, ot),
                exc,
            )
        time.sleep(max(0.0, sleep_sec))

    if dirty:
        store.save()
        dirty = 0

    stats = coverage_stats(store, symbol=symbol, min_far_dte=min_far_dte)
    logger.info(
        "Done. ok=%s fail=%s skip=%s store_rows=%s path=%s coverage=%s",
        ok,
        fail,
        skip,
        len(store.df),
        store_path,
        stats,
    )
    meta_path = store_path.parent / f"{store_path.stem}_cal1_coverage.json"
    meta_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "ok": ok,
                "fail": fail,
                "skip": skip,
                "planned_jobs": len(jobs),
                "coverage": stats,
                "start": str(start),
                "end": str(end),
                "strike_width_steps": strike_width_steps if mode == "calendar" else 0,
                "min_far_dte": min_far_dte,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download index options OHLC via jugaad-data (research-only)")
    ap.add_argument("--excel", default=str(DEFAULT_INDEX_EXCEL))
    ap.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    ap.add_argument("--start", default="2026-07-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--store", default=None, help="CSV/parquet path for options store")
    ap.add_argument("--strike-step", type=float, default=50.0)
    ap.add_argument("--sleep", type=float, default=1.2, help="Seconds between NSE requests")
    ap.add_argument("--max-contracts", type=int, default=None, help="Cap downloads (smoke test)")
    ap.add_argument(
        "--mode",
        choices=["atm", "calendar"],
        default="atm",
        help="atm=nearest weekly ATM; calendar=CAL-1 weekly+monthly strike grid",
    )
    ap.add_argument(
        "--strike-width-steps",
        type=int,
        default=4,
        help="Calendar mode: ATM ± N strike steps (default 4 → 9 strikes)",
    )
    ap.add_argument("--min-far-dte", type=int, default=28, help="Far leg minimum DTE for calendar mode")
    ap.add_argument("--max-far-dte", type=int, default=60, help="Prefer far expiry within this DTE cap")
    ap.add_argument("--lookback-days", type=int, default=None, help="Bars to request before expiry")
    ap.add_argument(
        "--report-only",
        action="store_true",
        help="Print coverage stats for existing store and exit (no download)",
    )
    args = ap.parse_args(argv)

    store_path = Path(args.store) if args.store else default_store_dir() / f"{args.symbol.lower()}_options_daily.csv"

    if args.report_only:
        store = OptionsStore.load(store_path)
        stats = coverage_stats(store, symbol=args.symbol, min_far_dte=int(args.min_far_dte))
        print(json.dumps(stats, indent=2))
        return 0

    run_download(
        excel_path=Path(args.excel),
        symbol=args.symbol,
        start=_parse_date(args.start),
        end=_parse_date(args.end),
        store_path=store_path,
        strike_step=float(args.strike_step),
        sleep_sec=float(args.sleep),
        max_contracts=args.max_contracts,
        mode=str(args.mode),
        strike_width_steps=int(args.strike_width_steps),
        min_far_dte=int(args.min_far_dte),
        max_far_dte=int(args.max_far_dte),
        lookback_days=args.lookback_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
