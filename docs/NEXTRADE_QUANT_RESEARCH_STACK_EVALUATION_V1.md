# NexTrade Quant Research Stack — Technical Evaluation V1

**Date:** 2026-07-28  
**Status:** Architecture Recommendation / Pre-Implementation  
**Sources:** awesome-systematic-trading + PWB ecosystem due diligence  
**Decision framework:** ADOPT / ADAPT / STUDY / EXPERIMENT / REJECT

---

## 1. Executive decision

External projects are **research engines and references**.  
They are **not** authority for order quantity, risk limits, kill switches, execution authorisation, or live activation.

```text
InvestMitra → Research Hypothesis
     ↓
NexTrade Quant Lab (VectorBT / PWB / event sim — later)
     ↓
Strategy Validation → Certification → Signed Package
     ↓
Strategy Registry → Portfolio proposal → Risk Engine → Execution
```

---

## 2. Decision matrix (final shortlist)

| Project | Role | NexTrade | InvestMitra | License note | Decision |
|---------|------|----------|-------------|--------------|----------|
| **VectorBT** | Vectorised research | Very High | High | Apache + Commons Clause — legal gate | **ADAPT** (adapter later) |
| **PWB Toolbox** | Academic strategies/data | Very High | Very High | MIT | **ADOPT SELECTIVELY** (later) |
| **NautilusTrader** | Event-driven sim | Very High | Low | LGPL-3.0 — legal gate | **STUDY → ADAPT** |
| **QuantConnect LEAN** | Full algo engine reference | High | Medium | Apache-2.0 | **STUDY / ADAPT CONCEPTS** |
| **PySystemTrade** | Portfolio / vol targeting | High | High | Verify licence | **STUDY / ADAPT CONCEPTS** |
| **HftBacktest** | Microstructure | Specialised | Low | Verify licence | **OPTIONAL** |
| **pwb-alphaevolve** | AI strategy evolution | Potentially High | High | Verify terms | **EXPERIMENT ONLY** |
| Backtrader / crypto bots | Legacy / niche | Low–Med | Low | Mixed | **REJECT as core** |

---

## 3. Strategy Certification Invariant (new)

> No strategy may transition from `RESEARCH` / `CANDIDATE` to `LIVE_ELIGIBLE` without a valid, signed, versioned Strategy Certification Package whose code, data, config and validation evidence are cryptographically bound to the registered strategy version.

Lifecycle:

```text
RESEARCH → CANDIDATE → BACKTESTED → VALIDATED → CERTIFIED
        → SHADOW → PAPER → LIVE_ELIGIBLE
```

---

## 4. InvestMitra boundary

InvestMitra may emit: hypothesis, evidence, academic refs, market analysis.  
InvestMitra must **never** emit: Execute BUY/SELL, quantity, risk override.

---

## 5. Phase mapping

| Sub-phase | Scope |
|-----------|--------|
| **7A (scaffold now)** | Contracts, BacktestEngine protocol, Certification Engine stub |
| **7A+ (post-observation)** | VectorBT adapter, PWB selective import |
| **7B** | Walk-forward, Monte Carlo, TCA, slippage |
| **7C** | Signed packages + registry binding |
| **7D** | Portfolio Intelligence |
| **7E** | Nautilus / LEAN study adapters |
| **7F** | AI Alpha Lab (sandbox) |

---

## 6. Anti-pattern: Strategy Zoo

Do **not** import 100 strategies because they are listed.  
Every candidate must pass: economic rationale → data quality → IS/OOS → walk-forward → costs → parameter stability → regime → Monte Carlo → paper/shadow → certification.
