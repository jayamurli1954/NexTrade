# NexTrade — Platform Research Roadmap V1  
## After FI-2: Warehouse → Analytics → Query → FI-3 UI

**Status:** APPROVED FOR IMPLEMENTATION (Phase 7P research master roadmap)  
**Date:** 2026-08-04 (refined same day)  
**Context:** FI-1 + FI-2 complete. Formalize **Research Platform** as first-class capability.  
**Related:**  
- `docs/NEXTRADE_FUNDAMENTAL_INTELLIGENCE_LAYER_PLAN_V1.md`  
- `docs/NEXTRADE_FI2_OPPORTUNITY_FACTOR_DISPLAY_PLAN_V1.md`  
- `docs/NEXTRADE_DEFERRED_IMPLEMENTATION_MEMORY_V1.md`  
- `docs/NEXTRADE_QUANT_RESEARCH_STACK_EVALUATION_V1.md`

---

## 0. Architectural decision (formal)

> **Declare the Research Layer as a first-class platform capability.**

```text
Research Platform
├── Market Data Warehouse
├── Feature Store                 ← NEW (approved refinement)
├── Fundamental Intelligence      (FI-1/FI-2 DONE)
├── Technical Intelligence
├── Research Analytics Engine
├── Research Service              ← NEW platform API facade
├── Research Query Engine
└── AI Explanation Service        (rule-based now; LLM polish later)
```

| Product | Consumes |
|---------|----------|
| **NexTrade** | Full Research Platform + Execution & Risk |
| **InvestMitra** | Research Platform + portfolio / investment research — **never** execution |

### Approved dependency graph

```text
MDW (Market Data Warehouse)
        ↓
RAE (Research Analytics)
        ↓
Feature Store
        ↓
Research Service          ← single platform API: research_service.search(...)
        ↓
RQE (Query Engine)
        ↓
FI-3 Fundamental Research Center
```

Later (documented, not Sprint A): Research Notebook · Model Registry.

---

## 0. Verdict on FI-2

**FI-2 is complete and successful.** Do not reopen for feature creep.

| Strength | Why it matters |
|----------|----------------|
| Fundamental Service | Single abstraction for Opportunity / future Portfolio / AI / InvestMitra |
| Technical vs Investment Intelligence UI | Clear evidence separation |
| Rule-based AI Summary | Deterministic; LLM may polish later |
| Opportunity Strength (display-only) | Context without gate change |
| `use_factor_overall_for_gates = false` | Research ≠ execution |

**FI-3 UI is deliberately delayed** until Market Data Warehouse depth and Research Analytics / Query Engine exist — so the Research Center is immediately useful, not empty chrome.

---

## 1. Strategic shift

```text
FROM:  add feature → add feature → add feature
TO:    finish foundations → analytics leverage → shared query → UI that consumes both
```

### Platform engines (target)

```text
1. Market Data Engine          ← Priority 1 (complete warehouse)
2. Fundamental Intelligence    ← FI-1/FI-2 DONE (service + store)
3. Technical Analysis Engine   ← exists (EnhancedAnalyzer)
4. Research Analytics Engine   ← Priority 2 (NEW)
5. Research Query Engine       ← Priority 2.5 (NEW — before FI-3 UI)
6. Opportunity Intelligence    ← FI-2 DONE (explainability)
7. Execution & Risk Engine     ← freeze-isolated until promotion
```

**Product split**

| Product | Consumes |
|---------|----------|
| **NexTrade** | All engines |
| **InvestMitra** | Market Data + Fundamental + Research Analytics + Query (+ portfolio UX). **Never** execution / risk overrides |

---

## 2. Priority order (approved steering — refined)

| Pri | ID | Name | Why |
|-----|-----|------|-----|
| **P1** | **MDW-*** | Market Data Warehouse | Real options/OI/PCR; unblocks ARASS |
| **P2** | **RAE-*** | Research Analytics Engine | Distributions, history, leaders |
| **P2.5** | **FS-*** | Feature Store | Unified date×symbol feature rows (tech + fund + macro) |
| **P2.6** | **RS-*** | Research Service | Platform API facade over warehouse/analytics/factors/query |
| **P2.7** | **RQE-*** | Research Query Engine | Shared filters behind Research Service |
| **P3** | **FI-3** | Fundamental Research Center UI | Thin client over Research Service |
| **P4** | **IM-*** | InvestMitra bind | Same Research Service — no trading imports |
| Later | **RN-*** / **MR-*** | Research Notebook / Model Registry | Quant lab UX + strategy versioning |
| Later | FI-4 / FI-5 / AST / Margin | Post-freeze | As previously deferred |

### Sprint A (DONE)

1. **MDW-1** — Options lookup hardening + ARASS hit-rate diagnostic + entry uses real premiums when store hits  
2. **MDW-7** — Warehouse facade skeleton  
3. **FS-0 / RS-0** — Feature Store + Research Service scaffolds  

### Sprint B (APPROVED PLAN)

**Plan:** `docs/NEXTRADE_SPRINT_B_FEATURE_PLATFORM_PLAN_V1.md`  

```text
B1 Feature Store backfill + Feature Registry + feature_panel()
B2 RAE-1…4
B3 Research Query Engine
B4 MDW-3 OI → B5 MDW-4 PCR
B6 FI-3 Research Center
```

Start coding at **B1a/B1b** (registry + fundamental PIT + `feature_panel`).

---

## 3. Priority 1 — Market Data Warehouse (MDW)

### 3.1 Current state

| Asset | Status |
|-------|--------|
| Index / VIX Excel loader | Done (`excel_index_loader`) |
| NIFTY options daily OHLC (jugaad) | Partial — `research/data/options/nifty_options_daily.csv` (~2024–2026 ATM CE/PE) |
| ARASS options lookup | Fragile hit rate (daily vs expanded bars) |
| Open Interest | Missing |
| PCR | Missing |
| Futures OHLC | Missing |
| Economic calendar | Missing |
| BANKNIFTY options | Missing / optional |

### 3.2 Goals

Build a **versioned, research-only warehouse** that backtests and analytics can query with provenance — never as live execution authority.

```text
research/data/market_warehouse/
├── index/           # NIFTY, BANKNIFTY, INDIAVIX daily (+ optional 5m later)
├── options/         # already started; normalize layout
├── futures/         # FUTIDX daily OHLC
├── oi/              # open interest by contract / expiry
├── derived/         # PCR, term structure snapshots
├── calendar/        # economic / event calendar
└── manifests/       # build dates, row counts, provenance
```

### 3.3 Work packages

| ID | Deliverable | Exit criteria | Freeze |
|----|-------------|---------------|--------|
| **MDW-1** | Options store hardening | Schema + expiry/ATM lookup docs; ARASS hit-rate diagnostic + tighter join (date+expiry+strike); resume-safe download CLI | Research OK |
| **MDW-2** | Options history depth | Extend NIFTY CE/PE beyond current window where jugaad allows; optional BANKNIFTY | Research OK |
| **MDW-3** | Open Interest ingest | Daily OI per contract (or expiry aggregate) + manifest | Research OK |
| **MDW-4** | PCR + derived series | Put/Call OI (and/or volume) PCR daily for NIFTY | Research OK |
| **MDW-5** | Futures OHLC | NIFTY/BANKNIFTY near-month futures daily store | Research OK |
| **MDW-6** | Economic calendar | Minimal INR-relevant event calendar (RBI / CPI / GDP / elections stubs) + as-of join helper | Research OK |
| **MDW-7** | Warehouse facade | `research/market_warehouse.py` — load index/options/OI/PCR/futures/calendar with provenance strings | Research OK |

### 3.4 Non-goals (MDW)

- Live Angel streaming as warehouse authority (OIE-001 already owns live quotes)
- Using warehouse prices for paper fills
- Full tick history / HFT microstructure

### 3.5 Suggested build order

```text
MDW-1 (lookup fix) → MDW-7 facade skeleton
     → MDW-3 OI → MDW-4 PCR
     → MDW-2 depth / MDW-5 futures (parallelizable)
     → MDW-6 calendar
```

**Estimate:** multi-session; MDW-1 alone is highest ARASS value.

---

## 4. Priority 2 — Research Analytics Engine (RAE)

### 4.1 Goal

Turn FI-1 factor archives + (later) strategy results into **reusable analytics tables**, not charts-first UI.

```text
Factor Store + Historical Factors + (optional) backtest trade logs
        ↓
Research Analytics Engine
        ↓
Parquet/JSON analytics products
        ↓
Query Engine / FI-3 / InvestMitra / AI
```

### 4.2 Analytics products (v1)

| ID | Product | Description |
|----|---------|-------------|
| **RAE-1** | Factor distribution | Histograms / quantiles for Q,G,V,H,C,Overall across 86 names |
| **RAE-2** | Factor history panels | Per-symbol time series from `historical/YYYY.json` |
| **RAE-3** | Factor correlation | Cross-sectional corr matrix (Quality↔Growth etc.) |
| **RAE-4** | Improvement leaders | Δ Overall / Δ Quality over 1Y and 3Y |
| **RAE-5** | Strategy × factor join | When ARASS / equity scan logs exist: win rate, expectancy by Quality/Value buckets |
| **RAE-6** | Sector / peer slices | Aggregate scores by Screener sector/industry |

### 4.3 Module sketch

```text
research/analytics/
  __init__.py
  factor_distributions.py
  factor_history.py
  strategy_factor_join.py
  build_research_analytics.py   # CLI
research/data/analytics/
  factor_distribution.json
  factor_history_panel.parquet  # or CSV if parquet optional
  improvement_leaders.csv
  manifests/analytics_build.json
```

### 4.4 Freeze / authority

- Research-only outputs  
- Must not feed execution gates  
- Strategy×factor joins use **logged** research trades only, not live paper without provenance tags  

**Estimate:** 1–2 sessions after factor store stable (can start RAE-1…4 immediately; RAE-5 after better MDW/ARASS logs).

---

## 5. Priority 2.5 — Research Query Engine (RQE)

### 5.1 Goal

One internal query API so FI-3 / Portfolio / AI / Scanner don’t reinvent filters.

### 5.2 Example queries

```text
Quality > 80 AND Growth > 70 AND Value > 60
Companies with largest Quality improvement over 3 years
Value↑ and Consistency > 70 (cross-section)
As-of FY2022: Quality > 75 (point-in-time — look-ahead safe)
```

### 5.3 API sketch

```python
# research/research_query_engine.py

@dataclass
class FactorQuery:
    fiscal_year: Optional[int] = None   # None = current
    min_quality: Optional[float] = None
    min_growth: Optional[float] = None
    min_value: Optional[float] = None
    min_health: Optional[float] = None
    min_consistency: Optional[float] = None
    min_overall: Optional[float] = None
    improved_quality_years: Optional[int] = None  # e.g. 3
    sector_contains: Optional[str] = None
    limit: int = 50
    sort_by: str = "overall_fundamental"

def query_factors(q: FactorQuery) -> List[dict]: ...
```

### 5.4 Work packages

| ID | Deliverable |
|----|-------------|
| **RQE-1** | Current-universe filter/sort |
| **RQE-2** | Historical as-of + improvement queries |
| **RQE-3** | Optional DSL / JSON query doc for AI assistants |
| **RQE-4** | Unit tests with fixture factor store |

**Depends on:** FI-1 store (done). Benefits from RAE-2/4 but can ship RQE-1 in parallel.

**InvestMitra:** same `query_factors` — no trading imports.

---

## 6. Priority 3 — FI-3 Fundamental Research Center (UI)

**Only after** RQE-1 (minimum) and ideally RAE-1/2/4.

### 6.1 Scope

| Surface | Content |
|---------|---------|
| Universe table | Symbol · Q · G · V · H · C · Overall · Δ1Y · sector · as-of FY |
| Filters | Driven by Research Query Engine (not ad-hoc JS filters on raw JSON) |
| Symbol drill-down | Factor history sparkline + thesis + peers (via Fundamental Service) |
| Analytics tabs | Embed RAE distribution / leaders (read-only) |

### 6.2 Naming

Use **Fundamental Research Center** (not “Research Dashboard”).

### 6.3 Non-goals

- Changing opportunity ranking  
- Editing factor weights in UI (config stays file-based until FI-4)  

**Plan doc when approved to build:** `docs/NEXTRADE_FI3_FUNDAMENTAL_RESEARCH_CENTER_PLAN_V1.md` (create at build time).

---

## 7. Priority 4 — InvestMitra bind (IM)

| ID | Item |
|----|------|
| **IM-1** | Document Fundamental Service as shared contract (no trading types) |
| **IM-2** | InvestMitra reads `get_symbol_intelligence` / `query_factors` only |
| **IM-3** | InvestMitra UI: Investment Intelligence panel (no BUY ticket) |

**Boundary (existing):** InvestMitra may emit hypothesis/evidence — never Execute / qty / risk override.

---

## 8. Freeze & authority matrix

| Work | Phase 7P |
|------|----------|
| MDW downloads, stores, ARASS research fixes | **Allowed** (research) |
| RAE / RQE offline builds + APIs | **Allowed** |
| FI-3 read-only UI | **Allowed** if no gate changes |
| InvestMitra fundamental panels | **Allowed** (no execution) |
| Factors → BUY confidence / ranking | **BLOCKED** (FI-4) |
| Warehouse as paper fill price | **Forbidden** |

---

## 9. Suggested near-term sequence (concrete)

### Sprint A — Warehouse spine
1. MDW-1 options lookup + ARASS hit-rate report  
2. MDW-7 facade stub  
3. MDW-3 OI prototype for NIFTY  

### Sprint B — Analytics + query
1. RAE-1 distributions + RAE-4 improvement leaders  
2. RQE-1 current filter API + tests  
3. Optional RAE-2 history panel  

### Sprint C — Research Center UI
1. FI-3 plan + build table/filters on RQE  
2. Symbol drill-down via Fundamental Service  

### Sprint D — Cross-product
1. IM-1/IM-2 contract + InvestMitra panel spike  

---

## 10. Success metrics

| Layer | Metric |
|-------|--------|
| MDW | ARASS real-premium hit rate ≫ current (~9/day-scale misses); OI/PCR series continuous for download window |
| RAE | Rebuild CLI produces distribution + leaders for ≥80 symbols |
| RQE | Query `Q>80 & G>70 & V>60` returns deterministic set |
| FI-3 | UI is thin client over RQE (no duplicated filter logic) |
| InvestMitra | Zero imports from `trading_app.opportunity_engine` / execution |

---

## 11. Explicitly deferred (do not sneak into Sprint A)

- FI-4 gate promotion  
- Capital Allocation / Earnings Surprise scores  
- VectorBT / GS-P2+ / Margin M1–M6  
- LLM-authored scores  
- Oracle Angel hosting  

---

## 12. Decision required from you

~~Approve reorder~~ — **APPROVED** with Feature Store + Research Service + Research Platform formalization.

**Sprint A in progress:** MDW-1 + MDW-7 skeleton + FS-0/RS-0 scaffolds.

---

## 13. Change log

| Date | Change |
|------|--------|
| 2026-08-04 | Initial platform roadmap after FI-2 success; FI-3 deprioritized behind MDW/RAE/RQE |
| 2026-08-04 | Approved: Feature Store + Research Service; Research Platform formalized; Sprint A = MDW-1 |
