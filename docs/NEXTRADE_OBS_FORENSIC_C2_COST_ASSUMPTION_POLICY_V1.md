# OBS-FORENSIC-REPAIR — C2 Cost-Assumption Policy V1

**Status:** APPROVED FOR FORENSIC USE (policy/design only)  
**Date:** 2026-08-13  
**Scope:** Observation / forensic reporting only  
**Does NOT change:** strategy defs, exits, scoring, risk limits, live paper cost engine defaults, LIVE promotion

---

## 1. Purpose

Establish which P&L definitions are authoritative for **OBS-FORENSIC** analysis so strategy conclusions do not flip depending on whether the 0.05% slippage proxy is included.

Evidence from Investigation C (`OBS_FORENSIC_56_Cost_Validation_20260813`):

- Log charges ≡ rebuild with current model (56/56 match).
- ~52% of estimated “costs” were the **0.05% turnover slippage** proxy.
- Without slippage, sample economics change materially but remain negative overall.

Therefore slippage is a **scenario parameter**, not a verdict on strategy quality.

---

## 2. Triple P&L framework (mandatory for forensic reports)

For every closed paper trade, forensic artifacts MUST report three views:

| View ID | Name | Formula | Purpose |
|---------|------|---------|---------|
| **V1** | Gross P&L | Entry/exit price difference × qty (direction-aware) | Signal / direction quality |
| **V2** | Net P&L — charges only | V1 − statutory/broker charges (no slippage) | Economic viability under tariff |
| **V3** | Net P&L — full friction | V1 − charges − assumed slippage | Conservative execution robustness |

Charge components in **V2** (Angel One equity intraday template, research):

- Brokerage (2 orders)
- GST (on brokerage + exchange txn, per current `broker_charges.py`)
- STT (sell leg)
- Exchange transaction charge
- SEBI turnover charge
- Stamp duty (buy leg)

**V3** adds:

- Slippage = turnover × `slippage_pct` (default **0.05%** of buy+sell turnover) as a **scenario**, not empirical Angel fill shortfall.

```text
SIGNAL QUALITY          →  V1 Gross
ECONOMIC VIABILITY      →  V2 Gross − charges
EXECUTION ROBUSTNESS    →  V3 Gross − charges − assumed slippage
```

---

## 3. Governance rules

1. **Do not turn slippage off and pretend it does not exist.** Always publish V1, V2, and V3 together.
2. **0.05% slippage must not alone determine KEEP / TUNE / RETIRE** for a strategy.
3. Strategy quality claims require at least **V1 and V2**; V3 is stress/robustness.
4. Until empirical slippage is measured from Angel WS paper fills (decision price vs fill, adverse selection), treat V3 as **assumed friction**, not observed.
5. **Do not change** `trading_app/broker_charges.py` defaults as part of C2. Dual/triple reporting lives in forensic rebuilds.
6. Strategy / exit / scoring / risk freeze remains intact. C2 is reporting policy only.

---

## 4. Classification language (for later strategy forensics)

After clean identity + decision-trace evidence, classify strategies using all three views:

| Pattern | Interpretation |
|---------|----------------|
| V1>0, V2>0, V3>0 | Robust under conservative friction |
| V1>0, V2>0, V3≤0 | Viable after charges; fragile to assumed slip |
| V1>0, V2≤0 | Edge fails under statutory/broker costs |
| V1≤0 | Negative before friction — signal/exit/routing suspect |

---

## 5. Observation period posture (current)

- Continue paper observation without strategy changes.
- Accumulate evidence with V1/V2/V3 preserved on each forensic refresh.
- Monitor Angel WS authority + quote freshness (OIE-001).
- Do not optimise on individual wins/losses.
- Next dependency order after C2 freeze: **A (canonical IDs) → B (decision trace) → larger sample → strategy forensics**.

---

## 6. Artifacts

| Artifact | Role |
|----------|------|
| This doc | Policy |
| `research/build_obs_forensic_triple_pnl.py` | Rebuild V1/V2/V3 for the 56-trade baseline |
| `reports/OBS_FORENSIC_56_Triple_PnL_20260813.xlsx` | Baseline triple-P&L workbook |

---

## 7. Explicit non-goals

- No strategy parameter tuning
- No exit-rule changes
- No suitability/scoring formula changes
- No LIVE promotion
- No silent change of paper Excel “Est. Charges” meaning without dual columns
