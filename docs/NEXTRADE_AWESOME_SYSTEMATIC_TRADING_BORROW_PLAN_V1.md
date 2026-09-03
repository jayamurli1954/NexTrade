# NexTrade — Awesome Systematic Trading Borrow Plan V1

**Status:** APPROVED ROADMAP (selective concepts only)  
**Date:** 2026-07-28  
**Source:** [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) + internal due-diligence note  
**Authority:** Phase 7P freeze remains; this work is **research-domain scaffolding only** (no strategy/risk/execution changes under OIE-001)

---

## 0. Core principle

> Treat Awesome Systematic Trading as a **discovery map**, not a framework to plug into live trading.

External engines (VectorBT, Nautilus, LEAN, …) may accelerate **research**.  
They must **never** become authority for quantity, risk, kill-switch, or live deployment.

```text
InvestMitra (hypothesis) → Quant Lab (test) → Certification → Registry
        → Portfolio proposal → Risk Engine (sole authority) → Execution
```

---

## 1. What we borrow from the note (decision)

| Borrow item | Decision | When |
|-------------|----------|------|
| Strategy Research Catalogue taxonomy | **ADAPT** | Scaffold now |
| Research → Strategy → Certification lifecycle | **ADAPT** | Contracts now |
| BacktestEngine abstraction (swap-able adapters) | **ADAPT** | Protocol now |
| Strategy Certification Engine + signed package | **ADAPT** | Scaffold now |
| InvestMitra ↔ NexTrade Research Hypothesis contract | **ADAPT** | Contracts now |
| VectorBT as research accelerator | **ADAPT later** | After observation + licence review |
| PWB Toolbox selective content | **ADOPT later** | Post-freeze research |
| NautilusTrader / LEAN patterns | **STUDY** | Phase 7E |
| PySystemTrade portfolio concepts | **STUDY** | Phase 7D |
| HftBacktest | **OPTIONAL** | Microstructure only |
| pwb-alphaevolve | **EXPERIMENT** | Sandbox only |
| Replace NexTrade execution with LEAN/Backtrader | **REJECT** | — |

---

## 2. Freeze compliance

| Work | Allowed under OIE-001? |
|------|------------------------|
| Docs + contracts + certification scaffold | ✅ Yes (no live trading path) |
| Install VectorBT / wire into paper fills | ❌ No |
| New strategy entry/exit rules or scoring | ❌ No |
| Risk-limit / execution-gate changes | ❌ No |

---

## 3. Implemented in this tranche (NOW)

1. `docs/NEXTRADE_QUANT_RESEARCH_STACK_EVALUATION_V1.md` — ADOPT/ADAPT/STUDY matrix  
2. `contracts/strategy_research.py` — hypothesis, lifecycle, certification records  
3. `research/backtest_protocol.py` — `BacktestEngine` Protocol + result types  
4. `research/strategy_certification_engine.py` — certification gate (research only)  
5. `research/legacy_backtest_adapter.py` — existing V2 engine behind protocol  
6. `research/robustness.py` — walk-forward windows + trade-shuffle Monte Carlo  
7. `research/certification_store.py` — JSONL persistence under `storage/research/`  
8. Unit tests for lifecycle invariant, robustness, and persistence  

---

## 4. Explicit non-goals (this tranche)

- No VectorBT/Nautilus/LEAN runtime dependency  
- No automatic strategy promotion to paper/live  
- No InvestMitra execution path  
- No change to Risk Engine or paper observation clock  
- Legacy adapter does **not** yet map draft entry/exit rules into V2 signals (scaffolding only)  

---

## 5. Next after valid 15-day observation (Phase 7A+)

```text
7A  VectorBT adapter behind BacktestEngine (licence gate)
7B  Walk-forward / Monte Carlo / TCA robustness
7C  Signed Strategy Package binding to registry
7D  Portfolio Intelligence (PySystemTrade concepts)
7E  Event-driven research (Nautilus study)
7F  AI Alpha Lab (sandbox only)
```
