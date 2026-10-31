#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OBS-FORENSIC C2 — Triple P&L rebuild (policy reporting only).

V1 Gross | V2 Net charges-only | V3 Net full friction (charges + 0.05% slip)
Does not modify trading_app/broker_charges.py or strategies.

  python -m research.build_obs_forensic_triple_pnl
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_app.broker_charges import (
    AngelOneEquityIntradayCharges,
    estimate_equity_intraday_round_trip,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ObsTriplePnL")

LOG_XLSX = ROOT / "reports" / "NexTrade_Trading_Log_20260813_152345_16952.xlsx"
OUT_XLSX = ROOT / "reports" / "OBS_FORENSIC_56_Triple_PnL_20260813.xlsx"
OUT_JSON = ROOT / "reports" / "OBS_FORENSIC_56_Triple_PnL_20260813.json"
POLICY = "docs/NEXTRADE_OBS_FORENSIC_C2_COST_ASSUMPTION_POLICY_V1.md"


def _load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Executed Trades", header=3)
    df = df.dropna(subset=["Trade ID"]).copy()
    for c in ["Qty", "Entry Price (INR)", "Exit Price (INR)", "Gross P&L (INR)", "Est. Charges (INR)", "Est. Net P&L (INR)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _pattern(v1: float, v2: float, v3: float) -> str:
    if v1 > 0 and v2 > 0 and v3 > 0:
        return "ROBUST_UNDER_FRICTION"
    if v1 > 0 and v2 > 0 and v3 <= 0:
        return "VIABLE_CHARGES_FRAGILE_SLIP"
    if v1 > 0 and v2 <= 0:
        return "FAILS_UNDER_CHARGES"
    if v1 <= 0:
        return "NEGATIVE_BEFORE_FRICTION"
    return "MIXED_OR_FLAT"


def build() -> Dict[str, Any]:
    trades = _load_trades(LOG_XLSX)
    with_slip_model = AngelOneEquityIntradayCharges()  # includes 0.05% slip
    no_slip_model = AngelOneEquityIntradayCharges(slippage_pct=0.0)

    rows: List[Dict[str, Any]] = []
    for _, t in trades.iterrows():
        entry = float(t["Entry Price (INR)"])
        exit_px = float(t["Exit Price (INR)"])
        qty = int(t["Qty"])
        v1 = float(t["Gross P&L (INR)"] or 0)
        chg = estimate_equity_intraday_round_trip(
            entry=entry, exit_px=exit_px, qty=qty, model=no_slip_model, include_slippage=False
        )
        full = estimate_equity_intraday_round_trip(
            entry=entry, exit_px=exit_px, qty=qty, model=with_slip_model, include_slippage=True
        )
        v2 = v1 - chg.total
        v3 = v1 - full.total
        rows.append(
            {
                "trade_id": str(t["Trade ID"]),
                "symbol": t["Symbol"],
                "strategy": t["Strategy"],
                "direction": t["Direction"],
                "qty": qty,
                "entry": entry,
                "exit": exit_px,
                "V1_gross_pnl": round(v1, 2),
                "charges_only": round(chg.total, 2),
                "slippage_assumed": round(full.slippage, 2),
                "charges_plus_slip": round(full.total, 2),
                "V2_net_charges_only": round(v2, 2),
                "V3_net_full_friction": round(v3, 2),
                "log_est_charges": round(float(t["Est. Charges (INR)"] or 0), 2),
                "log_est_net_equals_V3": round(float(t["Est. Net P&L (INR)"] or 0), 2),
                "forensic_pattern": _pattern(v1, v2, v3),
                "V1_positive": v1 > 0,
                "V2_positive": v2 > 0,
                "V3_positive": v3 > 0,
            }
        )

    df = pd.DataFrame(rows)

    def _agg(sub: pd.DataFrame, name: str) -> Dict[str, Any]:
        if sub.empty:
            return {"slice": name, "trades": 0}
        return {
            "slice": name,
            "trades": int(len(sub)),
            "V1_sum": round(float(sub["V1_gross_pnl"].sum()), 2),
            "V2_sum": round(float(sub["V2_net_charges_only"].sum()), 2),
            "V3_sum": round(float(sub["V3_net_full_friction"].sum()), 2),
            "V1_win_rate_pct": round(100.0 * sub["V1_positive"].mean(), 1),
            "V2_win_rate_pct": round(100.0 * sub["V2_positive"].mean(), 1),
            "V3_win_rate_pct": round(100.0 * sub["V3_positive"].mean(), 1),
            "pattern_counts": sub["forensic_pattern"].value_counts().to_dict(),
        }

    by_strategy = [_agg(sub, str(s)) for s, sub in df.groupby("strategy")]
    by_pattern = (
        df.groupby("forensic_pattern")
        .size()
        .reset_index(name="trades")
        .to_dict(orient="records")
    )

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "policy": POLICY,
        "n_trades": int(len(df)),
        "overall": _agg(df, "ALL"),
        "by_strategy": by_strategy,
        "by_pattern": by_pattern,
        "notes": [
            "V3 matches historical Excel Est. Net when log used full-friction model.",
            "Slippage is assumed 0.05% of turnover — scenario, not empirical Angel shortfall.",
            "Do not KEEP/RETIRE strategies from V3 alone.",
            "Strategy freeze intact; C2 is forensic reporting policy only.",
        ],
        "unfreeze_recommendation": "DO_NOT_UNFREEZE_STRATEGY_LAYER",
        "next": ["A_canonical_strategy_ids", "B_decision_trace", "continue_observation"],
    }
    return {"summary": summary, "trades": rows}


def main() -> int:
    payload = build()
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    s = payload["summary"]
    trades = pd.DataFrame(payload["trades"])
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xl:
        trades.to_excel(xl, sheet_name="TRIPLE_PNL_TRADES", index=False)
        pd.DataFrame(s["by_strategy"]).to_excel(xl, sheet_name="BY_STRATEGY", index=False)
        pd.DataFrame(s["by_pattern"]).to_excel(xl, sheet_name="BY_PATTERN", index=False)
        pd.DataFrame([s["overall"]]).to_excel(xl, sheet_name="OVERALL", index=False)
        pd.DataFrame([{"note": n} for n in s["notes"]]).to_excel(xl, sheet_name="POLICY_NOTES", index=False)

    logger.info(
        "Triple P&L: V1=%.2f V2=%.2f V3=%.2f -> %s",
        s["overall"]["V1_sum"],
        s["overall"]["V2_sum"],
        s["overall"]["V3_sum"],
        OUT_XLSX,
    )
    print(
        json.dumps(
            {
                "out_xlsx": str(OUT_XLSX),
                "out_json": str(OUT_JSON),
                "policy": POLICY,
                "overall": s["overall"],
                "by_strategy": s["by_strategy"],
                "by_pattern": s["by_pattern"],
                "unfreeze_recommendation": s["unfreeze_recommendation"],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
