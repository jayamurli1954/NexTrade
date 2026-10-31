# NexTrade — Sprint B Implementation Plan V1  
## Feature Store Backfill → Analytics → Query → OI/PCR → FI-3

**Status:** APPROVED + B1a/B1b IN IMPLEMENTATION (research platform; execution freeze unchanged)  
**Date:** 2026-08-04  
**Depends on:** Sprint A DONE (MDW-1 soft lookup 84%, MDW-7, FS-0, RS-0)  
**Parent:** `docs/NEXTRADE_PLATFORM_RESEARCH_ROADMAP_V1.md`  
**Freeze:** Research-only. No change to BUY/SELL gates, confidence, or risk limits.

### Approved refinements (2026-08-04)

| Addition | Notes |
|----------|-------|
| `feature_panel` **metadata** | `feature_store_version`, `build_date`, `as_of`, `lookahead_safe` |
| **Feature provenance** | Registry: source → transformation → version → status |
| **RAE-7** Feature Coverage Report | After RAE-1…4; data-quality table |
| **Data Validation Engine (DVE-0)** | Scaffold in B1; nightly checks later |
| **ResearchQuery** naming | Evolve `FactorQuery` → generic query (B3) |
| **SanMitra Research Platform** | Formal product name for shared layer |
| Sprint C preview | FI-3 → InvestMitra → RN-1 → RAE-5 → MR-1 |

---

## 0. Context & verdict on Sprint A

Sprint A crossed the **research backbone** milestone:

| Item | Result |
|------|--------|
| MDW-1 soft options lookup | Exact 0% → soft **84%** (200-day sample) |
| MDW-7 warehouse facade | Skeleton live |
| FS-0 / RS-0 | Contracts live; backfill deferred to Sprint B |

**Steering change (approved):** Do **not** lead with MDW-3/4. Sequence is:

```text
B1 Feature Store backfill (+ Feature Registry)
        ↓
B2 Research Analytics (RAE-1…4)
        ↓
B3 Research Query Engine (behind Research Service)
        ↓
B4 MDW-3 Open Interest
        ↓
B5 MDW-4 PCR
        ↓
B6 FI-3 Fundamental Research Center
```

**Abstraction rule:** Technical indicators, fundamental factors, and market series are all **Features**. No module re-derives them ad hoc when the Feature Store has them.

---

## 1. Target architecture (Sprint B end-state)

```text
                  ┌─────────────────────────────┐
                  │     Research Platform       │
                  └─────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   Market Warehouse      Feature Store       Fundamental Engine
   (+ OI/PCR later)     (+ Registry)              │
        │                      │                      │
        └──────────────┬───────┴──────────────┬───────┘
                       │                      │
                Research Analytics      Research Service
                       │               search / symbol_intelligence
                       │               feature_panel(symbol, as_of)
                       └──────────┬───────────┘
                                  │
                         Research Query Engine
                                  │
               ┌──────────────────┼──────────────────┐
               │                  │                  │
           NexTrade         InvestMitra        AI Assistant
```

---

## 2. Sprint B work packages

### B1 — Feature Store Backfill + Feature Registry  ⭐ highest leverage

#### B1.1 Feature Registry

**New:** `research/feature_registry.py` + `research/data/feature_store/registry.json`

```json
{
  "rsi": {
    "name": "RSI",
    "version": "1.0",
    "family": "technical",
    "source": "technical_engine",
    "frequency": "daily",
    "status": "research",
    "description": "14-period RSI on NSE equity close"
  },
  "quality": {
    "name": "Quality",
    "version": "1.1",
    "family": "fundamental",
    "source": "fundamental_factor_engine",
    "frequency": "as_of_fiscal",
    "status": "research"
  }
}
```

| Field | Purpose |
|-------|---------|
| version | Reproducibility when math changes |
| family | technical \| fundamental \| market \| portfolio |
| source | Owning engine |
| frequency | daily \| as_of_fiscal \| event |
| status | research \| production (production = post-freeze promotion only) |

**Exit:** Registry lists all columns written by B1.2; unit test validates required keys.

#### B1.2 Feature panel backfill

**CLI:** `python -m research.build_feature_store`

| Family | Columns (v1) | Source |
|--------|--------------|--------|
| Keys | `date`, `symbol` | — |
| Technical | `rsi`, `ema20`, `ema50`, `atr`, `adx` (optional `vwap`) | Daily OHLC via existing data provider / yfinance research path / local cache |
| Fundamental | `quality`, `growth`, `value`, `financial_health`, `consistency`, `overall_fundamental` | Factor store current + **point-in-time** from `historical/YYYY.json` mapped to calendar dates (FY end) |
| Market | `vix` | Index/VIX Excel or warehouse; broadcast to all symbols that day |
| Market (stub) | `pcr`, `oi` | Null until B4/B5; columns reserved |

**Universe:** Watchlist (86) + optional `NIFTY` index row for market-only features.

**Date range (v1 default):** Last **2 years** trading days (config); extend later.

**Storage:**

```text
research/data/feature_store/
  features_daily.csv          # or parquet if available
  registry.json
  manifests/feature_build.json
```

**Look-ahead rules**

- Fundamental columns for calendar date `D` use latest fiscal snapshot with `FY_end ≤ D` (never future FY).  
- Technicals use only bars ≤ `D`.  
- VIX uses same-day (or prior close if missing).

**Exit:** ≥80 symbols × ≥200 dates with non-null RSI + Overall (or documented miss); deterministic rebuild; manifest with row counts + provenance.

#### B1.3 Research Service — `feature_panel`

```python
def feature_panel(self, symbol: str, as_of_date: str) -> Optional[dict]:
    """
    {
      "symbol": "TCS",
      "as_of": "2026-07-28",
      "technical": {"rsi": 64, "ema20": ..., "ema50": ..., "atr": ..., "adx": ...},
      "fundamental": {"quality": 88, "growth": 60, ...},
      "market": {"vix": 14.2, "pcr": null, "oi": null},
      "metadata": {
        "feature_store_version": "1.0",
        "build_date": "2026-08-04T...",
        "as_of": "2026-07-28",
        "lookahead_safe": true,
        "feature_versions": {"quality": "1.1", "rsi": "1.0"},
        "provenance": {"quality": "fundamental_factor_engine@1.1"}
      }
    }
    """
```

Deprecate raw flat `features_for` as primary API (keep as thin alias).

**Consumers (read-only):** AI summary seeds, future scanner, InvestMitra, backtests — **not** execution gates in Sprint B.

---

### B2 — Research Analytics Engine (RAE-1…4)

**Package:** `research/analytics/`

| ID | Product | Output |
|----|---------|--------|
| **RAE-1** | Factor distributions | Quantiles / histogram bins for Q,G,V,H,C,Overall (current universe) |
| **RAE-2** | Factor history panels | Per-symbol series from historical factor years |
| **RAE-3** | Factor correlation | Cross-sectional corr matrix |
| **RAE-4** | Improvement leaders | Δ1Y / Δ3Y Quality & Overall rankings |
| **RAE-7** | Feature Coverage Report | % non-null per feature column (data quality) |

**CLI:** `python -m research.build_research_analytics`

**Outputs:** `research/data/analytics/` (+ manifest)

**Prefer:** Read via Feature Store / FactorScoreStore — not re-scrape Screener.

**Exit:** Rebuild CLI; unit tests on fixtures; leaders CSV non-empty for ≥50 symbols with history.

---

### B3 — Research Query Engine (RQE)

**Module:** `research/research_query_engine.py`  
**Facade:** `ResearchService.search` delegates to RQE (single public API).

Prefer generic name **`ResearchQuery`** (alias `FactorQuery` for back-compat) so filters can combine fundamentals + technicals + market:

```text
Quality > 80 AND RSI < 35 AND VIX > 18 AND Sector = IT
```

**Exit:** Query `Quality>80 AND Growth>70 AND Value>60` deterministic; as-of / improvement queries covered by tests; InvestMitra-safe (no `trading_app` imports).

---

### B4 — MDW-3 Open Interest

| Deliverable | Notes |
|-------------|-------|
| OI in options store / warehouse | Prefer columns already in jugaad CSV (`oi`, `CHANGE IN OI`) — **normalize & expose** before new downloads |
| Daily OI series by expiry/strike | Warehouse path `market_warehouse/oi/` or derived from options long table |
| Feature Store column `oi` | Aggregate (e.g. ATM straddle OI or total expiry OI) joined by date for index symbol |

**Exit:** Non-null `oi` feature for NIFTY on ≥70% of feature dates in overlap window; provenance in manifest.

---

### B5 — MDW-4 PCR

| Deliverable | Notes |
|-------------|-------|
| Put/Call OI (and/or volume) PCR daily | Derived from options warehouse |
| `market_warehouse/derived/nifty_pcr_daily.csv` | |
| Feature Store `pcr` | Broadcast to symbols / index row |

**Exit:** PCR series continuous for download window; `feature_panel(...).market.pcr` populated for recent dates.

---

### B6 — FI-3 Fundamental Research Center (UI)

**Only after B3 (minimum).** Prefer after B2 analytics artifacts exist.

| Surface | Behavior |
|---------|----------|
| Universe table | Via `ResearchService.search` / RQE — no client-side filter reinvent |
| Symbol drill-down | `symbol_intelligence` + `feature_panel` |
| Analytics tabs | Embed RAE-1/4 outputs |
| Naming | **Fundamental Research Center** |

**Separate build plan when starting B6:** `docs/NEXTRADE_FI3_FUNDAMENTAL_RESEARCH_CENTER_PLAN_V1.md`

---

## 3. Explicit non-goals (Sprint B)

| Do not | Why |
|--------|-----|
| Change `use_factor_overall_for_gates` | Freeze / FI-4 |
| LLM-authored features | Deterministic research only |
| Full tick / HFT features | Out of scope |
| Max Pain / breadth (nice-to-have) | Reserve columns; implement after B5 |
| Research Notebook / Model Registry | Documented later (RN-1 / MR-1) |
| Live Angel as feature authority | OIE-001 owns live quotes; features = research hist |

---

## 4. File touch list (B1–B3 core)

| File | Role |
|------|------|
| `research/feature_registry.py` | **NEW** registry load/validate |
| `research/feature_store.py` | Expand backfill merge APIs |
| `research/build_feature_store.py` | **NEW** CLI |
| `research/research_service.py` | Add `feature_panel` |
| `research/analytics/*.py` | **NEW** RAE-1…4 |
| `research/build_research_analytics.py` | **NEW** CLI |
| `research/research_query_engine.py` | **NEW** |
| `config/feature_store.json` | **NEW** date range, periods, paths |
| `tests/test_feature_store_backfill.py` | **NEW** |
| `tests/test_research_analytics.py` | **NEW** |
| `tests/test_research_query_engine.py` | **NEW** |

B4/B5 additionally touch `options_store` / `market_warehouse` / feature join.

---

## 5. Config sketch (`config/feature_store.json`)

```json
{
  "version": "1.0",
  "universe": "watchlist",
  "lookback_calendar_days": 730,
  "rsi_period": 14,
  "ema_short": 20,
  "ema_long": 50,
  "atr_period": 14,
  "adx_period": 14,
  "technical_source": "local_or_yfinance_research",
  "fundamental_point_in_time": true,
  "reserve_columns": ["pcr", "oi", "vwap", "max_pain", "breadth"]
}
```

---

## 6. Test plan

| ID | Assert |
|----|--------|
| T1 | Registry contains rsi + quality with version/source |
| T2 | Backfill: no future FY fundamentals on date D |
| T3 | `feature_panel` groups technical/fundamental/market |
| T4 | RAE-4: improvement Δ uses historical years only |
| T5 | RQE filter deterministic on fixture store |
| T6 | Research Service has zero imports from `trading_app` |
| T7 (B4) | OI coverage ≥ threshold on overlap |
| T8 (B5) | PCR non-null on recent feature dates |

---

## 7. Suggested session breakdown

| Session | Scope |
|---------|-------|
| **B1a** | Feature Registry + config + `feature_panel` API shape |
| **B1b** | Fundamental PIT join into feature panel (fast win — data already local) |
| **B1c** | Technical backfill for watchlist (heavier; cache OHLC) |
| **B1d** | VIX broadcast + manifest + tests |
| **B2** | RAE-1…4 CLI + outputs |
| **B3** | RQE + wire `ResearchService.search` |
| **B4–B5** | OI normalize → PCR derive → feature join |
| **B6** | FI-3 UI plan + build |

---

## 8. Success metrics

| Metric | Target |
|--------|--------|
| Feature panel coverage | ≥80 symbols with tech+fund on latest date |
| PIT safety | Zero look-ahead failures in tests |
| `feature_panel` | Single object for AI / InvestMitra / research CLI |
| RAE rebuild | &lt;60s on 86-symbol factor history |
| RQE | Documented queries return stable sets |
| OI/PCR | Features null-safe until B4/B5; then ≥70% fill on overlap |

---

## 9. Product boundary reminder

| Layer | Role |
|-------|------|
| **Research Platform** | Warehouse, Feature Store, Registry, Analytics, Service, Query |
| **Product** | NexTrade + InvestMitra consume Research Service |
| **Execution** | Isolated; Phase 7P freeze; no Sprint B coupling |

InvestMitra may call `feature_panel` / `search` / `symbol_intelligence` only — never opportunity tickets or risk overrides.

---

## 9b. Data Validation Engine (DVE)

**Scaffold in B1** (`research/data_validation.py`). Full nightly suite after B1c/B2.

Checks: missing values, duplicate (date,symbol), stale as_of, impossible ranges (RSI∉[0,100]), row counts, feature completeness → feeds RAE-7 coverage.

## 9c. After Sprint B → Sprint C (preview)

| Pri | Component |
|-----|-----------|
| 1 | FI-3 Research Center |
| 2 | InvestMitra ↔ Research Service |
| 3 | Research Notebook (RN-1) |
| 4 | Strategy × Factor (RAE-5) |
| 5 | Model Registry (MR-1) |

Platform branding: **SanMitra Research Platform** (shared intelligence for NexTrade + InvestMitra).

---

## 10. Decision

**Approve Sprint B sequence B1→B6** — **APPROVED** with metadata / RAE-7 / DVE refinements.

**First coding session:** **B1a + B1b** (Registry + fundamental PIT + `feature_panel` + DVE scaffold).

---

## 11. Change log

| Date | Change |
|------|--------|
| 2026-08-04 | Sprint B plan: FS backfill + Registry + feature_panel; RAE; RQE; then MDW-3/4; FI-3 last |
| 2026-08-04 | Approved refinements: panel metadata, RAE-7, DVE, ResearchQuery naming, Sprint C preview |
