# NexTrade — FI-2 Implementation Plan  
## Opportunity + Analyzer Factor Display (Gates Unchanged)

**Status:** APPROVED + IMPLEMENTED (display-only; Phase 7P freeze-safe)  
**Date:** 2026-08-04  
**Depends on:** FI-1 DONE (`research/data/fundamentals/current/factor_scores.json`)  
**Parent:** `docs/NEXTRADE_FUNDAMENTAL_INTELLIGENCE_LAYER_PLAN_V1.md` (V1.1)  
**Freeze rule:** Must **not** change confidence, ranking, BUY/SELL gates, or risk limits.

### Approved refinements (2026-08-04)

| Enhancement | Implementation |
|-------------|----------------|
| **Fundamental Service** | `research/fundamental_service.py` — single API/cache for Opportunity / Analyzer / future consumers |
| **Investment Intelligence** panel | Thesis + badges + trends + peers + as-of FY (replaces bare “Investment Thesis” label) |
| **AI Summary** | Rule-based `build_ai_summary()` — no LLM |
| **Score trends** | ▲/▼ vs prior FY from `historical/` |
| **Factor badges** | Excellent / Good / Fair / Weak / Poor |
| **Opportunity strength** | Technical / Fundamental / Overall — **display only** |
| **Meta** | `factor_version`, `generated_at`, `fiscal_year`, `as_of_label` |
| **FI-3 naming** | Prefer **Fundamental Research Center** |

---

## 0. Goal

Wire precomputed Fundamental Intelligence scores into the live scan path so Opportunities explain **why** with factor language — without becoming a scoring authority.

```text
factor_scores.json (FI-1)
        ↓
FundamentalsAnalyzer (prefer factors over legacy blend)
        ↓
EnhancedAnalyzer signal fields (attach only)
        ↓
OpportunityEngine (thesis + factor strip; no gate change)
        ↓
/api/opportunities + dashboard card UI
```

**Success look:** Expanding an opportunity shows Investment Thesis + Q/G/V/H/C strip; signal confidence % is identical to pre-FI-2 for the same technical inputs.

---

## 1. Current state (gap)

| Layer | Today | Gap |
|-------|-------|-----|
| Factor store | Built (83/86) | Not read by analyzer |
| `FundamentalsAnalyzer` | Local raw metrics → legacy 0–100 + highlights | Ignores FI-1 factor store |
| `EnhancedAnalyzer` signal | `fundamentals_score`, `fundamentals_highlights` | No `factor_scores` / `investment_thesis` / relatives |
| `OpportunityEngine` | Appends raw highlights into `why_this_trade` | Still interprets-ish via highlights; no structured factors |
| `/api/opportunities` | Serializes `why_this_trade` only | No factor payload |
| Dashboard detail row | “WHY THIS TRADE?” bullet list | No thesis section / factor strip |

---

## 2. Non-goals (explicit)

| Do not | Why |
|--------|-----|
| Change `min_confidence`, MB gate, BUY weight math | Freeze / FI-4 |
| Recompute factors during scan | Latency + determinism; FI-1 is batch |
| Call Screener / Yahoo for factors | Local store only |
| Build Research Dashboard table | That is **FI-3** |
| Portfolio-average factors | That is **FI-4** |
| LLM-written thesis | Rule-based thesis already in store |

---

## 3. Target UX / API

### 3.1 Opportunity card (detail expand)

```text
WHY THIS TRADE? (Technical)
  • Near Golden Ratio (61.8%)
  • RSI oversold (32.1)
  • Volume 1.8x vs average

INVESTMENT THESIS (Fundamental Intelligence)
  • Below sector P/E (−26% vs peers)
  • Strong quality (100/100)
  • Strong consistency (94/100)

FACTORS   Q 100 · G 41 · V 85 · H 98 · C 94 · Overall 84
          as of FY2026 · store local · peers ok
```

### 3.2 API shape (`/api/opportunities` item)

```json
{
  "symbol": "TCS",
  "signal_strength_pct": 78,
  "why_this_trade": ["Near Golden Ratio...", "RSI oversold..."],
  "investment_thesis": [
    "Below sector P/E (−26% vs peers)",
    "Strong quality (100/100)"
  ],
  "factor_scores": {
    "quality": 100,
    "growth": 41,
    "value": 84.8,
    "financial_health": 97.7,
    "consistency": 94.2,
    "overall_fundamental": 83.7
  },
  "valuation_relatives": {
    "pe": 16.7,
    "sector_pe_median": 22.51,
    "pe_vs_sector_pct": -25.8
  },
  "fundamentals_meta": {
    "source": "factor_store",
    "fiscal_year": 2026,
    "as_of": "2026-08-04T..."
  }
}
```

**Separation rule:** `why_this_trade` = technical (+ volume/RSI extras).  
`investment_thesis` = fundamental bullets from FI-1.  
Do not merge into one list longer than needed; UI shows two columns/sections.

---

## 4. Module design

### 4.1 `FundamentalsAnalyzer` adapter

**Change:** `analyze_fundamentals_bundle(symbol)` prefers `FactorScoreStore.load_current_symbol(symbol)`.

```text
If factor record exists and overall_fundamental is not null:
  score     = round(overall_fundamental)
  highlights / thesis = record.thesis
  factor_scores = record.scores
  relatives = record.relatives
  source = "factor_store"
Else:
  existing local raw → legacy score + highlights  (fallback)
  Else yfinance fallback
```

**Cache:** Keep day-keyed cache; key may include `"factor_store"` suffix.

**Legacy `_calculate_score`:** Keep for fallback only; do not dual-score when factors exist.

### 4.2 `EnhancedAnalyzer`

Attach on every signal (even HOLD path if produced):

| Field | Type |
|-------|------|
| `fundamentals_score` | float — Overall (or 0) |
| `fundamentals_highlights` | list — **deprecated for opp cards**; keep for compat |
| `investment_thesis` | list[str] |
| `factor_scores` | dict \| null |
| `valuation_relatives` | dict \| null |
| `fundamentals_source` | `factor_store` \| `local` \| `yfinance` \| null |

**Freeze check:** `_generate_golden_ratio_signal` buy/sell **points** may still use `fundamentals_score` as today.  
FI-2 does **not** change those weight formulas. Only the *source* of the number may become Overall Fundamental (expected to be similar magnitude 0–100).  

**Optional safety toggle** in `config/analyzer_config.json`:

```json
"fundamentals_score_source": "factor_overall"   // or "legacy_blend"
```

Default for FI-2 under freeze: prefer **`legacy_blend` for scoring points** and **`factor_store` for display fields only** — cleanest freeze proof.

**Recommended FI-2 default (strict freeze):**

| Concern | Source |
|---------|--------|
| BUY/SELL fundamental points | Keep current legacy `analyze_fundamentals` score path OR freeze-snapshot of prior behavior |
| Display thesis / factors | Always from factor store when present |

Simplest clean split:

```python
display_bundle = load_factor_store(symbol)   # thesis + factors
score_for_gates = legacy_or_existing_score() # unchanged math inputs
```

If legacy score is already “local metrics blend”, leave it. Attach factors in parallel.  
**Do not** replace gate score with Overall until FI-4.

### 4.3 `OpportunityEngine`

Extend `TradeOpportunity`:

```python
investment_thesis: List[str] = field(default_factory=list)
factor_scores: Optional[Dict[str, Any]] = None
valuation_relatives: Optional[Dict[str, Any]] = None
fundamentals_meta: Optional[Dict[str, Any]] = None
```

Logic:

1. Build `why` from technical `reason` + volume + RSI **only** (stop appending raw `fundamentals_highlights` into why — move to thesis).  
2. Set `investment_thesis` from `sig["investment_thesis"]` or factor store fallback.  
3. Pass through `factor_scores` / relatives / meta.  
4. **Unchanged:** `min_confidence`, MB gate, sorting by confidence, top_n.

### 4.4 `web_dashboard.py`

1. Serialize new fields in `/api/opportunities`.  
2. Detail row: three blocks — Why (tech) | Thesis (fund) | Invalidation.  
3. Compact factor strip under thesis.  
4. Missing factors → hide thesis section (no empty noise).

### 4.5 Optional thin helper

`research/factor_score_store.py` already has `load_current_symbol`.  
Analyzer imports store only — no recompute.

---

## 5. Freeze safety protocol

| Check | Method |
|-------|--------|
| Confidence unchanged | Unit test: mock signal with fixed technicals → same confidence with/without factor attach |
| Ranking unchanged | Snapshot top-N symbols from fixture signals before/after |
| No network in scan path | Factor load is file JSON only |
| Config flag | `enable_factor_display: true` (default on); `use_factor_overall_for_gates: false` (default off until FI-4) |

Document in OIE/freeze notes: FI-2 is **display provenance**, not strategy change.

---

## 6. Implementation steps (ordered)

### Step A — Analyzer adapter (display fields)

1. Add `_load_factor_display(symbol) -> dict` in `FundamentalsAnalyzer` or small `research/factor_display.py`.  
2. Extend `analyze_fundamentals_bundle` return:

```python
{
  "score": <legacy gate score>,
  "highlights": [...],          # legacy
  "investment_thesis": [...],   # from factor store
  "factor_scores": {...}|None,
  "valuation_relatives": {...}|None,
  "fundamentals_meta": {...}|None,
  "source": "...",
  "display_source": "factor_store"|None,
}
```

3. Unit tests with temp factor JSON fixture.

### Step B — EnhancedAnalyzer wire-through

1. Pass thesis / factors / relatives onto `signal_data`.  
2. Keep `fundamentals_score` from legacy path for gate points.  
3. Test: signal dict contains keys when store hit.

### Step C — OpportunityEngine

1. Extend dataclass + `signals_to_opportunities`.  
2. Split why vs thesis.  
3. Cap thesis at 6 (already in store).  
4. Tests: opportunity JSON shape; confidence/sort unchanged.

### Step D — API + UI

1. `/api/opportunities` fields.  
2. Dashboard detail: thesis + factor strip.  
3. Manual smoke: rescan → expand TCS/INFY card.

### Step E — Docs / memory

1. Mark FI-2 DONE in deferred memory.  
2. Short note in parent FI plan §7 FI-2 exit criteria.

---

## 7. File touch list

| File | Change |
|------|--------|
| `analyzer/fundamentals_analyzer.py` | Load factor display; keep legacy score for gates |
| `analyzer/enhanced_analyzer.py` | Attach thesis/factors on signal |
| `trading_app/opportunity_engine.py` | Dataclass + split why/thesis |
| `web_dashboard.py` | API serialize + UI sections |
| `config/analyzer_config.json` | `enable_factor_display`, `use_factor_overall_for_gates: false` |
| `tests/test_fi2_factor_display.py` | **NEW** — freeze + shape tests |
| `docs/NEXTRADE_DEFERRED_IMPLEMENTATION_MEMORY_V1.md` | FI-2 → DONE |
| `docs/NEXTRADE_FUNDAMENTAL_INTELLIGENCE_LAYER_PLAN_V1.md` | FI-2 checklist filled |

**Not touched:** risk engine, paper day limits, scanner confidence thresholds, factor math (FI-1).

---

## 8. Tests

| ID | Assert |
|----|--------|
| T1 | Factor store hit → thesis + scores on bundle |
| T2 | Store miss → thesis empty; legacy highlights still work |
| T3 | Opportunity `why_this_trade` has no PE/ROCE raw lines when thesis present |
| T4 | Same mock technicals → identical `confidence` before/after FI-2 |
| T5 | API payload includes `factor_scores` keys for fixture symbol |
| T6 | ICICIGI-like missing annual → no crash; thesis omitted |

---

## 9. Exit criteria

- [ ] Opportunities for factor-covered symbols show Investment Thesis + Q/G/V/H/C  
- [ ] `use_factor_overall_for_gates` remains `false`  
- [ ] Confidence / top-N order unchanged on fixture suite  
- [ ] No Screener/Yahoo calls added to scan hot path for factors  
- [ ] Deferred memory FI-2 = DONE; FI-3 remains READY TO PLAN  

**Estimate:** 1 focused session  

---

## 10. Out of scope handoff → FI-3

After FI-2, next plan should cover:

- Dedicated **Fundamental Research** page (sortable 86-row table)  
- CSV already at `current/factor_scores_table.csv` as data source  
- “Is quality improving?” sparkline from `historical/YYYY.json`

Do **not** expand FI-2 into a full research dashboard.

---

## 11. Recommended decision before coding

Confirm freeze posture:

1. **Strict (recommended):** Factors display-only; gate score stays legacy blend.  
2. **Soft:** Gate score = Overall Fundamental, but weights unchanged (still a behavior change → treat as needing your explicit OK).

Default plan assumes **(1)**.

---

## 12. Change log

| Date | Change |
|------|--------|
| 2026-08-04 | FI-2 implementation plan created after FI-1 completion |
