# NexTrade — Validation Gate & Platform Readiness Plan V1.1  
## From “build features” → “prove correctness”

**Status:** APPROVED · **VG-1 PASSED** · **Validation & Observation ACTIVE** (feature freeze locked)  
**Date:** 2026-08-04  
**Operating charter:** `docs/NEXTRADE_VALIDATION_OBSERVATION_CHARTER_V1.md`  
**Approved refinements:** Performance targets · SHA256 repeatability · Release readiness report · Categorized known-gaps · IM-V1 · Engine Definition of Done  
**Trigger:** Research infrastructure substantially complete (B1 Feature Store + B2 Analytics DONE)  
**Related:** Sprint B plan, Platform Research Roadmap, Phase 7P / OIE-001, deferred memory  

---

## 0. Verdict

> Stop optimizing for feature count. Optimize for **what we can prove is correct.**  
> **Engineering discipline is more valuable than engineering speed.**

Official phase: **Validation & Observation** — not another build sprint.

| Area | Score | Sign-off |
|------|------:|----------|
| Research Platform | **94–95%** | Production-grade for research |
| Validation & Evidence | **45–50%** | Operational; gap = time + ops evidence |
| Execution Platform | **63–65%** | Intentionally deferred |
| Live Trading Readiness | Blocked | Correctly blocked |

ARASS remaining **PENDING** proves the certification framework can reject — stronger platform validation than a lucky PASS.

### Mindset by phase

| Phase | Measure progress by |
|-------|---------------------|
| Before VG-1 | Platform capabilities delivered |
| Validation Phase | Evidence produced |
| After VG-1 | Production readiness (not feature count) |

### Bridge / VG-1 status (2026-08-04)

| Item | Status |
|------|--------|
| B3 Research Query Engine | DONE |
| DVE-1 Validation pack | DONE (`python -m research.run_data_validation` → PASS) |
| E2E-R1 | DONE |
| Release readiness | PASS (`research/data/validation/`) |
| **VG-1** | **PASSED** |
| **Validation Phase** | **IN PROGRESS** — `python -m research.run_validation_phase` |

### First Validation Phase evidence run

| Track | Status |
|-------|--------|
| VAL-A DVE + coverage | PASS |
| VAL-B Dual analytics SHA256 | PASS |
| VAL-C ARASS dual-run | PASS |
| VAL-D Paper fill hygiene | PASS (28 fills, ~6 days — observation continues) |
| VAL-E Cert checklist | PASS (ARASS package PENDING, not LIVE) |
| VAL-F Known gaps | PASS |
| VAL-G Release readiness | PASS |
| VAL-H Perf hard gates | PASS (`feature_panel` ~12ms warm) |

**Feature freeze locked (2026-08-04):** No FI-3 / OI/PCR / Margin / Capital / gate changes / LIVE promotion.

ARASS package: `research/data/validation/arass_certification_package.json` · CLI: `python -m research.certify_arass`

---

## 1. Honest scorecard (updated for shipped work)

| Platform | Note’s “today” | **Actual now** | Next target before Validation Gate |
|----------|----------------|----------------|--------------------------------------|
| **Research Platform** | 82% | **~91%** (B1+B2 shipped) | **~94–95%** after B3 Query (+ light DVE) |
| **Execution Platform** | 63% | **~63%** (unchanged; Phase 7P freeze) | Hold until post-validation / unfreeze |
| **Validation & Evidence** | 25% | **~28%** (DVE-0 scaffold + unit tests + RAE-7) | **~50%** after Validation Phase |

### Research — still open before claiming ~95%

| ID | Item | Needed for gate? |
|----|------|------------------|
| **B3** | Research Query Engine (`ResearchQuery`) | **YES** |
| **DVE-1** | Nightly/CLI validation pack (+ perf + hash hooks) | **YES** |
| **E2E-R1** | One integration test | **YES** |
| B4/B5 OI/PCR | Market depth | **NO for gate** |
| B6 FI-3 UI | Research Center screen | **NO for gate** |

### Execution — do not expand during VG-1

After Validation Phase (explicit unfreeze), order:

1. Capital Allocation → 2. Margin → 3. Portfolio Risk → 4. Order Lifecycle → 5. Monitoring → 6. Audit

---

## 2. Definition: Validation Gate (VG-1)

We **enter Validation Mode** when all VG-1 exit criteria pass:

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | Feature Store rebuild is deterministic & documented | `feature_build.json` + CLI idempotent |
| 2 | Analytics rebuild deterministic | `analytics_build.json` + CLI |
| 3 | `ResearchQuery` / RQE-1 filters fundamentals (+ optional RSI/VIX) | Unit tests + sample queries |
| 4 | `feature_panel` returns metadata with `lookahead_safe` | Existing + regression |
| 5 | DVE-1 produces pass/fail report (duplicates, coverage floors, RSI range) | `validation_latest.json` |
| 6 | E2E-R1 integration test green | `tests/test_research_e2e_pipeline.py` |
| 7 | Written freeze: no FI-3 / no FI-4 / no Margin M1 until VG-2 | This doc + deferred memory |
| 8 | **Performance smoke** (warn/fail vs targets) | DVE perf section |
| 9 | **Repeatability hash** recorded for key artifacts | SHA256 in validation report |

**Explicitly NOT required for VG-1:** FI-3 UI, OI/PCR, Capital/Margin engines, live trading, 3–6 months paper (VG-2 / evidence clock).

### Performance targets (VG-1 smoke; harden in Validation Phase)

| Metric | Target |
|--------|--------|
| `feature_panel()` | < 100 ms (warm / single symbol) |
| `ResearchService.search()` | < 500 ms (factor filter, limit 50) |
| Feature Store rebuild | < 5 min (full panel) |
| Analytics rebuild | < 5 min |

### Repeatability metric

```text
Run 1 → SHA256(artifact) → Run 2 → SHA256(artifact) → Equal
```

Primary artifacts: feature panel CSV (or sorted content hash), factor `current/factor_scores.json` (stable fields), analytics build outputs excluding volatile timestamps where needed.

---

## 3. Bridge sprint (finish research → then stop)

### Bridge-1 — B3 Research Query Engine

- `research/research_query_engine.py` with **`ResearchQuery`** (alias `FactorQuery`)
- Filters: Q/G/V/H/C/Overall + optional RSI/VIX from Feature Store as-of
- Historical / as-of fiscal where data exists; improvement queries
- `ResearchService.search` delegates to RQE
- Tests: deterministic `Quality>80 AND Growth>70 AND Value>60`

### Bridge-2 — DVE-1 Validation pack

- Feature panel: dup keys, RSI bounds, coverage floors
- Factor store: symbol count, missing overall
- PIT spot-check
- Perf smoke + artifact SHA256
- Release readiness summary
- CLI: `python -m research.run_data_validation` → nonzero on errors

### Bridge-3 — E2E-R1

```text
Factor/Feature inputs
  → ResearchService.feature_panel / search
  → Opportunity display attach (fields only)
  → assert confidence/gates unchanged (freeze)
```

**After Bridge-1…3 → declare VG-1 PASSED → Validation Phase.**

---

## 4. Validation Phase (feature freeze)

**Duration:** ~2–4 weeks calendar (overlap with paper observation)  
**Rule:** No net-new product features. Fix bugs / proof only.

| Track | Work | Target |
|-------|------|--------|
| **VAL-A** | Nightly or on-demand DVE + coverage (RAE-7) | Automated report |
| **VAL-B** | Rebuild CLIs twice → SHA256 equality | Determinism |
| **VAL-C** | ARASS / research backtest: fixed seed, two-run equality | Repeatability |
| **VAL-D** | Paper trading evidence hygiene (OIE-001) | Observation clock |
| **VAL-E** | Strategy certification checklist | Version / data / feature version / status |
| **VAL-F** | Categorized known-gaps register | Honesty |
| **VAL-G** | Release readiness report each validation run | Executive dashboard |
| **VAL-H** | Enforce performance targets as hard gates | Harden smoke → fail |

### Release readiness report (each Validation Phase run)

```text
Research Platform     PASS|FAIL
Feature Store         PASS|FAIL
Validation            PASS|FAIL
Analytics             PASS|FAIL
Research Service      PASS|FAIL
Known Issues          N
```

Artifact: `research/data/validation/release_readiness_latest.json` (+ optional markdown).

### Known gaps register (categories)

| Category | Examples |
|----------|----------|
| **Data gaps** | Missing OI/PCR; incomplete options history |
| **Feature gaps** | FI-3 UI deferred |
| **Execution gaps** | Margin, Capital Allocation (Phase 7P) |
| **Validation gaps** | Paper-trading evidence still accumulating |

Living file: `research/data/validation/known_gaps.json`

---

## 5. Engine Definition of Done (governance)

Every engine is **complete** only when:

| Check | Required |
|-------|----------|
| Functional tests | ✅ |
| Integration tests | ✅ |
| Performance target | ✅ |
| Documentation | ✅ |
| Versioned API / manifest | ✅ |
| Validation report coverage | ✅ |

Applies to: Market Data Warehouse, Feature Store, Fundamental Intelligence, Research Query Engine, Research Service.

---

## 6. InvestMitra milestone (explicit)

| ID | Goal |
|----|------|
| **IM-V1** | Consume `ResearchQuery` / `feature_panel` / `symbol_intelligence` via Research Service **without importing trading modules** |

Schedule: **Phase E** after Validation Phase (not during Bridge). Same shared architecture — consumer integration, not rewrite.

---

## 7. Roadmap beyond VG-1

| Phase | Focus |
|-------|--------|
| VG-1 | Bridge (B3 + DVE-1 + E2E-R1) |
| Validation | Evidence, determinism, integration, release report |
| Phase D | Execution (Capital → Margin → Risk → Lifecycle → Monitor → Audit) |
| Phase E | InvestMitra IM-V1 |
| Phase F | FI-3 UI, Research Notebook, Model Registry |

---

## 8. What we deliberately defer past the gate

| Item | When to reopen |
|------|----------------|
| FI-3 Research Center UI | Phase F / after VG-1 |
| MDW-3/4 OI/PCR | After Validation Phase or if ARASS blocked |
| Capital / Margin / Portfolio risk | Phase D (explicit unfreeze) |
| FI-4 factor gates in BUY score | Unfreeze + A/B |
| Research Notebook / Model Registry | Phase F |
| IM-V1 InvestMitra consume API | Phase E |

---

## 9. Effort allocation (remaining work)

| Bucket | Share of *remaining* effort | Focus now |
|--------|------------------------------|-----------|
| Research completion | **~20%** | Bridge B3 + DVE-1 + E2E only |
| Validation & Evidence | **~50%** | VG-1 then Validation Phase |
| Execution (later) | **~30%** | After VG-1 evidence; still freeze-gated |

---

## 10. Phased targets

| Platform | Now | After Bridge (VG-1) | After Validation Phase | Later (unfreeze) |
|----------|-----|---------------------|------------------------|------------------|
| Research | ~91% | **~94–95%** | Hold / harden | 96%+ with OI/PCR |
| Execution | ~63% | Hold | Hold | →90% Capital/Margin/Risk/Monitor |
| Validation | ~28% | **~40%** | **~50%** | →70% with paper + cert |

---

## 11. Decision (locked)

1. **This plan is the governing roadmap.**  
2. **Implement Bridge only:** B3 → DVE-1 → E2E-R1.  
3. **Declare VG-1** when criteria pass.  
4. **Enter Validation Phase** (feature freeze).  
5. Reopen Execution / InvestMitra / FI-3 only on the Phase D–F sequence above.

### Success question

From: *“How many more features can we build?”*  
To: *“How much of the platform can we prove is correct?”*

---

## 12. Change log

| Date | Change |
|------|--------|
| 2026-08-04 | Initial Validation Gate plan; recalibrated scores post B1/B2; Bridge = B3+DVE-1+E2E |
| 2026-08-04 | **V1.1 APPROVED:** perf targets, SHA256 repeatability, release readiness, categorized gaps, IM-V1, engine DoD; Bridge implementation authorized |
| 2026-08-04 | Bridge shipped; DVE-1 PASS; **VG-1 PASSED**; Validation Phase next |
| 2026-08-04 | Validation Phase runner shipped; first evidence run PARTIAL (VAL-E) |
| 2026-08-04 | ARASS cert package PENDING; VAL-E PASS; feature freeze locked |
| 2026-08-04 | Validation & Observation charter; scores 94–95% / 45–50% / 63–65%; cadence + bug severity + versioning |
