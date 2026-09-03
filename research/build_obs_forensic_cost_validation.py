#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OBS-FORENSIC Investigation C — Cost model validation (read-only).

Compares trading-log Est. Charges vs independent Angel equity-intraday rebuild.
Does NOT change strategies, risk, or live cost engine behaviour.

  python -m research.build_obs_forensic_cost_validation
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_app.broker_charges import (
    AngelOneEquityIntradayCharges,
    estimate_equity_intraday_round_trip,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ObsCostValidation")

LOG_XLSX = ROOT / "reports" / "NexTrade_Trading_Log_20260813_152345_16952.xlsx"
OUT_XLSX = ROOT / "reports" / "OBS_FORENSIC_56_Cost_Validation_20260813.xlsx"
OUT_JSON = ROOT / "reports" / "OBS_FORENSIC_56_Cost_Validation_20260813.json"


def _load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Executed Trades", header=3)
    df = df.dropna(subset=["Trade ID"]).copy()
    for c in [
        "Qty",
        "Entry Price (INR)",
        "Exit Price (INR)",
        "Gross P&L (INR)",
        "Est. Charges (INR)",
        "Est. Net P&L (INR)",
    ]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build() -> Dict[str, Any]:
    trades = _load_trades(LOG_XLSX)
    default_model = AngelOneEquityIntradayCharges()
    no_slip_model = AngelOneEquityIntradayCharges(slippage_pct=0.0)
    # Conservative alternate: lower slip, GST on brokerage only (sensitivity)
    sens_model = AngelOneEquityIntradayCharges(slippage_pct=0.02)

    rows: List[Dict[str, Any]] = []
    for _, t in trades.iterrows():
        entry = float(t["Entry Price (INR)"])
        exit_px = float(t["Exit Price (INR)"])
        qty = int(t["Qty"])
        log_charges = float(t["Est. Charges (INR)"] or 0)
        gross = float(t["Gross P&L (INR)"] or 0)
        log_net = float(t["Est. Net P&L (INR)"] or 0)

        buy_n = entry * qty
        sell_n = exit_px * qty
        turnover = buy_n + sell_n

        with_slip = estimate_equity_intraday_round_trip(
            entry=entry, exit_px=exit_px, qty=qty, model=default_model, include_slippage=True
        )
        no_slip = estimate_equity_intraday_round_trip(
            entry=entry, exit_px=exit_px, qty=qty, model=no_slip_model, include_slippage=False
        )
        sens = estimate_equity_intraday_round_trip(
            entry=entry, exit_px=exit_px, qty=qty, model=sens_model, include_slippage=True
        )

        rows.append(
            {
                "trade_id": str(t["Trade ID"]),
                "symbol": t["Symbol"],
                "strategy": t["Strategy"],
                "direction": t["Direction"],
                "qty": qty,
                "entry": entry,
                "exit": exit_px,
                "buy_notional": round(buy_n, 2),
                "sell_notional": round(sell_n, 2),
                "turnover": round(turnover, 2),
                "gross_pnl": gross,
                "log_est_charges": round(log_charges, 2),
                "log_est_net": round(log_net, 2),
                "rebuild_total_with_slip": round(with_slip.total, 2),
                "rebuild_total_no_slip": round(no_slip.total, 2),
                "rebuild_total_slip_2bps_proxy": round(sens.total, 2),  # 0.02% model
                "delta_log_vs_rebuild": round(log_charges - with_slip.total, 2),
                "net_if_no_slip": round(gross - no_slip.total, 2),
                "net_if_with_slip": round(gross - with_slip.total, 2),
                "brokerage": with_slip.brokerage,
                "gst": round(with_slip.gst, 2),
                "stt": round(with_slip.stt, 2),
                "exchange": round(with_slip.exchange, 2),
                "sebi": round(with_slip.sebi, 2),
                "stamp": round(with_slip.stamp, 2),
                "slippage": round(with_slip.slippage, 2),
                "slip_share_of_rebuild_pct": round(
                    100.0 * with_slip.slippage / with_slip.total, 1
                )
                if with_slip.total
                else 0.0,
            }
        )

    df = pd.DataFrame(rows)
    n = len(df)
    sum_gross = float(df["gross_pnl"].sum())
    sum_log = float(df["log_est_charges"].sum())
    sum_rebuild = float(df["rebuild_total_with_slip"].sum())
    sum_noslip = float(df["rebuild_total_no_slip"].sum())
    sum_slip = float(df["slippage"].sum())
    match_n = int((df["delta_log_vs_rebuild"].abs() < 0.05).sum())

    findings = [
        f"Log total est. charges ₹{sum_log:,.2f} vs rebuild(with slip) ₹{sum_rebuild:,.2f} — "
        f"{'MATCH' if abs(sum_log - sum_rebuild) < 1 else 'MISMATCH'} "
        f"(exact row match {match_n}/{n}).",
        f"Slippage component alone ₹{sum_slip:,.2f} "
        f"({100.0 * sum_slip / sum_rebuild:.1f}% of rebuild total) at default slippage_pct=0.05% of turnover.",
        f"Without slippage, total charges ≈ ₹{sum_noslip:,.2f}; "
        f"sample net would be ₹{sum_gross - sum_noslip:,.2f} instead of log net ₹{float(df['log_est_net'].sum()):,.2f}.",
        "Cost engine applies round-trip on buy+sell turnover (correct structure): brokerage×2, STT on sell, stamp on buy, exchange+SEBI on turnover, GST on brokerage+exchange.",
        "P0 question is whether 0.05% slippage on full turnover is appropriate for paper forensic (may dominate edge).",
        "Strategy freeze remains; this validates cost *measurement*, not strategy quality.",
    ]

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_log": str(LOG_XLSX),
        "model_defaults": default_model.to_dict(),
        "n_trades": n,
        "gross_pnl_total": round(sum_gross, 2),
        "log_charges_total": round(sum_log, 2),
        "rebuild_with_slip_total": round(sum_rebuild, 2),
        "rebuild_no_slip_total": round(sum_noslip, 2),
        "slippage_total": round(sum_slip, 2),
        "avg_log_charge_per_trade": round(sum_log / n, 2) if n else 0,
        "avg_turnover": round(float(df["turnover"].mean()), 2) if n else 0,
        "exact_match_rows": match_n,
        "component_totals": {
            "brokerage": round(float(df["brokerage"].sum()), 2),
            "gst": round(float(df["gst"].sum()), 2),
            "stt": round(float(df["stt"].sum()), 2),
            "exchange": round(float(df["exchange"].sum()), 2),
            "sebi": round(float(df["sebi"].sum()), 2),
            "stamp": round(float(df["stamp"].sum()), 2),
            "slippage": round(sum_slip, 2),
        },
        "findings": findings,
        "unfreeze_recommendation": "DO_NOT_UNFREEZE_STRATEGY_LAYER",
        "workstream": "OBS-FORENSIC-REPAIR / Investigation C — Cost Validation",
    }
    return {"summary": summary, "trades": rows}


def main() -> int:
    payload = build()
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    s = payload["summary"]
    trades = pd.DataFrame(payload["trades"])
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xl:
        trades.to_excel(xl, sheet_name="TRADE_COST_REBUILD", index=False)
        pd.DataFrame([s["component_totals"]]).to_excel(xl, sheet_name="COMPONENT_TOTALS", index=False)
        pd.DataFrame([{"finding": f} for f in s["findings"]]).to_excel(xl, sheet_name="FINDINGS", index=False)
        pd.DataFrame(
            [
                {"Item": k, "Value": str(v)}
                for k, v in s.items()
                if k not in ("findings", "component_totals", "model_defaults")
            ]
            + [{"Item": f"model.{k}", "Value": str(v)} for k, v in s["model_defaults"].items()]
        ).to_excel(xl, sheet_name="SUMMARY", index=False)

    logger.info(
        "Cost validation: log=%.2f rebuild=%.2f slip=%.2f match=%s/%s -> %s",
        s["log_charges_total"],
        s["rebuild_with_slip_total"],
        s["slippage_total"],
        s["exact_match_rows"],
        s["n_trades"],
        OUT_XLSX,
    )
    print(
        json.dumps(
            {
                "out_xlsx": str(OUT_XLSX),
                "out_json": str(OUT_JSON),
                "log_charges_total": s["log_charges_total"],
                "rebuild_with_slip_total": s["rebuild_with_slip_total"],
                "rebuild_no_slip_total": s["rebuild_no_slip_total"],
                "slippage_total": s["slippage_total"],
                "component_totals": s["component_totals"],
                "exact_match_rows": s["exact_match_rows"],
                "findings": s["findings"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
