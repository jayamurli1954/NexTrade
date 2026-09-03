# NexTrade — Fundamental Intelligence Layer Plan V1.1

**Status:** APPROVED FOR FI-1 (research-first; live ranking gated by Phase 7P)  
**Date:** 2026-08-04 (refined same day)  
**Depends on:** Local fundamentals repository (`research/data/fundamentals/`) — **DONE**  
**Related:** `docs/NEXTRADE_DEFERRED_IMPLEMENTATION_MEMORY_V1.md`, Phase 7P / OIE-001  

---

## 0. Platform positioning

Fundamental Intelligence is a **core platform service**, not an Opportunity-only helper:

| # | Engine | Role |
|---|--------|------|
| 1 | Market Data Engine | OHLC, VIX, options, OI |
| 2 | **Fundamental Intelligence Engine** | Factor scores, thesis, history |
| 3 | Technical Analysis Engine | EMA, RSI, ATR, volume, fib |
| 4 | AI Intelligence Engine | Explains scores; never invents them |
| 5 | Risk & Portfolio Engine | Consumes factors for portfolio health |
| 6 | Backtesting & Research Engine | Point-in-time fundamentals only |

```text
Raw Fundamentals (local JSON / long CSV)
        ↓
Fundamental Intelligence Engine
        ↓
Current Factor Scores + Historical Factor Archive + Thesis
        ↓
┌───────────────┬──────────────┬─────────────┬──────────────┐
│ Opportunity   │ Portfolio    │ AI Explain  │ Backtest     │
│ Engine        │ Engine       │ Engine      │ / Research   │
└───────────────┴──────────────┴─────────────┴──────────────┘
```

**Hard rules**

1. Opportunity / Portfolio / AI must **not** interpret raw P/E or ROE.  
2. Scores are **rule-based and deterministic**. LLM explains; it does not score.  
3. Backtests must load **point-in-time** historical factors — never 2026 ROE for a 2019 bar (look-ahead bias).

---

## 1. What already exists (do not rebuild)

| Asset | Location | Role |
|-------|----------|------|
| Per-symbol fundamentals JSON | `research/data/fundamentals/by_symbol/*.json` | Raw store (86 watchlist) |
| Long CSVs | `research/data/fundamentals/long/*.csv` | Research joins |
| Annual ratios / P&L / BS / CF history | Same JSON sections | **Input for historical factors** |
| Loader + highlights | `research/fundamentals_loader.py` | Metrics + light bullets |
| Analyzer bridge | `analyzer/fundamentals_analyzer.py` | Local-first score + highlights |
| Opportunity append | `trading_app/opportunity_engine.py` | Highlights → `why_this_trade` |
| Peer tables | `peer_comparison` | Sector P/E, ROCE (current only) |

---

## 2. Factor set

### v1 (FI-1) — implement now

| Score | Range | Purpose |
|-------|-------|---------|
| Quality | 0–100 | ROE, ROCE, margins, cash conversion, promoter |
| Growth | 0–100 | Sales / PAT YoY + multi-year CAGR |
| Value | 0–100 | Absolute + peer-relative valuation (current); absolute-only historically |
| Financial Health | 0–100 | Leverage, earnings stability, liquidity |
| **Consistency** | 0–100 | Stability of ROE / margins / sales growth over trailing years |
| Fundamental Risk | 0–100 | Higher = safer (v1 ≈ Health remap) |
| Overall Fundamental | 0–100 | Weighted blend |

### v1.1 / later

| Score | Phase | Purpose |
|-------|-------|---------|
| **Capital Allocation** | FI-5a | Dividend policy, debt reduction, OCF vs capex deployment |
| **Earnings Surprise** | FI-5b | Actual vs expected EPS (needs estimates feed) |

---

## 3. Storage layout (current + historical)

**Approved enhancement:** do not store only a single `factor_scores.json`.

```text
research/data/fundamentals/
├── by_symbol/                 # raw Screener payloads (existing)
├── long/                      # long CSVs (existing)
├── current/
│     factor_scores.json       # latest snapshot, all symbols
│     factor_scores_table.csv  # research dashboard sort view
├── historical/
│     2015.json                # FY ending that calendar year (Mar/Dec…)
│     2016.json
│     …
│     2026.json
└── manifests/
      factor_build_manifest.json
```

### Current vs historical semantics

| Store | Value / peers | Consistency | Use |
|-------|---------------|-------------|-----|
| `current/` | Full peer-relative Value | Trailing window ending latest FY | Scanner, Opportunities, Portfolio, AI |
| `historical/YYYY.json` | Absolute Value only (no peer look-ahead); peers omitted | Trailing window ending that FY | Backtests, “is quality improving?” |

Each historical file:

```json
{
  "fiscal_year": 2024,
  "built_at": "...",
  "symbols": {
    "RELIANCE": { "scores": { "...": 0 }, "missing_inputs": [] }
  }
}
```

---

## 4. Factor definitions (deterministic)

Missing inputs → omit that sub-leg; reweight remaining legs. Do not invent.

### 4.1 Quality

| Input | Weight | Sketch |
|-------|--------|--------|
| ROE % | 25% | Higher better; soft cap ~25% |
| ROCE % | 30% | Higher better; soft cap ~30% |
| Profit margin (PAT/Sales) | 20% | Higher better |
| Promoter holding (latest; current only) | 15% | Prefer stable/high |
| OCF / PAT | 10% | Cash ≥ profit preferred |

### 4.2 Growth

| Input | Weight | Sketch |
|-------|--------|--------|
| Sales YoY | 35% | Banded |
| PAT YoY | 35% | Banded |
| Sales CAGR 3Y | 15% | If ≥3 periods |
| PAT CAGR 3Y | 15% | If ≥3 periods |

### 4.3 Value

| Input | Weight | Sketch |
|-------|--------|--------|
| Stock P/E absolute | 30% (current) / 70% (historical) | Exclude &lt;0 or &gt;80 |
| Peer-relative P/E | 40% (current only) | vs peer median |
| Dividend yield | 15% | Modest bonus |
| Peer-relative ROCE | 15% (current only) | vs peer median |

### 4.4 Financial Health

| Input | Weight | Sketch |
|-------|--------|--------|
| Debt / Equity | 45% | Lower better; wider bands for Bank/Finance |
| Interest coverage (if present) | 25% | Else redistribute |
| Current ratio (if present) | 15% | Prefer &gt;1.2 |
| PAT volatility (3–5Y) | 15% | Lower better |

### 4.5 Consistency (NEW — FI-1)

Trailing 4–5 fiscal years ending at the snapshot year:

| Input | Weight | Sketch |
|-------|--------|--------|
| ROE / ROCE coefficient of variation | 35% | Lower CV → higher score |
| Profit margin CV | 25% | Lower better |
| Sales YoY volatility | 25% | Lower better |
| Sign stability (positive PAT years) | 15% | Fewer loss years better |

Unstable “25 → 5 → 30” ROE scores poorly; steady “17 → 18 → 19 → 20” scores well.

### 4.6 Capital Allocation (FI-5a — design only)

| Input | Idea |
|-------|------|
| Dividend payout trend | Sustainable vs erratic |
| Borrowings YoY | Debt reduction preferred (non-financials) |
| OCF vs Investing | Capex funded by operations |
| Buybacks | If/when field available |

### 4.7 Earnings Surprise (FI-5b — design only)

Requires external estimates. Deferred until estimate feed exists. Quarterly actuals alone are not a surprise score.

### 4.8 Overall Fundamental (v1)

```text
Overall = 0.25·Quality + 0.20·Growth + 0.20·Value
        + 0.15·Health + 0.20·Consistency
```

Config-driven; Financials industry uses wider D/E bands.

---

## 5. Investment Thesis generator

Rule-based (not LLM):

1. Supporting factors (score ≥ 65) → positive bullets  
2. Weak factors (score ≤ 40) → caution bullets  
3. Peer-relative PE line when peers exist (current only)  
4. Consistency callout when ≥ 75 or ≤ 40  
5. Up to 2 Screener pros/cons (truncate)  
6. Cap **6** thesis bullets  

---

## 6. Downstream consumers (beyond Opportunity)

| Consumer | Reads | Phase |
|----------|-------|-------|
| Opportunity Engine | Current scores + thesis | FI-2 (display) / FI-4 (ranking) |
| **Portfolio Engine** | Portfolio-weighted Q/G/V/H/C averages | FI-4+ |
| Research Dashboard | Sortable Q/G/V/H/C/Overall table | FI-3 |
| AI Explain | Same table (“Why #3?”, “Is Reliance improving?”) | FI-4 |
| Backtest / ARASS | `historical/YYYY.json` as-of bar date | FI-5 / research |

Portfolio health example:

```text
Portfolio avg: Quality 78 · Growth 65 · Value 52 · Health 90 · Consistency 71
AI: “Your book is overpaying for growth (Value lagging).”
```

---

## 7. Phased delivery

### FI-0 — Freeze

| Work | Posture |
|------|---------|
| Offline factor batch + history + tests | **Allowed** |
| Display scores/thesis without changing gates | **Allowed** |
| Factors change ranking / confidence | **BLOCKED** until unfreeze |

### FI-1 — Factor engine + current/historical store  ← **BUILD NOW**

1. `research/fundamental_factor_engine.py`  
2. `research/factor_score_store.py`  
3. `config/fundamental_factors.json`  
4. CLI `python -m research.build_fundamental_factors`  
5. Outputs under `current/` + `historical/` + `manifests/`  
6. Unit tests (fixtures; no network)

**Exit criteria**

- ≥95% watchlist symbols with Overall (current)  
- Historical years emitted for every FY present in annual tables (where computable)  
- Deterministic rebuild  
- Peer-relative PE when ≥3 peer PEs (current only)  
- Consistency score present when ≥3 trailing years  

### FI-2 — Analyzer / Opportunity display (gates unchanged)

**Plan:** `docs/NEXTRADE_FI2_OPPORTUNITY_FACTOR_DISPLAY_PLAN_V1.md`  
**Status:** DONE (2026-08-04)

Display Investment Intelligence (thesis, badges, trends, AI summary, as-of FY) via `FundamentalService`.  
Gate score stays legacy blend (`use_factor_overall_for_gates: false`) until FI-4.

### FI-3 — Fundamental Research Center (UI)

**Status:** READY TO PLAN — **deprioritized** behind MDW / RAE / RQE  
**Roadmap:** `docs/NEXTRADE_PLATFORM_RESEARCH_ROADMAP_V1.md`  

Build only after Research Query Engine (minimum RQE-1). Prefer richer analytics tabs from RAE.

### FI-4 — Strategy + Portfolio + AI consumption (POST-FREEZE)

### FI-5 — Enrichment

Capital Allocation · Earnings Surprise · sector profiles · PEG/EV · Overall AI Rating composer · backtest as-of loader

---

## 8. FI-1 implementation checklist

### Engine API

```python
@dataclass
class FactorScores:
    symbol: str
    fiscal_year: Optional[int]       # None = current snapshot
    quality: Optional[float]
    growth: Optional[float]
    value: Optional[float]
    financial_health: Optional[float]
    consistency: Optional[float]
    fundamental_risk: Optional[float]
    overall_fundamental: Optional[float]
    relatives: Dict[str, Any]
    thesis: List[str]
    as_of: str
    missing_inputs: List[str]
    mode: str  # "current" | "historical"
```

### Store API

```python
class FactorScoreStore:
    def save_current(self, scores: Dict[str, FactorScores]) -> Path: ...
    def save_historical_year(self, year: int, scores: Dict[str, FactorScores]) -> Path: ...
    def load_current(self, symbol: str) -> Optional[dict]: ...
    def load_as_of(self, symbol: str, fiscal_year: int) -> Optional[dict]: ...
```

### Tests

| Test | Assert |
|------|--------|
| DEMO fixture | Known Q/G/V/H/C |
| RELIANCE peers | Sector PE median & % cheaper |
| Consistency | High CV series scores lower than stable series |
| Historical | FY snapshot does not use later-year P&L |
| Idempotent rebuild | Stable scores |

---

## 9. Non-goals (v1)

- Live Screener scrape in scanner loop  
- Factor engine as execution / risk authority  
- LLM-authored scores  
- Earnings surprise without estimate feed  
- Auto-promotion into live strategy gates  

---

## 10. Success metrics

| Metric | Target |
|--------|--------|
| Current coverage | ≥95% Overall |
| Historical depth | Multi-year files for symbols with ≥5 FY rows |
| Look-ahead safety | Historical Value never uses current peer table |
| Scan latency | Factor load from disk &lt;5 ms/symbol |
| Freeze safety | Confidence formula unchanged until FI-4 |

---

## 11. Change log

| Date | Change |
|------|--------|
| 2026-08-04 | V1.0 initial plan |
| 2026-08-04 | V1.1: Consistency; current+historical store; Capital Allocation & Earnings Surprise deferred; Portfolio/Research/AI consumers; core platform positioning; FI-1 approved |
