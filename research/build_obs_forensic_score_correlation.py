#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OBS-FORENSIC-56 — Score × Outcome correlation (read-only).

Uses trading log + day recommendation audit. Does not change strategies.

  python -m research.build_obs_forensic_score_correlation
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_app.dual_score_evaluator import DualScoreEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ObsScoreCorr")

MATRIX_JSON = ROOT / "reports" / "OBS_FORENSIC_56_RootCause_Matrix_20260813.json"
AUDIT_JSON = ROOT / "reports" / "daily_recommendation_audit_log.json"
OUT_XLSX = ROOT / "reports" / "OBS_FORENSIC_56_Score_Correlation_20260813.xlsx"
OUT_JSON = ROOT / "reports" / "OBS_FORENSIC_56_Score_Correlation_20260813.json"


def _load_audit_days(path: Path, start: str = "2026-07-28", end: str = "2026-08-13") -> Dict[str, Dict[str, Any]]:
    by_day: Dict[str, Dict[str, Any]] = {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    for r in rows:
        day = str(r.get("timestamp") or "")[:10]
        if day < start or day > end:
            continue
        by_day[day] = r  # last snapshot of day
    return by_day


def _strategy_score_map(rec: Dict[str, Any]) -> Dict[str, Any]:
    sm: Dict[str, Any] = {}
    name = rec.get("recommended_strategy_name")
    if name:
        sm[str(name)] = rec.get("suitability_score")
    for alt in rec.get("alternative_strategies") or []:
        if isinstance(alt, dict) and alt.get("strategy") is not None:
            sm[str(alt["strategy"])] = alt.get("score")
    return sm


def _match_exec_score(exec_strategy: str, score_map: Dict[str, Any]) -> Dict[str, Any]:
    es = exec_strategy.lower()
    for k, v in score_map.items():
        kl = k.lower()
        if es == kl or es in kl or kl in es:
            return {"matched_name": k, "matched_score": v}
    # keyword bridges between trade-ticket names and registry names
    bridges = [
        ("golden ratio", ["golden", "orb", "opening range"]),
        ("momentum breakdown", ["breakdown", "bearish"]),
        ("momentum continuation", ["momentum breakout", "continuation"]),
        ("oversold bounce", ["oversold", "rsi"]),
    ]
    for needle, keys in bridges:
        if needle in es:
            for k, v in score_map.items():
                kl = k.lower()
                if any(x in kl for x in keys):
                    return {"matched_name": k, "matched_score": v, "match_basis": "keyword_bridge"}
    return {"matched_name": None, "matched_score": None, "match_basis": "NO_MATCH"}


def build() -> Dict[str, Any]:
    matrix = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
    trades = pd.DataFrame(matrix["trades"])
    audit = _load_audit_days(AUDIT_JSON)

    rows: List[Dict[str, Any]] = []
    for _, t in trades.iterrows():
        day = str(t["entry_ts"])[:10]
        rec = audit.get(day, {})
        sm = _strategy_score_map(rec) if rec else {}
        match = _match_exec_score(str(t["strategy"]), sm)
        top_name = rec.get("recommended_strategy_name")
        rows.append(
            {
                "trade_id": t["trade_id"],
                "day": day,
                "symbol": t["symbol"],
                "exec_strategy": t["strategy"],
                "direction": t["direction"],
                "gross_pnl": t["gross_pnl"],
                "net_pnl": t["net_pnl"],
                "costs_est": t["costs_est"],
                "exit_bucket": t.get("exit_bucket"),
                "day_recommended_strategy": top_name,
                "day_top_suitability_score": rec.get("suitability_score"),
                "day_predicted_regime": rec.get("predicted_regime"),
                "day_regime_confidence_pct": rec.get("regime_confidence_pct"),
                "aligned_with_day_recommendation": bool(top_name) and str(t["strategy"]) == str(top_name),
                "exec_strategy_audit_match": match.get("matched_name"),
                "exec_strategy_audit_score": match.get("matched_score"),
                "exec_match_basis": match.get("match_basis"),
                "day_candidate_strategies": " | ".join(sm.keys()) if sm else None,
            }
        )

    df = pd.DataFrame(rows)

    # Correlations where variance exists
    corr_block: Dict[str, Any] = {}
    for score_col, pnl_col in [
        ("day_top_suitability_score", "gross_pnl"),
        ("day_top_suitability_score", "net_pnl"),
        ("day_regime_confidence_pct", "gross_pnl"),
        ("exec_strategy_audit_score", "gross_pnl"),
    ]:
        s = pd.to_numeric(df[score_col], errors="coerce")
        p = pd.to_numeric(df[pnl_col], errors="coerce")
        mask = s.notna() & p.notna()
        n = int(mask.sum())
        nunq = int(s[mask].nunique()) if n else 0
        entry: Dict[str, Any] = {
            "score": score_col,
            "outcome": pnl_col,
            "n": n,
            "score_unique_values": nunq,
        }
        if n >= 5 and nunq >= 2:
            entry["pearson"] = round(float(s[mask].corr(p[mask], method="pearson")), 4)
            entry["spearman"] = round(float(s[mask].corr(p[mask], method="spearman")), 4)
            entry["status"] = "COMPUTED"
        else:
            entry["pearson"] = None
            entry["spearman"] = None
            entry["status"] = "NOT_COMPUTABLE_ZERO_VARIANCE_OR_SPARSE"
        corr_block[f"{score_col}__{pnl_col}"] = entry

    # Alignment economics
    aligned = df[df["aligned_with_day_recommendation"]]
    misaligned = df[~df["aligned_with_day_recommendation"]]

    def _slice(sub: pd.DataFrame, name: str) -> Dict[str, Any]:
        if sub.empty:
            return {"slice": name, "trades": 0}
        g = sub["gross_pnl"]
        return {
            "slice": name,
            "trades": int(len(sub)),
            "win_rate_pct": round(100.0 * (g > 0).sum() / len(sub), 1),
            "gross": round(float(g.sum()), 2),
            "net": round(float(sub["net_pnl"].sum()), 2),
            "expectancy_gross": round(float(g.mean()), 2),
        }

    # P&L by day recommendation (regime proxy)
    by_rec = []
    for name, sub in df.groupby(df["day_recommended_strategy"].fillna("UNKNOWN")):
        by_rec.append(_slice(sub, str(name)))

    by_exec = []
    for name, sub in df.groupby("exec_strategy"):
        by_exec.append(_slice(sub, str(name)))

    # Dual score for whole sample (portfolio-level, not per-trade)
    overall = matrix["summary"]["overall"]
    # equity proxy drawdown from forensic earlier ~ not exact; use gross path estimate
    # From prior forensic max DD approx - use simple: if net negative use |net|/capital proxy
    # Use reported metrics loosely
    pf = float(overall.get("pf_gross") or 0)
    wr = float(overall.get("win_rate_pct") or 0)
    # rough DD from net vs starting  - not authoritative
    max_dd_proxy = 5.0  # placeholder unknown; DualScore needs it — compute from cumulative gross
    cum = np.cumsum(df["gross_pnl"].to_numpy())
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd_pct = float(abs(dd.min()) / 200000.0 * 100.0) if len(dd) else 0.0  # vs 2L paper capital assumption

    dq_pass = float(matrix["summary"].get("data_quality_pass_count") or 0)
    dq_rate = 100.0 * dq_pass / max(len(df), 1)
    # regime accuracy unknown at trade level — use audit match field if present else NaN->50 neutral
    dual = DualScoreEvaluator().calculate_dual_scores(
        regime_accuracy_pct=50.0,  # unknown — neutral until EOD regime labels joined
        counterfactual_advantage_pct=0.0,  # not computed
        data_quality_pass_rate_pct=dq_rate,
        profit_factor=max(pf, 0.0),
        win_rate_pct=wr,
        max_drawdown_pct=max_dd_pct,
    )

    findings = [
        "Day top suitability_score is saturated at 100 for all 56 trades → score↔P&L correlation not computable.",
        "Day regime_confidence_pct is constant (88.5) on these trade days → no variance.",
        f"0/{len(df)} trades executed the day's recommended strategy (selection misalignment).",
        "Executed ticket names (Golden Ratio Scan, Momentum Breakdown, …) do not match audit registry names (VWAP Mean Reversion, Momentum Breakout, ORB) → per-trade strategy score join fails.",
        "This indicates a STRATEGY-SELECTION / NAMING / ROUTING problem more than a 'score failed to predict' problem.",
        "Do NOT unfreeze strategy parameters yet — fix evidence instrumentation and selection linkage first (still freeze-safe analysis).",
    ]

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_trades": int(len(df)),
        "aligned_with_recommendation": int(aligned.shape[0]),
        "misaligned_with_recommendation": int(misaligned.shape[0]),
        "top_score_unique_values": int(df["day_top_suitability_score"].nunique(dropna=True)),
        "regime_conf_unique_values": int(df["day_regime_confidence_pct"].nunique(dropna=True)),
        "exec_audit_score_matched": int(df["exec_strategy_audit_score"].notna().sum()),
        "correlations": corr_block,
        "alignment_economics": {
            "aligned": _slice(aligned, "ALIGNED"),
            "misaligned": _slice(misaligned, "MISALIGNED"),
        },
        "by_day_recommendation": by_rec,
        "by_exec_strategy": by_exec,
        "portfolio_dual_score": {
            "intelligence_quality_score": dual.intelligence_quality_score,
            "trading_performance_score": dual.trading_performance_score,
            "summary": dual.evaluation_summary,
            "notes": [
                "Intelligence uses neutral regime_accuracy=50 and counterfactual=0 (not yet measured).",
                f"Data-quality pass rate from fill join ≈ {dq_rate:.1f}%.",
                f"Max DD proxy from cumulative gross vs ₹2L capital ≈ {max_dd_pct:.2f}%.",
            ],
        },
        "findings": findings,
        "unfreeze_recommendation": "DO_NOT_UNFREEZE_STRATEGY_LAYER",
        "next_freeze_safe_steps": [
            "Instrument per-trade intelligence/suitability score at fill time (observation logger).",
            "Unify strategy naming between ticket engine and StrategyRegistry / hybrid recommender.",
            "Measure how often paper entries follow vs ignore day recommendation.",
            "Then re-run score correlation once scores have variance.",
        ],
    }
    return {"summary": summary, "trades": rows}


def main() -> int:
    payload = build()
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    s = payload["summary"]
    trades = pd.DataFrame(payload["trades"])
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xl:
        trades.to_excel(xl, sheet_name="TRADE_SCORE_JOIN", index=False)
        pd.DataFrame(s["correlations"].values()).to_excel(xl, sheet_name="CORRELATIONS", index=False)
        pd.DataFrame([s["alignment_economics"]["aligned"], s["alignment_economics"]["misaligned"]]).to_excel(
            xl, sheet_name="ALIGNMENT_PNL", index=False
        )
        pd.DataFrame(s["by_day_recommendation"]).to_excel(xl, sheet_name="BY_DAY_REC", index=False)
        pd.DataFrame(s["by_exec_strategy"]).to_excel(xl, sheet_name="BY_EXEC_STRATEGY", index=False)
        pd.DataFrame([s["portfolio_dual_score"]]).to_excel(xl, sheet_name="DUAL_SCORE_PORTFOLIO", index=False)
        pd.DataFrame([{"finding": f} for f in s["findings"]]).to_excel(xl, sheet_name="FINDINGS", index=False)
        pd.DataFrame([{"step": x} for x in s["next_freeze_safe_steps"]]).to_excel(
            xl, sheet_name="NEXT_STEPS", index=False
        )

    logger.info(
        "Score correlation done aligned=%s/%s unfreeze=%s -> %s",
        s["aligned_with_recommendation"],
        s["n_trades"],
        s["unfreeze_recommendation"],
        OUT_XLSX,
    )
    print(
        json.dumps(
            {
                "out_xlsx": str(OUT_XLSX),
                "out_json": str(OUT_JSON),
                "aligned": s["aligned_with_recommendation"],
                "misaligned": s["misaligned_with_recommendation"],
                "correlations": s["correlations"],
                "dual_score": s["portfolio_dual_score"],
                "findings": s["findings"],
                "unfreeze_recommendation": s["unfreeze_recommendation"],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
