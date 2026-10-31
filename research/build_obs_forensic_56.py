#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OBS-FORENSIC-56 — read-only root-cause matrix builder.

No strategy / scoring / risk / gate changes.
Joins trading log + fill integrity + daily recommendation audit + daily OHLC proxy.

Usage:
  python -m research.build_obs_forensic_56
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ObsForensic56")

LOG_XLSX = ROOT / "reports" / "NexTrade_Trading_Log_20260813_152345_16952.xlsx"
FILL_JSONL = ROOT / "reports" / "phase_7p_fill_integrity_log.jsonl"
AUDIT_JSON = ROOT / "reports" / "daily_recommendation_audit_log.json"
OHLC_DIR = ROOT / "research" / "data" / "feature_store" / "ohlc_cache"
OUT_XLSX = ROOT / "reports" / "OBS_FORENSIC_56_RootCause_Matrix_20260813.xlsx"
OUT_JSON = ROOT / "reports" / "OBS_FORENSIC_56_RootCause_Matrix_20260813.json"

STRATEGY_CLASS = {
    "Golden Ratio Scan": "INVESTIGATE",
    "Momentum Breakdown": "INVESTIGATE",
    "Oversold Bounce": "INVESTIGATE",
    "Momentum Continuation": "KEEP_WATCH",
}


def _load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Executed Trades", header=3)
    df = df.dropna(subset=["Trade ID"]).copy()
    df["Trade ID"] = df["Trade ID"].astype(str)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    for c in ["Qty", "Entry Price (INR)", "Exit Price (INR)", "Gross P&L (INR)", "Est. Charges (INR)", "Est. Net P&L (INR)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _load_fills(path: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        tid = str(rec.get("trade_id") or "")
        if not tid:
            continue
        # keep richest record if duplicates
        prev = out.get(tid)
        if prev is None or len(json.dumps(rec)) > len(json.dumps(prev)):
            out[tid] = rec
    return out


def _load_audit_by_day(path: Path) -> Dict[str, Dict[str, Any]]:
    """Day-level recommendation snapshot (not per-trade)."""
    by_day: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return by_day
    rows = json.loads(path.read_text(encoding="utf-8"))
    for r in rows:
        ts = str(r.get("timestamp") or r.get("date") or "")
        day = ts[:10]
        if len(day) < 10:
            continue
        # last recommendation of the day wins
        by_day[day] = r
    return by_day


def _load_daily_ohlc(symbol: str) -> Optional[pd.DataFrame]:
    p = OHLC_DIR / f"{symbol.upper()}.csv"
    if not p.exists():
        # hyphen variants
        for q in OHLC_DIR.glob("*.csv"):
            if q.stem.upper().replace("-", "") == symbol.upper().replace("-", ""):
                p = q
                break
        else:
            return None
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).set_index("date").sort_index()


def _estimate_exit_ts(entry: pd.Timestamp, exit_reason: str) -> Tuple[pd.Timestamp, str]:
    reason = str(exit_reason or "")
    day = entry.normalize()
    if "SQUARE_OFF" in reason.upper() or "15:15" in reason:
        return day + pd.Timedelta(hours=15, minutes=15), "ASSUMED_SQUARE_OFF_15:15"
    if "PAPER_KILL" in reason.upper():
        return entry + pd.Timedelta(minutes=30), "ASSUMED_KILL_PLUS_30M"
    if "DAY_LOSS" in reason.upper() or "DAY_PROFIT" in reason.upper():
        return day + pd.Timedelta(hours=15, minutes=15), "ASSUMED_DAY_RISK_FLAT"
    if "MANUAL" in reason.upper():
        return day + pd.Timedelta(hours=15, minutes=15), "ASSUMED_EOD_PROXY"
    if "STOP" in reason.upper() or "TARGET" in reason.upper():
        return day + pd.Timedelta(hours=15, minutes=15), "ASSUMED_EOD_PROXY_NO_EXACT_EXIT_TS"
    return day + pd.Timedelta(hours=15, minutes=15), "ASSUMED_EOD_PROXY"


def _mfe_mae_daily_proxy(
    *,
    symbol: str,
    direction: str,
    entry: float,
    exit_px: float,
    entry_ts: pd.Timestamp,
    ohlc_cache: Dict[str, pd.DataFrame],
) -> Dict[str, Any]:
    df = ohlc_cache.get(symbol.upper())
    if df is None:
        df_loaded = _load_daily_ohlc(symbol)
        if df_loaded is not None:
            ohlc_cache[symbol.upper()] = df_loaded
            df = df_loaded
    if df is None or entry_ts.normalize() not in df.index:
        return {
            "mfe_pct": None,
            "mae_pct": None,
            "mfe_mae_basis": "UNAVAILABLE",
            "day_high": None,
            "day_low": None,
            "counterfactual_note": "No local daily OHLC for trade date",
        }
    row = df.loc[entry_ts.normalize()]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    hi = float(row["high"])
    lo = float(row["low"])
    side = str(direction).upper()
    if side == "BUY":
        mfe = (hi - entry) / entry * 100.0 if entry else None
        mae = (lo - entry) / entry * 100.0 if entry else None
        # if stop-like: did price go favourable after adverse?
        recovered = hi > entry and exit_px < entry
    else:  # SELL
        mfe = (entry - lo) / entry * 100.0 if entry else None
        mae = (entry - hi) / entry * 100.0 if entry else None
        recovered = lo < entry and exit_px > entry

    return {
        "mfe_pct": round(mfe, 3) if mfe is not None else None,
        "mae_pct": round(mae, 3) if mae is not None else None,
        "mfe_mae_basis": "COARSE_DAILY_OHLC_PROXY",
        "day_high": round(hi, 4),
        "day_low": round(lo, 4),
        "favourable_then_loss_flag": bool(recovered),
        "counterfactual_note": (
            "Daily high/low proxy only — true intraday MFE/MAE needs Jul–Aug 2026 5m bars"
            if True
            else ""
        ),
    }


def _exit_bucket(reason: str) -> str:
    r = str(reason or "").upper()
    if "STOP" in r:
        return "STOP"
    if "TARGET" in r:
        return "TARGET"
    if "SQUARE_OFF" in r:
        return "TIME_FLAT"
    if "DAY_LOSS" in r:
        return "RISK_DAY_LOSS"
    if "DAY_PROFIT" in r:
        return "RISK_DAY_PROFIT"
    if "PAPER_KILL" in r:
        return "OPS_KILL"
    if "MANUAL" in r:
        return "MANUAL"
    return "OTHER"


def _diagnose_row(row: Dict[str, Any]) -> str:
    """Heuristic trade diagnosis — not a strategy change recommendation."""
    net = float(row.get("net_pnl") or 0)
    gross = float(row.get("gross_pnl") or 0)
    bucket = row.get("exit_bucket")
    mfe = row.get("mfe_pct")
    mae = row.get("mae_pct")
    dq = row.get("data_quality_passed")
    auth = str(row.get("data_authority") or "")

    if dq is False or (auth and auth not in ("ANGEL_WS_LIVE", "ANGEL_WEBSOCKET", "")):
        return "UNCERTAIN_DATA"
    if bucket == "OPS_KILL":
        return "UNCERTAIN_OPS"
    if bucket == "MANUAL":
        return "UNCERTAIN_MANUAL"
    if bucket == "RISK_DAY_LOSS":
        return "RISK_LAYER"
    if bucket == "STOP" and mfe is not None and mfe > 0.4 and gross < 0:
        return "EXIT_SUSPECT_GOOD_EXCURSION"
    if bucket == "TIME_FLAT" and mfe is not None and mae is not None:
        if abs(mae) > abs(mfe) * 1.5 and gross < 0:
            return "SIGNAL_OR_HOLD_SUSPECT"
        if mfe > 0.5 and gross < 0:
            return "EXIT_TIMING_SUSPECT"
    if gross > 0 and bucket == "TARGET":
        return "GOOD_SIGNAL_EXIT"
    if gross > 0:
        return "GOOD_OUTCOME"
    if gross < 0:
        return "BAD_OUTCOME_NEEDS_CONTEXT"
    return "UNCERTAIN"


def build_matrix(
    trades: pd.DataFrame,
    fills: Dict[str, Dict[str, Any]],
    audit_by_day: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    ohlc_cache: Dict[str, pd.DataFrame] = {}
    rows: List[Dict[str, Any]] = []

    for _, t in trades.iterrows():
        tid = str(t["Trade ID"])
        entry_ts = pd.Timestamp(t["Timestamp"])
        day = entry_ts.strftime("%Y-%m-%d")
        fill = fills.get(tid, {})
        audit = audit_by_day.get(day, {})
        exit_reason = str(t.get("Exit Reason") or "")
        exit_ts, exit_ts_basis = _estimate_exit_ts(entry_ts, exit_reason)
        hold_min = (exit_ts - entry_ts).total_seconds() / 60.0

        direction = str(t.get("Direction") or "")
        entry = float(t["Entry Price (INR)"])
        exit_px = float(t["Exit Price (INR)"])
        symbol = str(t["Symbol"])
        mfe = _mfe_mae_daily_proxy(
            symbol=symbol,
            direction=direction,
            entry=entry,
            exit_px=exit_px,
            entry_ts=entry_ts,
            ohlc_cache=ohlc_cache,
        )

        auth = fill.get("data_authority") or (
            "ANGEL_WS_LIVE"
            if "ANGEL_WS_LIVE" in str(fill.get("quote_quality") or "")
            else fill.get("fill_price_source")
        )
        age = fill.get("quote_age_ms")
        if age is None and fill.get("age_sec") is not None:
            age = float(fill["age_sec"]) * 1000.0

        alts = audit.get("alternative_strategies") or []
        alt_names = []
        if isinstance(alts, list):
            for a in alts[:5]:
                if isinstance(a, dict):
                    alt_names.append(str(a.get("strategy") or a.get("name") or a))
                else:
                    alt_names.append(str(a))

        row = {
            "trade_id": tid,
            "symbol": symbol,
            "strategy": str(t.get("Strategy") or ""),
            "style": str(t.get("Style") or ""),
            "direction": direction,
            "qty": int(t["Qty"]) if pd.notna(t["Qty"]) else None,
            "entry_ts": str(entry_ts),
            "entry_price": entry,
            "exit_ts_estimated": str(exit_ts),
            "exit_ts_basis": exit_ts_basis,
            "exit_price": exit_px,
            "holding_minutes_est": round(hold_min, 1),
            "exit_reason": exit_reason,
            "exit_bucket": _exit_bucket(exit_reason),
            "stop_hit": "STOP" in exit_reason.upper(),
            "target_hit": "TARGET" in exit_reason.upper() and "DAY_PROFIT" not in exit_reason.upper(),
            "gross_pnl": float(t["Gross P&L (INR)"] or 0),
            "costs_est": float(t["Est. Charges (INR)"] or 0),
            "net_pnl": float(t["Est. Net P&L (INR)"] or 0),
            "fill_price_source": fill.get("fill_price_source"),
            "data_authority": auth,
            "quote_age_ms": age,
            "data_quality_passed": fill.get("data_quality_passed"),
            "data_quality": fill.get("data_quality") or ("PASS" if fill.get("data_quality_passed") else None),
            "oie_exception": fill.get("oie_exception"),
            "fill_join": "JOINED" if fill else "MISSING_FILL_LOG",
            "day_predicted_regime": audit.get("predicted_regime"),
            "day_regime_confidence_pct": audit.get("regime_confidence_pct"),
            "day_suitability_score": audit.get("suitability_score"),
            "day_recommended_strategy": audit.get("recommended_strategy_name"),
            "day_recommended_strategy_id": audit.get("recommended_strategy_id"),
            "day_alternatives": " | ".join(alt_names) if alt_names else None,
            "day_audit_join": "JOINED" if audit else "MISSING_DAY_AUDIT",
            "counterfactual_alt_pnl": None,  # requires replay; not inventable
            "counterfactual_status": "NOT_COMPUTED_NEEDS_REPLAY",
            **mfe,
            "strategy_class_preliminary": STRATEGY_CLASS.get(str(t.get("Strategy") or ""), "INVESTIGATE"),
        }
        row["trade_diagnosis"] = _diagnose_row(row)
        rows.append(row)
    return rows


def _summaries(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    df = pd.DataFrame(rows)

    def slice_stats(sub: pd.DataFrame, name: str) -> Dict[str, Any]:
        g = sub["gross_pnl"]
        wins = g[g > 0]
        losses = g[g < 0]
        pf = float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else None
        return {
            "slice": name,
            "trades": int(len(sub)),
            "win_rate_pct": round(100.0 * len(wins) / len(sub), 1) if len(sub) else 0,
            "gross": round(float(g.sum()), 2),
            "net": round(float(sub["net_pnl"].sum()), 2),
            "costs": round(float(sub["costs_est"].sum()), 2),
            "pf_gross": round(pf, 3) if pf is not None else None,
            "avg_win": round(float(wins.mean()), 2) if len(wins) else 0,
            "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0,
        }

    by_strategy = [slice_stats(sub, str(s)) for s, sub in df.groupby("strategy")]
    by_exit = [slice_stats(sub, str(s)) for s, sub in df.groupby("exit_bucket")]
    by_diag = [slice_stats(sub, str(s)) for s, sub in df.groupby("trade_diagnosis")]
    by_regime = [slice_stats(sub, str(s)) for s, sub in df.groupby(df["day_predicted_regime"].fillna("UNKNOWN"))]

    fill_ok = int((df["fill_join"] == "JOINED").sum())
    dq_pass = int(df["data_quality_passed"].fillna(False).astype(bool).sum())

    # preliminary keep/modify/retire/investigate at strategy level
    classifications = []
    for s, sub in df.groupby("strategy"):
        st = slice_stats(sub, str(s))
        verdict = STRATEGY_CLASS.get(str(s), "INVESTIGATE")
        rationale = []
        if st["trades"] < 5:
            rationale.append("sample_too_small")
            verdict = "KEEP_WATCH"
        if st.get("pf_gross") is not None and st["pf_gross"] < 0.85 and st["trades"] >= 8:
            rationale.append("pf_below_0.85")
            verdict = "INVESTIGATE"
        if str(s) == "Golden Ratio Scan" and st["trades"] >= 20 and abs(st["gross"]) < 500:
            rationale.append("high_volume_near_breakeven_before_costs")
            verdict = "INVESTIGATE"
        if str(s) == "Momentum Breakdown" and st["win_rate_pct"] >= 50 and (st.get("pf_gross") or 0) < 1:
            rationale.append("asymmetric_payoff")
            verdict = "INVESTIGATE"
        classifications.append(
            {
                "strategy": s,
                "classification": verdict,
                "rationale": rationale,
                **{k: v for k, v in st.items() if k != "slice"},
                "freeze_note": "Do NOT modify until root-cause matrix reviewed + explicit unfreeze",
            }
        )

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_log": str(LOG_XLSX),
        "overall": slice_stats(df, "ALL"),
        "fill_joined": fill_ok,
        "data_quality_pass_count": dq_pass,
        "mfe_mae_note": "COARSE daily OHLC proxy only; Jul–Aug 2026 5m not in Kaggle store",
        "counterfactual_note": "Alternative strategy P&L not inventable without replay engine",
        "by_strategy": by_strategy,
        "by_exit_bucket": by_exit,
        "by_diagnosis": by_diag,
        "by_day_regime": by_regime,
        "strategy_classifications": classifications,
        "unfreeze_recommendation": "DO_NOT_UNFREEZE_STRATEGY_LAYER",
        "unfreeze_rationale": [
            "Sample still small (56 trades / ~12 days)",
            "Exact exit timestamps missing for MAE/MFE precision",
            "Counterfactual replay not yet computed",
            "Exit/risk layers (stop, day-loss, square-off) materially affect P&L",
            "Continue OBS-FORENSIC-56 evidence gathering only",
        ],
    }


def write_excel(rows: List[Dict[str, Any]], summary: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    master = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        master.to_excel(xl, sheet_name="TRADE_MATRIX", index=False)
        pd.DataFrame(summary["by_strategy"]).to_excel(xl, sheet_name="BY_STRATEGY", index=False)
        pd.DataFrame(summary["by_exit_bucket"]).to_excel(xl, sheet_name="BY_EXIT", index=False)
        pd.DataFrame(summary["by_diagnosis"]).to_excel(xl, sheet_name="BY_DIAGNOSIS", index=False)
        pd.DataFrame(summary["by_day_regime"]).to_excel(xl, sheet_name="BY_DAY_REGIME", index=False)
        pd.DataFrame(summary["strategy_classifications"]).to_excel(xl, sheet_name="KEEP_MODIFY_RETIRE", index=False)
        pd.DataFrame(
            [
                {"Item": "Freeze", "Detail": "Strategy/exit/scoring/risk LOCKED"},
                {"Item": "Unfreeze recommendation", "Detail": summary["unfreeze_recommendation"]},
                {"Item": "Rationale", "Detail": "; ".join(summary["unfreeze_rationale"])},
                {"Item": "MFE/MAE", "Detail": summary["mfe_mae_note"]},
                {"Item": "Counterfactual", "Detail": summary["counterfactual_note"]},
                {"Item": "Fill join", "Detail": f"{summary['fill_joined']}/{summary['overall']['trades']}"},
                {"Item": "Generated_UTC", "Detail": summary["generated_utc"]},
            ]
        ).to_excel(xl, sheet_name="METHODOLOGY", index=False)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OBS-FORENSIC-56 root-cause matrix (read-only)")
    ap.add_argument("--log", default=str(LOG_XLSX))
    ap.add_argument("--out-xlsx", default=str(OUT_XLSX))
    ap.add_argument("--out-json", default=str(OUT_JSON))
    args = ap.parse_args(argv)

    trades = _load_trades(Path(args.log))
    fills = _load_fills(FILL_JSONL)
    audit = _load_audit_by_day(AUDIT_JSON)
    rows = build_matrix(trades, fills, audit)
    summary = _summaries(rows)
    payload = {"summary": summary, "trades": rows}

    out_json = Path(args.out_json)
    out_json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    write_excel(rows, summary, Path(args.out_xlsx))

    logger.info(
        "OBS-FORENSIC-56 matrix: trades=%d fill_join=%d unfreeze=%s -> %s",
        len(rows),
        summary["fill_joined"],
        summary["unfreeze_recommendation"],
        args.out_xlsx,
    )
    print(
        json.dumps(
            {
                "out_xlsx": str(args.out_xlsx),
                "out_json": str(args.out_json),
                "overall": summary["overall"],
                "strategy_classifications": summary["strategy_classifications"],
                "unfreeze_recommendation": summary["unfreeze_recommendation"],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
