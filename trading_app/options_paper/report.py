"""
Daily + cumulative reporting for the options paper lane, built from ``logs/options_paper/summary.csv``
(one row per strategy per completed day). Mirrors the equity side: JSON for the dashboard and an Excel
workbook saved under ``reports/options/``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from trading_app.options_paper.ledger import DEFAULT_DIR

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "options"


def load_summary(log_dir: Path = DEFAULT_DIR) -> pd.DataFrame:
    path = Path(log_dir) / "summary.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for c in ("entry_credit", "gross_points", "charges", "net_pnl", "model_entry_credit", "fill_vs_model_points"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # A restarted day may append a second row for the same strategy/day: keep the last one.
    return df.drop_duplicates(["date", "strategy"], keep="last").sort_values(["date", "strategy"]).reset_index(drop=True)


def _max_drawdown(series: pd.Series) -> float:
    cum = series.cumsum()
    peak = cum.cummax().clip(lower=0)
    return float((cum - peak).min()) if len(cum) else 0.0


def strategy_stats(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    for name, g in list(df.groupby("strategy")) + [("ALL STRATEGIES", df)]:
        if g.empty:
            continue
        daily = g.groupby("date")["net_pnl"].sum()
        wins = daily[daily > 0]
        losses = daily[daily <= 0]
        rows.append({
            "strategy": name,
            "days": int(daily.size),
            "net_pnl": round(float(daily.sum()), 2),
            "avg_per_day": round(float(daily.mean()), 2),
            "win_rate_pct": round(100.0 * len(wins) / len(daily), 1),
            "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
            "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
            "best_day": round(float(daily.max()), 2),
            "worst_day": round(float(daily.min()), 2),
            "max_drawdown": round(_max_drawdown(daily), 2),
            "charges": round(float(g["charges"].sum()), 2),
            "avg_fill_vs_model_pts": (round(float(g["fill_vs_model_points"].mean()), 2)
                                      if g["fill_vs_model_points"].notna().any() else None),
        })
    return rows


def daily_table(df: pd.DataFrame) -> pd.DataFrame:
    """Rows = dates; one column per strategy (net P&L) + day total + cumulative total."""
    pv = df.pivot_table(index="date", columns="strategy", values="net_pnl", aggfunc="sum").fillna(0.0)
    pv["day_total"] = pv.sum(axis=1)
    pv["cumulative"] = pv["day_total"].cumsum()
    return pv.round(2)


def build_report(log_dir: Path = DEFAULT_DIR) -> Dict[str, Any]:
    df = load_summary(log_dir)
    if df.empty:
        return {"has_data": False, "stats": [], "daily": [], "strategies": [], "cumulative_by_strategy": {}}
    dt = daily_table(df)
    strategies = [c for c in dt.columns if c not in ("day_total", "cumulative")]
    cum_by = {s: [{"date": str(d), "cum": round(float(v), 2)} for d, v in dt[s].cumsum().items()] for s in strategies}
    cum_by["ALL"] = [{"date": str(d), "cum": float(v)} for d, v in dt["cumulative"].items()]
    return {
        "has_data": True,
        "first_day": str(df["date"].min()),
        "last_day": str(df["date"].max()),
        "strategies": strategies,
        "stats": strategy_stats(df),
        "daily": [{"date": str(d), **{k: float(v) for k, v in row.items()}} for d, row in dt.iloc[::-1].iterrows()],
        "cumulative_by_strategy": cum_by,
    }


def write_excel(log_dir: Path = DEFAULT_DIR, out_dir: Path = REPORT_DIR, asof: Optional[date] = None) -> Optional[Path]:
    df = load_summary(log_dir)
    if df.empty:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"Options_Paper_Report_{(asof or date.today()).strftime('%Y%m%d')}.xlsx"
    stats = pd.DataFrame(strategy_stats(df))
    dt = daily_table(df).reset_index()
    trades = df[["date", "strategy", "symbol", "expiry", "atm", "entry_credit", "exit_reason", "gross_points",
                 "charges", "net_pnl", "model_entry_credit", "fill_vs_model_points", "legs"]].copy()
    legs_rows = []
    for _, r in df.iterrows():
        for part in str(r.get("legs", "") or "").split(";"):
            if "->" not in part:
                continue
            sym, rest = part.split(":", 1)
            entry, rest = rest.split("->", 1)
            exitp, why = (rest.split("(", 1) + [""])[:2]
            legs_rows.append({"date": r["date"], "strategy": r["strategy"], "contract": sym,
                              "entry": float(entry), "exit": float(exitp), "exit_reason": why.rstrip(")")})
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        stats.to_excel(xw, sheet_name="Summary", index=False)
        dt.to_excel(xw, sheet_name="Daily & Cumulative", index=False)
        trades.to_excel(xw, sheet_name="Strategy-days", index=False)
        pd.DataFrame(legs_rows).to_excel(xw, sheet_name="Legs", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
            ws.freeze_panes = "B2"
    return path
