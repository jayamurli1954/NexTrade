# NexTrade — Deferred Implementation Memory V1

**Purpose:** Single recall list of work we deliberately deferred.  
**Created:** 2026-07-29  
**Trigger to reopen:** Valid Phase 7P / OIE-001 observation complete (or explicit user unfreeze)  
**Do not implement while freeze forbids strategy/risk/execution changes** (except documented OIE-001 exceptions).

---

## How to use this file

When the user asks “what did we defer?” or “is X ready to implement?”, check this list first, then the linked plan docs.

| Status meaning | Meaning |
|----------------|---------|
| **BLOCKED** | Waiting on observation / freeze / external dependency |
| **READY TO PLAN** | Observation done; still needs design approval before code |
| **READY TO BUILD** | Explicitly approved for implementation |

---

## A. Awesome Systematic Trading / Quant Lab

**Source:** [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading)  
**Plans:** `docs/NEXTRADE_AWESOME_SYSTEMATIC_TRADING_BORROW_PLAN_V1.md`, `docs/NEXTRADE_QUANT_RESEARCH_STACK_EVALUATION_V1.md`

| ID | Item | Status | Ready when | Notes |
|----|------|--------|------------|-------|
| AST-7A | VectorBT adapter behind `BacktestEngine` | BLOCKED | Post 15-day observation + licence review (Apache + Commons Clause) | Research only; never authority for live qty/risk |
| AST-7B | Full walk-forward / Monte Carlo / TCA robustness pack | BLOCKED | Post observation | Scaffold exists in `research/robustness.py` — deepen later |
| AST-7C | Signed Strategy Package → live registry promotion | BLOCKED | Post observation + certification gate signed-off | No auto-promotion to paper/live today |
| AST-7D | Portfolio Intelligence (PySystemTrade concepts) | BLOCKED | Phase 7D | Study → adapt |
| AST-7E | Event-driven research (NautilusTrader / LEAN patterns) | BLOCKED | Phase 7E | Study only; do not replace execution |
| AST-7F | AI Alpha Lab / pwb-alphaevolve sandbox | BLOCKED | Explicit sandbox approval | Experiment only |
| AST-PWB | PWB Toolbox selective content | BLOCKED | Post-freeze research | ADOPT selectively |
| AST-HFT | HftBacktest | OPTIONAL | Microstructure need only | Not default path |
| AST-LEGACY | Map draft entry/exit rules into BacktestEngineV2 signals | BLOCKED | Post observation | Legacy adapter is scaffold only |

**Already done (do not re-defer):** research contracts, backtest protocol, certification engine/store, legacy adapter scaffold, basic robustness helpers, unit tests.

---

## B. GS Quant borrow (post-P1)

**Plan:** `docs/NEXTRADE_GS_QUANT_BORROW_PLAN_V1.md`

| ID | Item | Status | Ready when |
|----|------|--------|------------|
| GS-P2 | Research → Production promotion lifecycle | BLOCKED | After valid 15-day observation |
| GS-P3 | Portfolio analytics beyond trade-level risk | BLOCKED | Phase 8+ |
| GS-P4 | Scenario / stress engine | BLOCKED | Phase 8+ |
| GS-P5 | Backtest realism (TCA / slippage) | BLOCKED | After observation |

**Already done:** GS-P1 Canonical Market Data Service (OIE-001).

---

## C. Margin & capital allocation

**Plan:** `docs/NEXTRADE_MARGIN_CAPITAL_ALLOCATION_PLAN_V1.md`

| ID | Item | Status | Ready when |
|----|------|--------|------------|
| M1 | Contracts + Capital Allocation Engine | BLOCKED | Post-freeze / approved unblock |
| M2 | MarginCapitalEngine (equity MIS/CNC) | BLOCKED | After M1 |
| M3 | Angel BrokerMarginPort (dynamic margin) | BLOCKED | After M2 |
| M4 | Risk Engine intersection (Risk remains authority) | BLOCKED | After M3 |
| M5 | Paper simulator + observation provenance | BLOCKED | After M4; may reset evidence clock |
| M6 | F&O / Options margin models | BLOCKED | After M5 |

**Note:** Paper “utilized margin” today ≈ notional, not true broker margin.

---

## D. Always-on / cloud runtime

| ID | Item | Status | Ready when | Notes |
|----|------|--------|------------|-------|
| OPS-MINIPC | Dedicated always-on mini PC for NexTrade | READY TO PLAN | User hardware purchase | Preferred Angel path (residential IP) |
| OPS-ORACLE | Oracle Always Free as Angel host | REJECTED (current) | Only if `apiconnect.angelone.in` reachable without unsafe free proxies | 2026-07-29: API timeout from OCI Mumbai; docs site OK |
| OPS-PROXY | Route Angel via residential proxy from cloud | DEFERRED / DISCOURAGED | Explicit security review | Prefer mini PC / Indian VPS that can reach API natively |
| OPS-IN-VPS | Retest Angel on Indian VPS (non–Always Free) | READY TO PLAN | User chooses vendor | Prove `curl` to `apiconnect` before migrating app |

---

## E. Fundamental Intelligence Layer

**Plan:** `docs/NEXTRADE_FUNDAMENTAL_INTELLIGENCE_LAYER_PLAN_V1.md` (V1.1)  
**Prerequisite:** Local Screener fundamentals store — DONE (`research/data/fundamentals/`)  
**Platform role:** Core engine alongside Market Data / Technical / AI / Risk-Portfolio / Backtest

| ID | Item | Status | Ready when | Notes |
|----|------|--------|------------|-------|
| FI-1 | Factor engine + current/historical stores + Consistency | DONE | Plan V1.1 approved | 83/86 scored; ICICIGI/IRFC/SBILIFE lack annual statements |
| FI-2 | Analyzer/Opportunity display of thesis + factors | DONE | FI-1 done; plan approved + refinements | Display-only via FundamentalService; gates unchanged — `docs/NEXTRADE_FI2_OPPORTUNITY_FACTOR_DISPLAY_PLAN_V1.md` |
| FI-3 | Fundamental Research Center (sortable Q/G/V/H/C table) | READY TO PLAN (deprioritized) | After RQE-1 (+ ideally RAE-1/2/4) | UI after analytics/query — see Platform Research Roadmap |
| FI-4 | Strategy + Portfolio + AI consumption | BLOCKED | Explicit Phase 7P unfreeze | Ranking / portfolio averages |
| FI-5a | Capital Allocation score | READY TO PLAN | After FI-1 | Dividend / debt / OCF-capex |
| FI-5b | Earnings Surprise score | BLOCKED | Estimate feed available | Needs expected EPS |
| FI-5 | Sector profiles, PEG/EV, Overall AI Rating, backtest as-of | READY TO PLAN | After FI-4 or parallel research | Enrichment |

**Already done:** Local fundamentals download, loader, analyzer local-first, opportunity `why_this_trade` highlights.

**V1.1 refinements (2026-08-04):** Consistency factor; current + historical factor archive; Portfolio/Research/AI consumers; Capital Allocation & Earnings Surprise deferred; look-ahead-safe historical Value.

---

## F. Platform Research Roadmap (post–FI-2)

**Plan:** `docs/NEXTRADE_PLATFORM_RESEARCH_ROADMAP_V1.md`  
**Steering:** Pause isolated features; complete leverage layers before FI-3 UI.

| ID | Item | Status | Ready when | Notes |
|----|------|--------|------------|-------|
| MDW-1 | Options store hardening + ARASS lookup | DONE (Sprint A) | Roadmap approved | Soft lookup 84% hit vs 0% exact on 200-day sample; entry uses store |
| MDW-7 | Warehouse facade API | DONE (skeleton) | With MDW-1 | `research/market_warehouse.py` |
| FS-0 | Feature Store scaffold | DONE | Roadmap refinement | `research/feature_store.py` |
| RS-0 | Research Service scaffold | DONE | After FS-0 stub | `research/research_service.py` — search() API |
| RAE-1…4 | Factor distributions / history / leaders | DONE | B2; + RAE-7 coverage |
| RQE-1…2 | Research Query Engine | DONE | B3 Bridge; `ResearchQuery` + ResearchService.search |
| DVE-1 | Data validation CLI pack | DONE | `python -m research.run_data_validation` |
| E2E-R1 | Research pipeline integration test | DONE | `tests/test_research_e2e_pipeline.py` |
| FI-3 | Fundamental Research Center UI | DEFERRED (post-gate) | Does not move readiness |
| RN-1 | Research Notebook layer | READY TO PLAN | After FI-3 |
| MR-1 | Model Registry | READY TO PLAN | Post-freeze research |
| IM-V1 | InvestMitra consume Research Service | READY TO PLAN | Phase E — no trading imports |
| IM-1…3 | InvestMitra ↔ Research Service | READY TO PLAN | After VG-1 / Validation Phase |

**Sprint A:** DONE · **Sprint B1/B2/B3:** DONE · **B4–B6:** deferred past Validation Gate unless blocking.

---

## G. Validation Gate (feature → proof)

**Plan:** `docs/NEXTRADE_VALIDATION_GATE_PLAN_V1.md` (**V1.1 APPROVED**)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| VG-BRIDGE | B3 + DVE-1 + E2E-R1 | **DONE** | Query engine + validation pack + E2E |
| VG-1 | Validation Gate pass | **PASSED** | Exit criteria met 2026-08-04; enter Validation Phase |
| VAL-PHASE | Validation Phase (no net-new features) | **ACTIVE / FREEZE** | Evidence CLI live; ARASS cert package PENDING |
| VG-2 | Paper/cert evidence track | BLOCKED | Observation clock; ARASS not LIVE_ELIGIBLE |
| OBS-FORENSIC-56 | Read-only 56-trade forensic (strategy×exit×cohort) | **ACTIVE** | Matrix + score correlation + cost validation + **C2 triple P&L**; continue observation; **no strategy edits** |
| OBS-FORENSIC-REPAIR | Observation-integrity / forensic repair (not strategy tune) | **ACTIVE** | **C2 policy FROZEN** (`docs/NEXTRADE_OBS_FORENSIC_C2_COST_ASSUMPTION_POLICY_V1.md`); next: A IDs → B decision trace |
| OBS-C2 | Triple P&L forensic policy (Gross / charges-only / full friction) | **DONE (policy)** | Slippage = scenario; do not KEEP/RETIRE on V3 alone; engine defaults unchanged |

**Latest evidence run:** `research/data/validation/validation_phase_latest.json`  
**ARASS package:** `research/data/validation/arass_certification_package.json` (status **PENDING**, `live_eligible=false`)

**Feature freeze (locked):** No FI-3 · No OI/PCR · No Margin/Capital · No gate changes · No LIVE promotion · **No strategy edits from paper-log review**. Narrow **OBS-FORENSIC-REPAIR** allowed for observation identity/trace/cost *measurement* only (explicit approval for any logger/code change).

### Operating charter (Validation & Observation)

**Doc:** `docs/NEXTRADE_VALIDATION_OBSERVATION_CHARTER_V1.md`

| Scorecard (2026-08-04) | |
|------------------------|--|
| Research Platform | **94–95%** — production-grade for research |
| Validation & Evidence | **45–50%** — operational; remainder = time/ops evidence |
| Execution | **63–65%** — intentionally deferred |
| Live readiness | **Blocked** (correct) |

**Cadence:** Daily validation + paper + defect fixes · Weekly reports · Monthly readiness review.  
**Bugs:** Classify Critical / High / Medium / Low — no unrelated features while fixing.  
**Versions:** Research Platform v1.0 (candidate), Feature Store v1.0, Fundamental Engine v1.1, RQE v1.0, Validation Pack v1.0.  
**ARASS PENDING** = governance working (framework can reject).

**Unfreeze order (later):** Execution → OI/PCR → InvestMitra → FI-3.

---

## J. Paper trading terminal (T1–T3) — freeze-safe exception

**Approved:** 2026-08-22 (explicit user go-ahead). Paper UI + tariff *preview* only.  
**Does not:** swap Angel, change strategies/risk/exits, cut over `broker_charges.py` ledger defaults, or connect Arrow live.

| ID | Item | Status | Notes |
|----|------|--------|-------|
| TT-1 | Broker-agnostic tariff catalog | **DONE** | `trading_app/tariff_catalog.py` — statutory rows + ARROW / FLAT20 profiles; authority `PREVIEW_ONLY` |
| TT-2 | Paper terminal shell | **DONE** | `/terminal` — watchlist \| daily OHLC \| ticket \| blotter; existing paper fill path |
| TT-3 | Pre-trade V2 charge line | **DONE** | Ticket + `/api/tariff/preview`; V3 0.05% slip is a toggle; ledger on close still Angel flat template |
| TT-4 | Arrow live execution adapter | BLOCKED | After observation + execution unfreeze |
| TT-5 | Mumbai order-gateway for Arrow latency | BLOCKED | After TT-4; desktop remains a client |

---

## K. NIFTY calendar / rollover spread (Chirag-style) — research first

**Plan:** `docs/NEXTRADE_CALENDAR_SPREAD_RESEARCH_PLAN_V1.md`  
**User intent:** Multi-year backtest → then paper. **Freeze:** research sandbox OK; paper/live strategy wiring **BLOCKED** until unfreeze (+ M6 for FO margin).

| ID | Item | Status | Notes |
|----|------|--------|-------|
| CAL-0 | Formalize rules + KPIs | **DONE / AMENDED** (2026-08-25) | Original [70,80] far−near rejected by data; default now far−near [200,300]; alt next−near [70,80] |
| CAL-1 | Expand options store (≥5y, weekly+monthly, zone strikes) | **DONE (data pass)** (2026-08-25) | Full calendar pass finished: `ok=7068` `fail=3741` `skip=3443` / 14248 jobs. Store: **312,787** rows, **2020-01-01→2026-07-28**, **358** strikes, **341** expiries, max_dte **45**, days DTE≥28 **1392**, trade_days **1631**. Optional later: retry FAIL contracts only. Jugaad/NSE (not Angel). |
| CAL-2 | Research calendar engine (ARASS-class) | **DONE (scaffold + evidence amend)** (2026-08-25) | `research/calendar_spread/` V1.1; `--diff-mode` / amended band. Research-only. |
| CAL-3 | Cert package (PENDING, not LIVE) | BLOCKED | After CAL-2 evidence runs |
| CAL-4 | Paper multi-leg FO | BLOCKED | Unfreeze + M6 + multi-leg adapter |
| CAL-5 | Live FO | BLOCKED | After CAL-4 cert |

**Audit note (2026-08-24):** Pre-CAL-1: ~15.6k rows; max DTE 27; 0 days DTE≥28.  
**CAL-1 complete (2026-08-25):** Coverage gate cleared (max_dte 45; 1392 days with DTE≥28; multi-year weekly+monthly depth).  
**CAL-2 evidence (2026-08-25):** Original far−near [70,80] unsupported (med≈245). Amended far−near [200,300]: 122 trades, **−14.8%** total, PF 0.70. next−near [70,80]: 58 trades, **−13.2%**, PF 0.56. Neither meets 2–4%/mo KPI → **do not promote**; further rule redesign or stop.

---

## H. Recall prompts (for future chats)

Say any of:
- “Open deferred implementation memory”
- “Open Validation & Observation charter”
- “Is VectorBT / AST-7A ready?”
- “Resume Awesome Systematic deferred items”
- “Resume margin M1”
- “Resume GS-P2”
- “Resume Fundamental Intelligence / FI-1”
- “Open platform research roadmap”
- “Start MDW-1 / RAE / RQE”
- “Open Validation Gate plan”
- “Build Bridge / B3”
- “Start Validation Phase” / `python -m research.run_validation_phase`
- “Open calendar spread / CAL plan” / Chirag Jain rollover research

Agent should read this file and the linked plan/charter, then confirm freeze/observation status before coding. **Do not start feature work during Validation & Observation unless user explicitly unfreezes.**

---

## I. Change log

| Date | Change |
|------|--------|
| 2026-07-29 | Initial memory: Awesome Systematic deferred + GS P2–P5 + Margin M1–M6 + Oracle/Angel cloud decision |
| 2026-08-04 | Added Fundamental Intelligence Layer FI-1…FI-5; linked plan doc |
| 2026-08-04 | Plan V1.1: Consistency + historical archive; FI-1 built (current/historical stores) |
| 2026-08-04 | FI-2 display plan linked (`NEXTRADE_FI2_OPPORTUNITY_FACTOR_DISPLAY_PLAN_V1.md`) |
| 2026-08-04 | FI-2 implemented (FundamentalService + Opportunity Investment Intelligence; gates unchanged) |
| 2026-08-04 | Platform Research Roadmap V1: MDW → RAE → RQE → FI-3; FI-3 deprioritized |
| 2026-08-04 | Approved refinements: Feature Store + Research Service; Sprint A MDW-1/FS-0/RS-0/MDW-7 shipped |
| 2026-08-04 | Sprint B plan: FS backfill → RAE → RQE → OI/PCR → FI-3 (`NEXTRADE_SPRINT_B_FEATURE_PLATFORM_PLAN_V1.md`) |
| 2026-08-04 | Sprint B approved + refinements; B1a/B1b shipped (registry, PIT panel, feature_panel metadata, DVE-0) |
| 2026-08-04 | B1c DONE: daily RSI/EMA/ATR/ADX + VIX + PIT fund; TATAMOTORS→TMPV.NS alias; ~43k rows / 86 symbols |
| 2026-08-04 | B2 DONE: RAE-1…4 + RAE-7 analytics artifacts under research/data/analytics/ |
| 2026-08-04 | Validation Gate plan V1: bridge B3+DVE-1+E2E then feature freeze / validation phase |
| 2026-08-04 | VG plan V1.1 APPROVED (perf, SHA256, release readiness, gaps, IM-V1, DoD) |
| 2026-08-04 | Bridge DONE + VG-1 PASSED: RQE, DVE-1, E2E-R1; enter Validation Phase |
| 2026-08-04 | Validation Phase started: VAL-A…H runner; first run PARTIAL (VAL-E cert pending) |
| 2026-08-04 | ARASS cert package generated (PENDING, not LIVE); VAL-E PASS; **feature freeze locked** |
| 2026-08-04 | Validation & Observation charter V1 — scores, cadence, bug severity, versioning, unfreeze order |
| 2026-08-13 | OBS-FORENSIC-56: trading-log review — relook selection/exits/costs; **do not modify strategies yet** |
| 2026-08-13 | OBS-FORENSIC-56 root-cause matrix Excel/JSON generated; unfreeze = DO_NOT_UNFREEZE_STRATEGY_LAYER |
| 2026-08-13 | OBS-FORENSIC-56 score×outcome: suitability saturated; **0/56** aligned with day recommendation |
| 2026-08-13 | OBS-FORENSIC-REPAIR opened; Investigation C cost validation: log≡rebuild; **52% of costs = slippage proxy** |
| 2026-08-13 | **C2 Cost-Assumption Policy** frozen — triple P&L (V1/V2/V3); continue observation; no strategy tune |
| 2026-08-22 | TT-1…T3 paper terminal + tariff catalog *preview* (user-approved freeze exception); ledger defaults unchanged |
| 2026-08-24 | CAL calendar/rollover research plan V1 + Section K (data gap: ~2.5y ATM weekly; paper FO BLOCKED) |
| 2026-08-24 | CAL-0 LOCKED (3:1:1 / zone / gap 0.80% / pts 70–80); CAL-1 calendar download mode in `research/download_nifty_options.py` |
| 2026-08-25 | CAL-1 data pass DONE (312,787 rows); CAL-2 → READY TO PLAN |
| 2026-08-25 | CAL-2 scaffold DONE (`research/calendar_spread/` + CLI + unit tests) |
| 2026-08-25 | CAL-0 pts band amended: far−near [200,300]; added next−near mode; V1.1 |
