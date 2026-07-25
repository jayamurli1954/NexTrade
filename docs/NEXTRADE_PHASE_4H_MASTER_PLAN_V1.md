# NexTrade Phase 4H — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4H constructs NexTrade's **Evidence-Based Promotion Validation Subsystem**, establishing a fail-closed readiness certification gate that evaluates empirical evidence collected across 4A–4G before certifying promotion eligibility from Shadow Mode to Phase 4I Readiness Audit and Phase 4J Controlled Live Staging.

---

## Master Safety Invariants (4H-P1 & 4H-P2)

### Invariant 4H-P1 — Certification Is Not Execution Authorization
> A `PROMOTE` decision certifies eligibility ONLY. **It MUST NOT change `ExecutionEnvironment`, enable live trading, unlock broker dispatch, or invoke `BrokerAdapter.submit_order()`.** Environment transitions require downstream 4I Readiness Audit and 4J Controlled Live Staging authorization.

### Invariant 4H-P2 — Deterministic Evidence Provenance
> Every `PROMOTE`, `HOLD`, or `REJECT` decision MUST be reproducible from an immutable, timestamp-bounded evidence snapshot whose canonical representation produces a deterministic SHA-256 fingerprint (`evidence_snapshot_hash`, `shadow_dataset_hash`, `dlq_snapshot_hash`, `metrics_snapshot_hash`).

---

## Decision Precedence & Outcome Rules

```text
Decision Precedence: REJECT > HOLD > PROMOTE
```

1. **`REJECT` (Mandatory Breach)**: Imposed when ANY mandatory safety invariant (S1–S12), core state machine rule (E1–E41), unexpected safety failure, hard-halt breach, or reconciliation discrepancy occurs. Mandatory safety failures are **sticky** and cannot be washed away within the evaluation cycle.
2. **`HOLD` (Insufficient Sample / Stale Evidence)**: **Default outcome** whenever observation sample size is insufficient (`total_orders < minimum_required_observations`, default 50) or evidence snapshot age exceeds `max_evidence_age_seconds` (24h).
3. **`PROMOTE` (Eligible for Readiness Audit)**: Certified ONLY when 100% of safety, integrity, reconciliation, observability, and performance gates pass AND sample size meets or exceeds `minimum_required_observations`.

---

## Safety & Certification Verification Checklist

- [x] All 10 Sub-Phase 4H unit and integration tests passed.
- [x] Invariant `4H-P1` verified: Promotion code has 0 execution authority, 0 environment mutation, and 0 order submissions.
- [x] Invariant `4H-P2` verified: Deterministic SHA-256 fingerprints computed over canonical JSON serializations.
- [x] Decision precedence (`REJECT > HOLD > PROMOTE`) enforced.
- [x] Sample size < 50 or evidence age > 24h correctly yields `HOLD`.
- [x] Sticky safety failures yield `REJECT`.
- [x] Dual persistence in SQLite (`promotion_decision.db`) and JSONL (`promotion_decision.jsonl`) verified.
- [x] Phase 3 E1–E41 state machine invariants and Phase 4D S1–S12 safety bounds preserved.
