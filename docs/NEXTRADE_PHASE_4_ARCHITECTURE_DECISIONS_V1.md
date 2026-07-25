# NexTrade Phase 4 — Architecture Decision Records (ADR-001 — ADR-010)

## Executive Summary
This document records the formal **Architecture Decision Records (ADRs)** governing NexTrade Phase 4 (External Broker & Live Market Integration). These decision records establish non-negotiable boundaries, safety gates, and architectural patterns to protect system capital and preserve the frozen Phase 3 core.

---

## ADR-001 — Phase 3 Golden Baseline Immutability
* **Status**: APPROVED
* **Context**: Phase 3 established a 100% verified execution, protection, and reconciliation engine baseline (`v3.0-phase-3-complete` / commit `db4a6ac`).
* **Decision**: Phase 4 additions (safety gates, broker adapters, market data adapters) wrap around the Phase 3 core. Zero code changes are permitted to touch Phase 3 invariants (E1–E41) or core execution control logic. Any behavior discrepancies discovered must be handled as formal DISCOVERY change proposals.
* **Consequences**: Ensures zero regression in verified protection, reconciliation, and audit machinery.

---

## ADR-002 — Broker Adapter Abstraction Pattern
* **Status**: APPROVED
* **Context**: Core engine components (`ExecutionEngine`, `ExecutionGateway`, `RiskEngine`) must remain isolated from specific broker API protocols.
* **Decision**: Define a generic, broker-neutral `BrokerAdapter` abstract base class defining standard order submission, cancellation, modification, status querying, fill reporting, and error normalization methods.
* **Consequences**: Core NexTrade engines do not know whether the active adapter is Paper, Interactive Brokers (IBKR), or a future exchange adapter.

---

## ADR-003 — Defense-in-Depth Live Safety Gate
* **Status**: APPROVED
* **Context**: Risk checks in Phase 2/3 protect strategy intent, but Phase 4 requires strict physical barriers before real capital or live API calls can be touched.
* **Decision**: Insert an explicit `LiveSafetyGate` layer between `ExecutionGateway` and `BrokerAdapter`. The safety gate enforces hard limiters (`LIVE_TRADING_ENABLED`, Hard Halt, Daily Loss Cap, Max Order Notional, Rate Limiter) and fails closed on any unverified state.
* **Consequences**: Execution requests that pass RiskEngine and ExecutionGateway are still blocked if live safety thresholds or health parameters fail.

---

## ADR-004 — Default-False Live Execution Control
* **Status**: APPROVED
* **Context**: Accidental execution of live orders during development or testing must be impossible.
* **Decision**: Set `LIVE_TRADING_ENABLED = False` by default across all configuration layers.
* **Consequences**: The system cannot place live broker orders without multi-layer explicit unlock overrides.

---

## ADR-005 — Multi-Factor Live Safety Unlock
* **Status**: APPROVED
* **Context**: Enabling live execution requires explicit, multi-dimensional verification.
* **Decision**: Live order routing requires all of the following conditions to simultaneously evaluate to TRUE:
  `LIVE_TRADING_ENABLED == True` AND `ENVIRONMENT == LIVE` AND `HARD_HALT == False` AND `OPERATOR_AUTHORIZATION == VALID` AND `RISK_LIMITS == HEALTHY` AND `BROKER_HEALTH == HEALTHY` AND `RECONCILIATION_BACKLOG == 0` AND `AUDIT_LOGGER == HEALTHY`.
* **Consequences**: Failing any single check causes immediate fail-closed denial.

---

## ADR-006 — UNKNOWN State & Reconciliation Boundary Semantics
* **Status**: APPROVED
* **Context**: Post-submission broker ambiguity (timeouts, socket drops) yields status `UNKNOWN`.
* **Decision**: Status `UNKNOWN` is a terminal state within `ExecutionStateMachine`'s normal transition graph (`VALID_TRANSITIONS[UNKNOWN] = set()`). Outward transitions from `UNKNOWN` are strictly restricted to `ExecutionStateMachine.reconcile_to()`, which requires exclusive `RECONCILIATION_AUTHORITY_KEY` held only by `ReconciliationEngine`.
* **Consequences**: Direct retries of `UNKNOWN` orders are physically prohibited. State resolution requires authoritative broker reconciliation.

---

## ADR-007 — Dual Persistence Strategy for Shadow Mode
* **Status**: APPROVED
* **Context**: Shadow Mode evaluates hypothetical strategy/execution performance against live market data without sending live orders.
* **Decision**: **SQLite** serves as the authoritative primary persistence engine for comparative analytics, decisions, expected fills, and slippage data. **JSONL** is retained as an optional, append-only diagnostic export for streaming audit and forensic debugging.
* **Consequences**: Enables rich SQL queries for execution quality while retaining fast event streaming for forensics.

---

## ADR-008 — Broker Selection & Staging Roadmap
* **Status**: APPROVED
* **Context**: Selecting the target broker implementation path for Phase 4.
* **Decision**: Build the generic `BrokerAdapter` contract first -> implement **Interactive Brokers (IBKR TWS/Gateway API)** as the first real broker adapter target -> retain `PaperBrokerAdapter` as the regression reference baseline.
* **Consequences**: IBKR provides robust production-grade verification (partial fills, rate limits, market data, order lifecycle), while keeping the adapter boundary neutral for future broker integrations.

---

## ADR-009 — Environment Isolation & Credential Security
* **Status**: APPROVED
* **Context**: Preventing API key exposure or environment confusion between Sandbox and Live accounts.
* **Decision**: Standardize `ExecutionEnvironment` enum (`PAPER`, `SANDBOX`, `SHADOW`, `LIVE`). API credentials must be injected via secure environment variables managed outside git repositories. Live credentials cannot be loaded in Sandbox or Paper mode.
* **Consequences**: Strict physical isolation prevents test scripts from invoking live production accounts.

---

## ADR-010 — Promotion Model & Staged Deployment
* **Status**: APPROVED
* **Context**: Progression criteria before production capital is exposed.
* **Decision**: Enforce strict promotion sequence: `PAPER -> BROKER SANDBOX -> SHADOW MODE -> CONTROLLED LIVE -> FULL PRODUCTION`. Each stage requires 100% test pass rate and formal audit verification.
* **Consequences**: Prevents unverified components or strategies from advancing directly to live deployment.
