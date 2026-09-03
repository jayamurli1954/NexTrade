# NexTrade — GS Quant Borrow Plan V1

**Status:** APPROVED ROADMAP (selective concepts only)  
**Date:** 2026-07-28  
**Authority:** Phase 7P freeze + OIE-001 for NOW work; Phase 8+ for analytics expansion  
**Principle:** Borrow *platform discipline*, not Goldman strategies, APIs, or the `gs-quant` package.

---

## 0. What we are NOT borrowing

| Item | Reason |
|------|--------|
| `gs-quant` Python dependency | Requires GS institutional credentials; wrong problem domain |
| Derivatives pricing / instrument models | NexTrade is equities-first systematic trading |
| GS institutional data APIs | Not available / not applicable |
| Proprietary-style factor stacks wholesale | Premature for current mandate |
| Strategy examples as alpha | Stale-or-not is irrelevant; they are not our edge |

---

## 1. Centres of gravity (do not merge)

```text
GS QUANT                         NEXTRADE
─────────                        ────────
Quant research / pricing toolkit Governed decision → execution system
Data + analytics + risk          Quant + ML + evidence + risk authority
                                 + mandate + local LLM interpreter
```

NexTrade keeps risk-as-final-authority, Mandate U5, and LLM-as-interpreter. GS Quant inspirations sit *under* those boundaries, never above them.

---

## 2. Borrow backlog (priority order)

### P1 — Canonical Market Data Service  🔴 NOW (OIE-001)

**GS lesson:** One institutional data model; all consumers share authority.

**NexTrade adoption:**

```text
Providers (Angel WS / Angel REST / Historical)
        │
        ▼
 Canonical Quote + Provenance + Authority State
        │
        ▼
   Data Quality Gate
        │
   ┌────┼──────────────┐
   ▼    ▼              ▼
 EXEC  DISPLAY      RESEARCH
 (WS)  (WS/REST)   (hist/yfinance OK)
```

**Rules (OIE-001):**

- `EXECUTION` / paper fill → `ANGEL_WS_LIVE` only  
- `DISPLAY` → WS preferred, REST reference OK  
- `RESEARCH` → historical / yfinance OK; never used for fills or observation P&L  

**Deliverables:**

- `contracts/market_data.py` — quote, purpose, authority contracts  
- `trading_app/market_data_service.py` — single facade over Angel bridge  
- Wire intelligence / desktop health off hard-coded LTP  

---

### P2 — Research → Production Promotion Lifecycle  🟡 AFTER valid 15-day observation

**GS lesson:** Research tooling is distinct from production trading.

**NexTrade adoption (extend existing promotion / evidence, do not invent parallel tracks):**

```text
RESEARCH → EXPERIMENT → BACKTEST → WALK-FORWARD → OOS
        → PAPER → CONTROLLED PILOT → PRODUCTION
```

Every strategy must carry an explicit promotion stage; skipping stages is a hard gate.

**Out of scope until observation evidence is valid.**

---

### P3 — Portfolio Analytics (beyond trade-level risk)  🟢 PHASE 8+

**GS lesson:** Decompose exposure / concentration / drivers of risk.

**NexTrade adoption (minimal set):**

- Position / sector / concentration exposure  
- Correlation / simple beta vs NIFTY  
- Portfolio volatility & drawdown attribution  

Full institutional factor models are **not** required for Indian single-book equities at this stage.

---

### P4 — Scenario / Stress Engine  🟢 PHASE 8+

**GS lesson:** Price / risk under shocked market states.

**NexTrade scenarios (examples):**

- NIFTY −3% / BANKNIFTY −2% gap  
- India VIX +30%  
- Liquidity −50%  
- Strategy historical edge decay  

Output must feed **risk impact + kill-switch thresholds**, not LLM authority.

---

### P5 — Backtest realism (TCA / slippage)  🟡 AFTER observation

Strengthen existing `backtesting/` with transaction-cost and slippage assumptions. Do not replace with gs-quant backtest modules.

---

## 3. Freeze compliance matrix

| Borrow item | Allowed under OIE-001? |
|-------------|------------------------|
| P1 Market Data Service / authority / provenance | ✅ Yes |
| Hard-coded / yfinance fill removal | ✅ Yes |
| P2–P5 research / portfolio / scenario / TCA | ❌ Freeze — Phase 8+ / post-observation |
| Strategy, ML, risk-limit, execution-rule changes | ❌ Forbidden |

---

## 4. Success criteria for P1

1. No paper fill without `ANGEL_WS_LIVE` + freshness gate  
2. All primary consumers resolve quotes through `MarketDataService` (or Angel bridge behind it)  
3. Quote provenance logged on every observation fill  
4. Intelligence / desktop health paths do not invent index LTP when Angel is unavailable (fail closed / degrade explicitly)

---

## 5. Ownership of truth

| Layer | Source of truth |
|-------|-----------------|
| Real-time execution price | Angel SmartWebSocketV2 via Market Data Service |
| Display / reference | Angel WS → Angel REST |
| Research / history | Historical providers / yfinance (non-execution) |
| Risk / mandate / execution auth | Existing NexTrade engines (unchanged by this plan) |
