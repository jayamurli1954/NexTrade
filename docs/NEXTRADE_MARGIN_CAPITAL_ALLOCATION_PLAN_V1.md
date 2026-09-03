# NexTrade — Margin & Capital Allocation Engine  
## Implementation Plan V1 (POST-7P)

**Status:** BACKLOG — do **not** change live/paper trading logic during Phase 7P freeze  
**Date:** 2026-07-29  
**Trigger:** After valid OIE-001 / RC2 market-data observation baseline  
**Authority:** Complements existing Risk Engine; never replaces it  
**Working capital context (operator):** Account equity ≈ ₹10,00,000; proposed max allocated trading capital ≈ ₹5,00,000

---

## 0. Problem statement

Today the paper dashboard treats **utilized margin ≈ open notional (entry × qty)**. That conflates:

| Concept | Meaning |
|---------|---------|
| **Capital** | Cash / equity allocated to trading |
| **Margin / collateral** | Broker-required pledge to open/hold a position |
| **Gross exposure** | Market value / notional of positions |
| **Risk capital** | Potential loss under SL / stress (Risk Engine domain) |

The note’s rule must become an invariant:

> **Margin determines how large a position you *can* open.  
> Risk determines whether you *should* open it.**

Hardcoding `INTRADAY_LEVERAGE = 5` is forbidden in production. 5× may appear as an **internal ceiling** for research/paper defaults only, never as the sole margin authority.

---

## 1. Operator capital policy (starting numbers)

These are **policy inputs** to the Capital Allocation Engine — not broker truth.

| Parameter | Initial value | Notes |
|-----------|---------------|-------|
| `account_equity` | ₹10,00,000 | Paper TOTAL_CAPITAL today |
| `max_allocated_capital` | ₹5,00,000 | 50% of equity reserved for active trading |
| `capital_reserve` | ₹5,00,000 | Unallocated buffer / overnight reserve |
| `nextrade_intraday_leverage_ceiling` | **≤ 5×** | Soft internal cap; final = min(broker, NexTrade, risk, strategy) |
| `nextrade_delivery_leverage_ceiling` | **1×** | No assumed CNC leverage |
| `max_risk_per_trade_pct_of_allocated` | Existing Risk Engine / mandate | Unchanged by this plan |

Illustrative (only if broker also allows ≥5× on that scrip):

```text
Allocated capital     ₹5,00,000
Internal ceiling      5×
Max gross exposure    ₹25,00,000   ← ceiling only
Actual max exposure   MIN(₹25L, broker RMS, risk limits, concentration)
```

---

## 2. Target architecture

```text
Market Data (Angel WS authority for fills)
        │
        ▼
Trade Intent / Trade Plan
        │
        ▼
┌───────────────────────────────┐
│  Capital Allocation Engine    │  ← NEW
│  allocated / available / reserve │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│  Margin Capital Engine        │  ← NEW
│  product × broker × exchange  │
│  margin_required / leverage   │
│  max_permitted_exposure       │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│  Risk Engine (EXISTING)       │  ← UNCHANGED as authority
│  SL risk, portfolio, kill     │
│  evaluates GROSS exposure     │
└───────────────┬───────────────┘
                ▼
Execution Authorization / Paper Fill
```

**Final leverage / size:**

```text
permitted = MIN(
  Broker RMS / margin API,
  Exchange / SEBI constraints,
  NexTrade leverage ceiling (by product),
  Capital allocation headroom,
  Risk Engine approved quantity,
  Strategy / mandate caps
)
```

Fail-closed if broker margin snapshot is stale/unavailable (same philosophy as OIE-001 LTP).

---

## 3. Product-specific margin models

| Product | Margin model (NexTrade) | Risk basis |
|---------|-------------------------|------------|
| **Intraday equity (MIS)** | Broker span/var or RMS %; internal ≤5× ceiling | Gross notional + SL; same-day square-off |
| **Delivery / Swing (CNC)** | Assume **1×** unless broker confirms otherwise | Full notional + **overnight/gap** risk |
| **Futures** | Broker SPAN + exposure margin via API | Contract notional (not margin paid) |
| **Options buying** | ≈ Premium × qty | Max loss ≈ premium |
| **Options selling** | Broker margin + stress; **no generic leverage** | Notional + gap + assignment stress |

Each product gets a dedicated `MarginModel` implementation behind one interface.

---

## 4. Canonical data model (new contracts)

Proposed module: `contracts/margin_capital.py`

```text
account_equity
allocated_capital
available_capital
reserved_capital

margin_required
margin_available
margin_utilisation_pct

gross_exposure
net_exposure
leverage_ratio

max_permitted_exposure
broker_margin_requirement
broker_leverage_implied
nextrade_leverage_limit
final_permitted_leverage

risk_capital_at_stop          # from Risk Engine / SL
expected_loss
maximum_loss_stress

margin_snapshot_id
margin_source                 # ANGEL_RMS | ANGEL_MARGIN_API | INTERNAL_ESTIMATE
margin_freshness_sec
fail_closed                   # bool
```

Every paper/live fill must log a **margin snapshot** (parallel to fill-integrity provenance).

---

## 5. Broker integration (Angel One)

### 5.1 Dynamic sources (priority order)

1. Angel **funds / RMS** APIs (available cash, available margin) — already partially via holdings/funds paths  
2. Angel **order margin / brokerage calculator** (required margin for proposed order) when available  
3. Internal **estimate** only as degraded DISPLAY; **never** sole authority for live; paper may use estimate only if labelled `INTERNAL_ESTIMATE` and fail-closed for certification-grade evidence

### 5.2 Adapter contract

```text
BrokerMarginPort
  get_funds_snapshot() -> FundsMarginSnapshot
  estimate_order_margin(order_intent) -> MarginRequirement
  get_rms_limits() -> RmsLimits
```

Implement in `data_provider/angel_provider.py` / broker adapter layer — not in UI globals.

---

## 6. Interaction with existing Risk Engine

Do **not** rewrite Phase 2B/2C/2D.

Insert a new pre-step **2A-Margin** (or parallel gate before RiskEngine):

```text
Q_intent
  → Capital headroom check
  → MarginCapitalEngine → Q_margin_capped
  → RiskEngine (2B→2C→2D) → Q_final
```

Risk continues to size on **stop-loss / portfolio / kill-switch** using **gross exposure**, not “margin paid”.

Dashboard must show both:

```text
Capital committed (margin)     ₹X
Gross exposure                 ₹Y
Stop-loss risk                 ₹Z
Leverage (Y/X)                 L×
```

---

## 7. Paper trading implications (critical)

Current paper path: `UTILIZED_MARGIN = sum(entry × qty)` → treats exposure as margin.

### Required change (post-freeze)

| Mode | Paper margin simulation |
|------|-------------------------|
| Intraday | `margin ≈ notional / effective_leverage` where effective_leverage = min(broker, ceiling) |
| Delivery | `margin ≈ notional` (1×) |
| F&O | broker estimate or documented model |

Observation logs (Phase 7P) must add:

- `margin_required`
- `gross_exposure`
- `leverage_ratio`
- `margin_source`
- `allocated_capital_at_fill`

Counterfactual / certification-grade paper runs require the **same model** intended for live.

Until this exists, treat current ₹10L “utilized margin” figures as **notional exposure proxies**, not true broker margin.

---

## 8. Workstreams (phased)

### Phase M0 — Spec freeze (docs only) ✅ this document

- Invariants, data model, product matrix, capital policy numbers  
- No code changes to trading path  

### Phase M1 — Contracts & Capital Allocation Engine

**Deliverables**

- `contracts/margin_capital.py`  
- `capital/allocation_engine.py` — allocated / reserve / available from account equity + policy  
- Unit tests for headroom math with ₹10L / ₹5L policy  

**Exit:** Capital fields computable without touching fills  

### Phase M2 — MarginCapitalEngine + product models

**Deliverables**

- `margin/margin_capital_engine.py`  
- Models: `IntradayEquityMarginModel`, `DeliveryEquityMarginModel`, stubs for F&O/options  
- Internal leverage ceilings (≤5× MIS, 1× CNC) as **caps**, not broker substitutes  
- Fail-closed when required snapshot missing  

**Exit:** Given a TradePlan, engine returns `MarginDecision` (required margin, max qty by margin, leverage)  

### Phase M3 — Angel BrokerMarginPort

**Deliverables**

- Wire funds/RMS + order-margin estimate  
- Freshness SLA (e.g. fail if snapshot age > N seconds for live; looser for paper estimate)  
- Rate-limit aware (reuse `angel_rest_limiter`)  

**Exit:** Live/paper can request real available margin; degraded path labelled  

### Phase M4 — Risk Engine intersection

**Deliverables**

- Pre-trade pipeline: MarginDecision → RiskEngine  
- RiskDecision audit fields include margin snapshot hash  
- No increase of Q beyond margin cap  

**Exit:** Integration tests: margin binds when risk would allow larger size  

### Phase M5 — Paper simulator + observation provenance

**Deliverables**

- Replace notional-as-margin in `_recompute_paper_margin_from_positions` with model-based margin  
- Fill integrity / observation JSONL extended with margin fields  
- UI: Capital vs Margin vs Exposure vs SL Risk on Trade Ticket + Dashboard  

**Exit:** Restart paper evidence clock only after M5 + OIE-001 data path certified  

### Phase M6 — F&O / Options models

**Deliverables**

- Futures SPAN/exposure model via broker API  
- Options buy (premium) vs sell (margin + stress)  
- Separate mandate / automation tier gates already exist — bind margin models to tiers  

---

## 9. Invariants (to certify)

1. **C1** Capital ≠ Margin ≠ Exposure ≠ Risk — four fields always persisted on fill  
2. **C2** No hardcoded production leverage as sole authority  
3. **C3** Final size = min(broker, NexTrade ceiling, capital, risk, mandate)  
4. **C4** Stale/missing margin → fail closed (live); paper may degrade only if labelled non-certification  
5. **C5** Delivery never assumes MIS leverage  
6. **C6** Risk Engine evaluates gross exposure / SL loss, not margin paid  
7. **C7** Every fill has `margin_snapshot_id` + hash  
8. **C8** UI must not display exposure as “capital used” without labelling  

---

## 10. Explicit non-goals (this program)

- Do not change strategy signals or ML during M1–M5  
- Do not raise kill-switch / daily loss limits “because leverage exists”  
- Do not use yfinance for margin or fill P&L  
- Do not treat ₹5L × 5 = ₹25L as guaranteed buying power  

---

## 11. Suggested sequencing vs current freeze

```text
NOW (freeze)
  ├── OIE-001 market data integrity (in progress)
  ├── Valid 15-day observation (RC2)
  └── This plan = backlog only

AFTER valid observation
  ├── M1 Capital Allocation
  ├── M2 MarginCapitalEngine (equity MIS/CNC)
  ├── M3 Angel margin port
  ├── M4 Risk intersection
  ├── M5 Paper + observation provenance  → then new evidence baseline if needed
  └── M6 F&O / Options
```

---

## 12. Acceptance demo (M5)

With account equity ₹10,00,000 and allocated ₹5,00,000:

1. Intraday MIS plan: show margin required, gross exposure, leverage, SL risk separately  
2. Same notional as CNC: margin ≈ notional, leverage ≈ 1×, overnight risk flag  
3. Broker margin unavailable → order blocked (fail closed)  
4. Observation log contains margin snapshot for the fill  
5. Risk rejects when SL loss exceeds mandate even if margin headroom exists  

---

## 13. Document control

| Field | Value |
|-------|-------|
| ID | `NEXTRADE_MARGIN_CAPITAL_ALLOCATION_PLAN_V1` |
| Depends on | OIE-001, Risk Engine V1, Broker adapter contracts |
| Related | GS Quant borrow P3 (portfolio), Awesome Systematic Trading 7D |
| Next action when unblocked | Implement **M1** contracts + Capital Allocation Engine only |
