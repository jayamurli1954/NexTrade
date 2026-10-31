"""
Fundamental Factor Engine — deterministic Quality / Growth / Value / Health / Consistency.

Research-only. Never calls brokers. Never invents missing inputs.
Historical snapshots must not use current peer tables (look-ahead safety).
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from research.fundamentals_loader import (
    _latest_two_periods,
    _parse_number,
    _parse_pct,
    _period_sort_key,
    _table_row_map,
    _yoy_growth,
)
from research.fundamentals_store import FundamentalsStore, default_fundamentals_dir


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_factor_config(path: Optional[Path] = None) -> Dict[str, Any]:
    cfg_path = path or (_repo_root() / "config" / "fundamental_factors.json")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


@dataclass
class FactorScores:
    symbol: str
    fiscal_year: Optional[int]
    quality: Optional[float]
    growth: Optional[float]
    value: Optional[float]
    financial_health: Optional[float]
    consistency: Optional[float]
    fundamental_risk: Optional[float]
    overall_fundamental: Optional[float]
    relatives: Dict[str, Any] = field(default_factory=dict)
    thesis: List[str] = field(default_factory=list)
    as_of: str = ""
    missing_inputs: List[str] = field(default_factory=list)
    mode: str = "current"
    inputs_used: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clamp(score: float) -> float:
    return round(max(0.0, min(100.0, score)), 1)


def _weighted_mean(parts: Sequence[Tuple[Optional[float], float]]) -> Optional[float]:
    usable = [(s, w) for s, w in parts if s is not None and w > 0]
    if not usable:
        return None
    total_w = sum(w for _, w in usable)
    if total_w <= 0:
        return None
    return _clamp(sum(s * w for s, w in usable) / total_w)


def _band_higher_better(value: Optional[float], bands: Sequence[Tuple[float, float]]) -> Optional[float]:
    """bands: (threshold, score) descending thresholds."""
    if value is None:
        return None
    for threshold, score in bands:
        if value >= threshold:
            return score
    return 0.0


def _band_lower_better(value: Optional[float], bands: Sequence[Tuple[float, float]]) -> Optional[float]:
    if value is None:
        return None
    for threshold, score in bands:
        if value <= threshold:
            return score
    return 0.0


def _cv(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    mean = statistics.mean(vals)
    if abs(mean) < 1e-9:
        return None
    return statistics.pstdev(vals) / abs(mean)


def _cv_to_score(cv: Optional[float]) -> Optional[float]:
    if cv is None:
        return None
    # CV 0 → 100; CV 0.5 → ~50; CV ≥ 1.0 → 0
    return _clamp(100.0 * (1.0 - min(1.0, cv)))


def _cagr(first: float, last: float, years: int) -> Optional[float]:
    if years <= 0 or first <= 0 or last <= 0:
        return None
    try:
        return (last / first) ** (1.0 / years) - 1.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _ordered_periods(period_map: Dict[str, float]) -> List[Tuple[str, float]]:
    return sorted(period_map.items(), key=lambda kv: _period_sort_key(kv[0]))


def _periods_up_to(period_map: Dict[str, float], fiscal_year: int) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for period, val in period_map.items():
        y, _ = _period_sort_key(period)
        if y and y <= fiscal_year:
            out[period] = val
    return out


def _period_year(period: str) -> Optional[int]:
    y, m = _period_sort_key(period)
    return y if y else None


def _is_financials(payload: Dict[str, Any], keywords: Sequence[str]) -> bool:
    peer = (payload.get("sections") or {}).get("peer_comparison") or {}
    blob = " ".join(
        str(peer.get(k) or "")
        for k in ("sector", "industry", "sub_industry", "sub_sub_industry")
    )
    return any(k.lower() in blob.lower() for k in keywords)


def _promoter_holding(payload: Dict[str, Any]) -> Optional[float]:
    sh = (payload.get("sections") or {}).get("shareholding")
    if not sh:
        return None
    rows = _table_row_map(sh)
    for key in ("Promoters", "Promoter", "Promoter Holding"):
        if key in rows:
            _, latest, _ = _latest_two_periods(rows[key])
            return latest
    # fallback: any label containing Promoter
    for label, pmap in rows.items():
        if "promoter" in label.lower():
            _, latest, _ = _latest_two_periods(pmap)
            return latest
    return None


def _peer_values(
    payload: Dict[str, Any],
    metric_key: str,
    *,
    exclude_self: bool = True,
    pe_min: Optional[float] = None,
    pe_max: Optional[float] = None,
) -> List[float]:
    peer = (payload.get("sections") or {}).get("peer_comparison") or {}
    peers = list(peer.get("peers") or [])
    self_name = str((peers[0].get("name") if peers else "") or "").lower()
    out: List[float] = []
    for p in peers:
        name = str(p.get("name") or "").lower()
        if exclude_self and self_name and name == self_name:
            continue
        values = p.get("values") or {}
        val = _parse_number(values.get(metric_key))
        if val is None:
            continue
        if metric_key == "P/E":
            if val <= 0:
                continue
            if pe_min is not None and val < pe_min:
                continue
            if pe_max is not None and val > pe_max:
                continue
        out.append(val)
    return out


def _median(vals: Sequence[float]) -> Optional[float]:
    if not vals:
        return None
    return float(statistics.median(vals))


def _score_quality(
    *,
    roe: Optional[float],
    roce: Optional[float],
    margin: Optional[float],
    promoter: Optional[float],
    ocf_pat: Optional[float],
    weights: Dict[str, float],
) -> Optional[float]:
    roe_s = _band_higher_better(
        roe,
        [(20, 100), (15, 80), (10, 60), (5, 40), (0, 20)],
    )
    roce_s = _band_higher_better(
        roce,
        [(25, 100), (18, 85), (12, 65), (8, 45), (0, 20)],
    )
    margin_pct = margin * 100.0 if margin is not None and margin <= 1 else margin
    margin_s = _band_higher_better(
        margin_pct,
        [(15, 100), (10, 80), (5, 60), (2, 40), (0, 20)],
    )
    promoter_s = _band_higher_better(
        promoter,
        [(55, 100), (45, 80), (35, 60), (25, 40), (0, 20)],
    )
    ocf_s = None
    if ocf_pat is not None:
        if ocf_pat >= 1.0:
            ocf_s = 100.0
        elif ocf_pat >= 0.7:
            ocf_s = 75.0
        elif ocf_pat >= 0.4:
            ocf_s = 50.0
        elif ocf_pat >= 0:
            ocf_s = 25.0
        else:
            ocf_s = 0.0
    return _weighted_mean(
        [
            (roe_s, weights.get("roe", 0.25)),
            (roce_s, weights.get("roce", 0.30)),
            (margin_s, weights.get("profit_margin", 0.20)),
            (promoter_s, weights.get("promoter", 0.15)),
            (ocf_s, weights.get("ocf_pat", 0.10)),
        ]
    )


def _score_growth_leg(g: Optional[float]) -> Optional[float]:
    if g is None:
        return None
    pct = g * 100.0 if abs(g) <= 1.5 else g
    return _band_higher_better(
        pct,
        [(20, 100), (15, 85), (10, 70), (5, 55), (0, 35), (-5, 15)],
    )


def _score_growth(
    *,
    sales_yoy: Optional[float],
    pat_yoy: Optional[float],
    sales_cagr: Optional[float],
    pat_cagr: Optional[float],
    weights: Dict[str, float],
) -> Optional[float]:
    return _weighted_mean(
        [
            (_score_growth_leg(sales_yoy), weights.get("sales_yoy", 0.35)),
            (_score_growth_leg(pat_yoy), weights.get("pat_yoy", 0.35)),
            (_score_growth_leg(sales_cagr), weights.get("sales_cagr_3y", 0.15)),
            (_score_growth_leg(pat_cagr), weights.get("pat_cagr_3y", 0.15)),
        ]
    )


def _score_pe_absolute(pe: Optional[float]) -> Optional[float]:
    if pe is None or pe <= 0 or pe > 80:
        return None
    return _band_lower_better(
        pe,
        [(12, 100), (18, 85), (25, 70), (35, 50), (50, 30)],
    )


def _score_peer_pe_rel(pe_vs_sector_pct: Optional[float]) -> Optional[float]:
    """Negative % = cheaper than peers → higher score."""
    if pe_vs_sector_pct is None:
        return None
    # -30% → ~100; 0% → 55; +30% → ~10
    return _clamp(55.0 - pe_vs_sector_pct)


def _score_value(
    *,
    pe: Optional[float],
    pe_vs_sector_pct: Optional[float],
    dividend_yield: Optional[float],
    roce_vs_peer: Optional[float],
    weights: Dict[str, float],
) -> Optional[float]:
    dy_pct = None
    if dividend_yield is not None:
        dy_pct = dividend_yield * 100.0 if dividend_yield <= 1 else dividend_yield
    dy_s = _band_higher_better(dy_pct, [(3, 100), (2, 80), (1, 60), (0.3, 40), (0, 20)])
    roce_rel_s = None
    if roce_vs_peer is not None:
        # positive = stock ROCE above peer median
        roce_rel_s = _clamp(50.0 + roce_vs_peer * 2.0)
    return _weighted_mean(
        [
            (_score_pe_absolute(pe), weights.get("pe_absolute", 0.30)),
            (_score_peer_pe_rel(pe_vs_sector_pct), weights.get("pe_peer_relative", 0.0)),
            (dy_s, weights.get("dividend_yield", 0.15)),
            (roce_rel_s, weights.get("roce_peer_relative", 0.0)),
        ]
    )


def _score_health(
    *,
    dte: Optional[float],
    interest_coverage: Optional[float],
    current_ratio: Optional[float],
    pat_cv: Optional[float],
    weights: Dict[str, float],
    financials: bool,
) -> Optional[float]:
    if financials:
        dte_s = _band_lower_better(dte, [(2.0, 100), (4.0, 80), (8.0, 55), (12.0, 30)])
    else:
        dte_s = _band_lower_better(dte, [(0.3, 100), (0.7, 85), (1.2, 65), (2.0, 40), (3.5, 15)])
    ic_s = _band_higher_better(interest_coverage, [(8, 100), (4, 80), (2, 55), (1, 30), (0, 5)])
    cr_s = _band_higher_better(current_ratio, [(2.0, 100), (1.5, 80), (1.2, 60), (1.0, 40), (0.8, 20)])
    pat_vol_s = _cv_to_score(pat_cv)
    return _weighted_mean(
        [
            (dte_s, weights.get("debt_to_equity", 0.45)),
            (ic_s, weights.get("interest_coverage", 0.25)),
            (cr_s, weights.get("current_ratio", 0.15)),
            (pat_vol_s, weights.get("pat_volatility", 0.15)),
        ]
    )


def _score_consistency(
    *,
    roe_series: Sequence[float],
    roce_series: Sequence[float],
    margin_series: Sequence[float],
    sales_yoy_series: Sequence[float],
    pat_series: Sequence[float],
    weights: Dict[str, float],
) -> Optional[float]:
    combo = list(roe_series) + list(roce_series)
    roe_roce_cv = _cv(combo) if len(combo) >= 2 else _cv(list(roe_series) or list(roce_series))
    margin_cv = _cv(margin_series)
    sales_vol = _cv(sales_yoy_series) if sales_yoy_series else None
    # For YoY series, use stdev of percentage points (already growth rates)
    if sales_yoy_series and len(sales_yoy_series) >= 2:
        sales_vol = statistics.pstdev(sales_yoy_series)
        sales_vol_s = _clamp(100.0 * (1.0 - min(1.0, sales_vol / 0.5)))
    else:
        sales_vol_s = None

    pos_pat = None
    if pat_series:
        pos_pat = 100.0 * (sum(1 for p in pat_series if p > 0) / len(pat_series))

    return _weighted_mean(
        [
            (_cv_to_score(roe_roce_cv), weights.get("roe_roce_cv", 0.35)),
            (_cv_to_score(margin_cv), weights.get("margin_cv", 0.25)),
            (sales_vol_s, weights.get("sales_yoy_vol", 0.25)),
            (pos_pat, weights.get("positive_pat_years", 0.15)),
        ]
    )


def _extract_series(payload: Dict[str, Any]) -> Dict[str, Any]:
    sections = payload.get("sections") or {}
    pl_table = ((sections.get("profit_loss") or {}).get("table") if isinstance(sections.get("profit_loss"), dict) else None)
    pl = _table_row_map(pl_table)
    bs = _table_row_map(sections.get("balance_sheet"))
    cf = _table_row_map(sections.get("cash_flow"))
    ratios = _table_row_map(sections.get("ratios"))
    km = ((sections.get("pros_cons") or {}).get("key_metrics") or {})

    sales = pl.get("Sales") or pl.get("Revenue") or {}
    pat = pl.get("Net Profit") or pl.get("Profit after tax") or {}
    ocf = cf.get("Cash from Operating Activity") or {}
    borrowings = bs.get("Borrowings") or {}
    equity_cap = bs.get("Equity Capital") or {}
    reserves = bs.get("Reserves") or {}
    roce = ratios.get("ROCE %") or ratios.get("ROCE") or {}
    roe = ratios.get("ROE %") or ratios.get("ROE") or {}

    return {
        "sales": sales,
        "pat": pat,
        "ocf": ocf,
        "borrowings": borrowings,
        "equity_cap": equity_cap,
        "reserves": reserves,
        "roce": roce,
        "roe": roe,
        "km": km,
        "sections": sections,
    }


def _fiscal_years_available(series: Dict[str, Any]) -> List[int]:
    years = set()
    for key in ("sales", "pat", "roce", "roe", "borrowings"):
        for period in (series.get(key) or {}):
            y = _period_year(period)
            if y:
                years.add(y)
    return sorted(years)


def _metrics_at_year(series: Dict[str, Any], fiscal_year: int) -> Dict[str, Any]:
    sales = _periods_up_to(series["sales"], fiscal_year)
    pat = _periods_up_to(series["pat"], fiscal_year)
    ocf = _periods_up_to(series["ocf"], fiscal_year)
    borrowings = _periods_up_to(series["borrowings"], fiscal_year)
    equity_cap = _periods_up_to(series["equity_cap"], fiscal_year)
    reserves = _periods_up_to(series["reserves"], fiscal_year)
    roce = _periods_up_to(series["roce"], fiscal_year)
    roe = _periods_up_to(series["roe"], fiscal_year)

    sales_period, sales_latest, sales_prior = _latest_two_periods(sales)
    _, pat_latest, pat_prior = _latest_two_periods(pat)
    _, ocf_latest, _ = _latest_two_periods(ocf)
    bs_period, borrow_latest, _ = _latest_two_periods(borrowings)

    equity = None
    if bs_period and equity_cap and reserves:
        ec = equity_cap.get(bs_period)
        rs = reserves.get(bs_period)
        if ec is not None and rs is not None:
            equity = ec + rs

    dte = None
    if borrow_latest is not None and equity and equity > 0:
        dte = borrow_latest / equity

    margin = None
    if pat_latest is not None and sales_latest and sales_latest > 0:
        margin = pat_latest / sales_latest

    ocf_pat = None
    if ocf_latest is not None and pat_latest and abs(pat_latest) > 1e-9:
        ocf_pat = ocf_latest / pat_latest

    _, roce_latest, _ = _latest_two_periods(roce)
    _, roe_latest, _ = _latest_two_periods(roe)

    # CAGR over last 3 intervals if enough points
    sales_ord = _ordered_periods(sales)
    pat_ord = _ordered_periods(pat)
    sales_cagr = None
    pat_cagr = None
    if len(sales_ord) >= 4:
        first, last = sales_ord[-4][1], sales_ord[-1][1]
        sales_cagr = _cagr(first, last, 3)
    if len(pat_ord) >= 4:
        first, last = pat_ord[-4][1], pat_ord[-1][1]
        if first > 0 and last > 0:
            pat_cagr = _cagr(first, last, 3)

    return {
        "sales_period": sales_period,
        "sales_latest": sales_latest,
        "sales_prior": sales_prior,
        "pat_latest": pat_latest,
        "pat_prior": pat_prior,
        "sales_yoy": _yoy_growth(sales_latest, sales_prior),
        "pat_yoy": _yoy_growth(pat_latest, pat_prior),
        "sales_cagr": sales_cagr,
        "pat_cagr": pat_cagr,
        "margin": margin,
        "ocf_pat": ocf_pat,
        "dte": dte,
        "roce": roce_latest,
        "roe": roe_latest,
        "sales_map": sales,
        "pat_map": pat,
        "roce_map": roce,
        "roe_map": roe,
    }


def _lookback_series(period_map: Dict[str, float], fiscal_year: int, n: int) -> List[float]:
    ordered = [(p, v) for p, v in _ordered_periods(period_map) if (_period_year(p) or 0) <= fiscal_year]
    return [v for _, v in ordered[-n:]]


def _yoy_series(period_map: Dict[str, float], fiscal_year: int, n: int) -> List[float]:
    ordered = [(p, v) for p, v in _ordered_periods(period_map) if (_period_year(p) or 0) <= fiscal_year]
    out: List[float] = []
    for i in range(1, len(ordered)):
        g = _yoy_growth(ordered[i][1], ordered[i - 1][1])
        if g is not None:
            out.append(g)
    return out[-n:]


def _build_thesis(
    scores: Dict[str, Optional[float]],
    relatives: Dict[str, Any],
    metrics: Dict[str, Any],
    payload: Dict[str, Any],
    cfg: Dict[str, Any],
    mode: str,
) -> List[str]:
    support = float(cfg.get("support_threshold", 65))
    caution = float(cfg.get("caution_threshold", 40))
    max_n = int(cfg.get("thesis_max_bullets", 6))
    lines: List[str] = []

    pe_vs = relatives.get("pe_vs_sector_pct")
    if pe_vs is not None and mode == "current":
        if pe_vs < 0:
            lines.append(f"Below sector P/E ({pe_vs:.0f}% vs peers)")
        else:
            lines.append(f"Above sector P/E (+{pe_vs:.0f}% vs peers)")

    labels = {
        "quality": "Quality",
        "growth": "Growth",
        "value": "Value",
        "financial_health": "Financial health",
        "consistency": "Consistency",
    }
    for key, label in labels.items():
        val = scores.get(key)
        if val is None:
            continue
        if val >= support:
            lines.append(f"Strong {label.lower()} ({val:.0f}/100)")
        elif val <= caution:
            lines.append(f"Weak {label.lower()} ({val:.0f}/100)")

    if metrics.get("sales_yoy") is not None:
        period = metrics.get("sales_period") or "latest FY"
        lines.append(f"Sales growth {metrics['sales_yoy'] * 100:+.1f}% YoY ({period})")
    if metrics.get("pat_yoy") is not None:
        lines.append(f"PAT growth {metrics['pat_yoy'] * 100:+.1f}% YoY")

    pros_cons = ((payload.get("sections") or {}).get("pros_cons") or {})
    for p in (pros_cons.get("pros") or [])[:1]:
        text = str(p).strip()
        if text:
            lines.append(text[:120])
    for c in (pros_cons.get("cons") or [])[:1]:
        text = str(c).strip()
        if text:
            lines.append(f"Caution: {text[:110]}")

    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out[:max_n]


def compute_factors_for_payload(
    payload: Dict[str, Any],
    *,
    mode: str = "current",
    fiscal_year: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> FactorScores:
    cfg = config or load_factor_config()
    symbol = str(payload.get("symbol") or "").upper()
    scraped_at = str(payload.get("scraped_at") or "")
    series = _extract_series(payload)
    years = _fiscal_years_available(series)
    missing: List[str] = []
    inputs_used: List[str] = []

    if not years:
        return FactorScores(
            symbol=symbol,
            fiscal_year=None,
            quality=None,
            growth=None,
            value=None,
            financial_health=None,
            consistency=None,
            fundamental_risk=None,
            overall_fundamental=None,
            relatives={},
            thesis=[],
            as_of=scraped_at,
            missing_inputs=["annual_statements"],
            mode=mode,
        )

    fy = fiscal_year or years[-1]
    metrics = _metrics_at_year(series, fy)
    lookback = int(cfg.get("consistency_lookback_years", 5))
    financials = _is_financials(payload, cfg.get("financials_industry_keywords") or [])

    # Prefer key_metrics for current snapshot levels when FY is latest
    km = series["km"]
    pe = None
    dy = None
    if mode == "current" and fy == years[-1]:
        pe = _parse_number(km.get("Stock P/E"))
        dy_raw = _parse_pct(km.get("Dividend Yield"))
        if dy_raw is not None:
            dy = dy_raw / 100.0
        km_roe = _parse_pct(km.get("ROE"))
        km_roce = _parse_pct(km.get("ROCE"))
        if km_roe is not None:
            metrics["roe"] = km_roe
            inputs_used.append("key_metrics.ROE")
        if km_roce is not None:
            metrics["roce"] = km_roce
            inputs_used.append("key_metrics.ROCE")
        if pe is not None:
            inputs_used.append("key_metrics.PE")
        if dy is not None:
            inputs_used.append("key_metrics.DividendYield")

    promoter = _promoter_holding(payload) if mode == "current" else None
    if promoter is not None:
        inputs_used.append("shareholding")

    relatives: Dict[str, Any] = {}
    pe_vs = None
    roce_vs = None
    min_peers = int(cfg.get("min_peers_for_relative", 3))
    if mode == "current":
        peer_pes = _peer_values(
            payload,
            "P/E",
            pe_min=float(cfg.get("peer_pe_min", 8.0)),
            pe_max=float(cfg.get("peer_pe_max", 60.0)),
        )
        peer_roces = _peer_values(payload, "ROCE %")
        sector_pe = _median(peer_pes) if len(peer_pes) >= min_peers else None
        sector_roce = _median(peer_roces) if len(peer_roces) >= min_peers else None
        if pe is not None and sector_pe and sector_pe > 0:
            pe_vs = (pe - sector_pe) / sector_pe * 100.0
            inputs_used.append("peer_comparison")
        if metrics.get("roce") is not None and sector_roce is not None:
            roce_vs = metrics["roce"] - sector_roce
        relatives = {
            "pe": pe,
            "sector_pe_median": round(sector_pe, 2) if sector_pe is not None else None,
            "pe_vs_sector_pct": round(pe_vs, 1) if pe_vs is not None else None,
            "roce": metrics.get("roce"),
            "sector_roce_median": round(sector_roce, 2) if sector_roce is not None else None,
            "roce_vs_sector_pp": round(roce_vs, 1) if roce_vs is not None else None,
        }
    else:
        relatives = {"pe": pe, "note": "historical_snapshot_no_peer_table"}

    if metrics.get("sales_yoy") is not None:
        inputs_used.append("pnl_annual")
    if metrics.get("dte") is not None:
        inputs_used.append("balance_sheet")
    if metrics.get("ocf_pat") is not None:
        inputs_used.append("cash_flow")
    if metrics.get("roce") is not None or metrics.get("roe") is not None:
        inputs_used.append("ratios_annual")

    quality = _score_quality(
        roe=metrics.get("roe"),
        roce=metrics.get("roce"),
        margin=metrics.get("margin"),
        promoter=promoter,
        ocf_pat=metrics.get("ocf_pat"),
        weights=cfg.get("quality_weights") or {},
    )
    growth = _score_growth(
        sales_yoy=metrics.get("sales_yoy"),
        pat_yoy=metrics.get("pat_yoy"),
        sales_cagr=metrics.get("sales_cagr"),
        pat_cagr=metrics.get("pat_cagr"),
        weights=cfg.get("growth_weights") or {},
    )

    value_weights = (
        cfg.get("value_weights_current") if mode == "current" else cfg.get("value_weights_historical")
    ) or {}
    value = _score_value(
        pe=pe,
        pe_vs_sector_pct=pe_vs,
        dividend_yield=dy,
        roce_vs_peer=roce_vs,
        weights=value_weights,
    )

    pat_vals = _lookback_series(metrics["pat_map"], fy, lookback)
    pat_cv = _cv(pat_vals)
    health = _score_health(
        dte=metrics.get("dte"),
        interest_coverage=None,
        current_ratio=None,
        pat_cv=pat_cv,
        weights=cfg.get("health_weights") or {},
        financials=financials,
    )

    margin_series: List[float] = []
    for period, sales_v in _ordered_periods(metrics["sales_map"])[-lookback:]:
        pat_v = metrics["pat_map"].get(period)
        if pat_v is not None and sales_v and sales_v > 0:
            margin_series.append(pat_v / sales_v)

    consistency = _score_consistency(
        roe_series=_lookback_series(metrics["roe_map"], fy, lookback),
        roce_series=_lookback_series(metrics["roce_map"], fy, lookback),
        margin_series=margin_series,
        sales_yoy_series=_yoy_series(metrics["sales_map"], fy, lookback),
        pat_series=pat_vals,
        weights=cfg.get("consistency_weights") or {},
    )

    score_map = {
        "quality": quality,
        "growth": growth,
        "value": value,
        "financial_health": health,
        "consistency": consistency,
    }
    ow = cfg.get("overall_weights") or {}
    overall = _weighted_mean(
        [
            (quality, ow.get("quality", 0.25)),
            (growth, ow.get("growth", 0.20)),
            (value, ow.get("value", 0.20)),
            (health, ow.get("financial_health", 0.15)),
            (consistency, ow.get("consistency", 0.20)),
        ]
    )

    if quality is None:
        missing.append("quality_inputs")
    if growth is None:
        missing.append("growth_inputs")
    if value is None and mode == "current":
        missing.append("value_inputs")
    if health is None:
        missing.append("health_inputs")
    if consistency is None:
        missing.append("consistency_inputs")

    thesis = _build_thesis(score_map, relatives, metrics, payload, cfg, mode)

    return FactorScores(
        symbol=symbol,
        fiscal_year=fy,
        quality=quality,
        growth=growth,
        value=value,
        financial_health=health,
        consistency=consistency,
        fundamental_risk=health,
        overall_fundamental=overall,
        relatives=relatives,
        thesis=thesis,
        as_of=scraped_at,
        missing_inputs=missing,
        mode=mode,
        inputs_used=sorted(set(inputs_used)),
    )


def compute_all_current(store: FundamentalsStore, config: Optional[Dict[str, Any]] = None) -> Dict[str, FactorScores]:
    cfg = config or load_factor_config()
    out: Dict[str, FactorScores] = {}
    for path in sorted(store.by_symbol.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        sym = path.stem.upper()
        payload.setdefault("symbol", sym)
        out[sym] = compute_factors_for_payload(payload, mode="current", config=cfg)
    return out


def compute_all_historical(
    store: FundamentalsStore,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[int, Dict[str, FactorScores]]:
    cfg = config or load_factor_config()
    by_year: Dict[int, Dict[str, FactorScores]] = {}
    for path in sorted(store.by_symbol.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        sym = path.stem.upper()
        payload.setdefault("symbol", sym)
        series = _extract_series(payload)
        for fy in _fiscal_years_available(series):
            scores = compute_factors_for_payload(
                payload,
                mode="historical",
                fiscal_year=fy,
                config=cfg,
            )
            by_year.setdefault(fy, {})[sym] = scores
    return by_year


def scores_to_symbol_record(fs: FactorScores) -> Dict[str, Any]:
    return {
        "symbol": fs.symbol,
        "fiscal_year": fs.fiscal_year,
        "mode": fs.mode,
        "as_of": fs.as_of,
        "scores": {
            "quality": fs.quality,
            "growth": fs.growth,
            "value": fs.value,
            "financial_health": fs.financial_health,
            "consistency": fs.consistency,
            "fundamental_risk": fs.fundamental_risk,
            "overall_fundamental": fs.overall_fundamental,
        },
        "relatives": fs.relatives,
        "thesis": fs.thesis,
        "inputs_used": fs.inputs_used,
        "missing_inputs": fs.missing_inputs,
    }
