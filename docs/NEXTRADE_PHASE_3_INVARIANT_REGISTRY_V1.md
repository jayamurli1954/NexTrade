# NexTrade Phase 3 — Master Invariant Registry (E1 — E41)

## Executive Summary
This document serves as the **authoritative Master Invariant Registry** for the NexTrade Execution, Protection & Reconciliation Subsystem (Phase 3). It consolidates all 41 operational and safety invariants established from Sub-Phase 3A through Sub-Phase 3H.

---

## 1. Execution Domain Contracts & Gateway Invariants (E1 — E16)

| ID | Invariant Name | Enforcing Module | Definition & Enforcement Mechanism | Failure Behavior | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **E1** | Default Deny Gate | `ExecutionAuthorizationGate` | Deny execution by default unless RiskDecision is explicitly APPROVED/MODIFIED and AuditLogger health is OK. | Returns `is_authorized = False`, logs rejection event. | 🟢 PASS |
| **E2** | Decision Binding | `ExecutionGateway` | Execution quantity must satisfy \(0 < Q_{\text{execution}} \le Q_{\text{approved}} \le Q_{\text{requested}}\). | Rejects request with `QUANTITY_EXCEEDED`. | 🟢 PASS |
| **E3** | Audit Logger Coupling | `ExecutionGateway` | Gate checks `audit_logger.health()`. If degraded or corrupted, execution is prohibited. | Returns `EXECUTION_GATE_DENIED`. | 🟢 PASS |
| **E4** | Risk Lineage Traceability | `ExecutionRequest` | Every request must retain immutable `risk_decision_id` and `idempotency_key`. | `ValueError` on initialization if missing. | 🟢 PASS |
| **E5** | Immutable Contracts | `contracts/execution.py` | `ExecutionRequest` and `ExecutionResult` are frozen dataclasses. | Runtime mutation attempt raises `FrozenInstanceError`. | 🟢 PASS |
| **E6** | Non-Retryable UNKNOWN | `contracts/execution.py` | Status `UNKNOWN` sets `requires_reconciliation = True`. Retries strictly prohibited without reconciliation. | `requires_reconciliation` evaluates to `True`. | 🟢 PASS |
| **E7** | Metric Monotonicity | `ExecutionResult` | Requires \(0 \le Q_{\text{filled}} \le Q_{\text{execution}}\) and \(Q_{\text{remaining}} = Q_{\text{execution}} - Q_{\text{filled}}\). | `ValueError` on post-init validation failure. | 🟢 PASS |
| **E8** | Execution Audit Chain | `ExecutionGateway` | All execution attempts generate immutable audit log records. | Audit failure blocks execution dispatch. | 🟢 PASS |
| **E9** | Mandatory UNKNOWN Reconciliation | `contracts/execution.py` | Status `UNKNOWN` requires explicit `ReconciliationEngine` resolution before any further action. | Request flagged for reconciliation queue. | 🟢 PASS |
| **E10** | Idempotency Intent Binding | `ExecutionGateway` | Reusing `idempotency_key` with conflicting request parameters triggers immediate rejection. | Rejects with `IDEMPOTENCY_CONFLICT`. | 🟢 PASS |
| **E11** | Broker Isolation | `PaperBrokerAdapter` | RiskEngine remains completely unaware of concrete broker implementation details. | Modular interface separation. | 🟢 PASS |
| **E12** | Quantity Preservation | `PaperBrokerAdapter` | Fill metrics strictly bounded: \(0 \le Q_{\text{filled}} \le Q_{\text{execution}}\). | Clamped or rejected with pre-submission error. | 🟢 PASS |
| **E13** | No Live Connectivity | `PaperBrokerAdapter` | Pure paper simulation engine without live broker endpoints or API keys. | Zero network requests initiated. | 🟢 PASS |
| **E14** | Unknown-State Preservation | `PaperBrokerAdapter` | Post-submission timeouts return `ExecutionStatus.UNKNOWN` with `requires_reconciliation = True`. | `UNKNOWN` status returned cleanly. | 🟢 PASS |
| **E15** | Pre vs Post Error Isolation | `PaperBrokerAdapter` | Pre-submission errors yield `REJECTED`; post-submission ambiguity yields `UNKNOWN`. | Distinct failure classifications. | 🟢 PASS |
| **E16** | Full Lineage Preservation | `PaperBrokerAdapter` | Preserves `execution_request_id`, `risk_decision_id`, `signal_id`, and `broker_order_id`. | Full field pass-through in `ExecutionResult`. | 🟢 PASS |

---

## 2. Protection Layer Invariants (E17 — E23)

| ID | Invariant Name | Enforcing Module | Definition & Enforcement Mechanism | Failure Behavior | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **E17** | Stop-Loss Direction Integrity | `contracts/protection.py` | LONG: \(\text{SL} < \text{Entry}\). SHORT: \(\text{SL} > \text{Entry}\). | `ValueError` on plan initialization. | 🟢 PASS |
| **E18** | Take-Profit Direction Integrity | `contracts/protection.py` | LONG: \(\text{TP} > \text{Entry}\). SHORT: \(\text{TP} < \text{Entry}\). | `ValueError` on plan initialization. | 🟢 PASS |
| **E19** | Trailing Stop Monotonicity | `contracts/protection.py` | LONG SL monotonically non-decreasing (\(\text{SL}_{\text{new}} \ge \text{SL}_{\text{prev}}\)). SHORT SL non-increasing. | Trailing step calculation ignores adverse ticks. | 🟢 PASS |
| **E20** | Trailing Activation Lifecycle | `contracts/protection.py` | Trailing stop remains dormant until market price reaches `trailing_activation_price`. | No trailing adjustments performed. | 🟢 PASS |
| **E21** | Trailing Distance vs Step Separation | `contracts/protection.py` | `trailing_distance` defines offset (ABSOLUTE/PERCENTAGE); `trailing_step` defines update threshold. | Independent parameter validation. | 🟢 PASS |
| **E22** | Exit Decision Lineage | `ProtectionLifecycleManager` | Exit `ExecutionRequest` retains `position_id`, `risk_decision_id`, and `protection_generation`. | Traceable exit payload. | 🟢 PASS |
| **E23** | Immutable Protection Audit | `ProtectionLifecycleManager` | Every stop adjustment emits a `ProtectionAdjustmentEvent`. | Appended to adjustment audit history. | 🟢 PASS |

---

## 3. Reconciliation Engine Invariants (E29 — E33)

| ID | Invariant Name | Enforcing Module | Definition & Enforcement Mechanism | Failure Behavior | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **E29** | Reconciliation Authority Boundary | `execution/state_machine.py` | Only `ReconciliationEngine` may call `ExecutionStateMachine.reconcile_to()` with valid authority key. | `PermissionError` or `ValueError` on unauthorized calls. | 🟢 PASS |
| **E30** | Position Quantity Conservation | `execution/reconciler.py` | \(Q_{\text{open\_new}} = Q_{\text{open\_old}} \pm \Delta Q_{\text{fill}}\) with \(0 \le Q_{\text{open}}\) and \(Q_{\text{protected}} \le Q_{\text{open}}\). | `CRITICAL` discrepancy logged if violated. | 🟢 PASS |
| **E31** | Cumulative Fill Monotonicity | `execution/reconciler.py` | Delta fill \(\Delta Q = \max(0, Q_{\text{authoritative}} - Q_{\text{reconciled}})\) prevents double fill accounting. | Non-overlapping delta calculation. | 🟢 PASS |
| **E32** | Authoritative Broker State & Discrepancies | `execution/reconciler.py` | Broker order status is authoritative for orders; position mismatches trigger `CRITICAL` audit reports. | Discrepancy report generated without blind overwrite. | 🟢 PASS |
| **E33** | Deterministic Idempotency Identity | `execution/reconciler.py` | SHA-256 hash `reconciliation_key` over broker state. Re-submitting returns cached result with 0 mutations. | Cached result returned cleanly. | 🟢 PASS |

---

## 4. Execution Engine Subsystem Invariants (E34 — E41)

| ID | Invariant Name | Enforcing Module | Definition & Enforcement Mechanism | Failure Behavior | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **E34** | Controlled Gateway Entry Single Point | `execution/engine.py` | Entry orders must originate from authorized `RiskDecision` payloads passing through `ExecutionGateway`. | Rejects unauthorized or zero-qty decisions early. | 🟢 PASS |
| **E35** | No Broker Bypass for Protection Exits | `execution/engine.py` | All protection exit requests pass through `ExecutionGateway` -> `BrokerAdapter`. | Direct broker calls strictly prohibited. | 🟢 PASS |
| **E36** | Authoritative State Machine Sync | `execution/engine.py` | `ExecutionStateMachine` is authoritative for order lifecycle states across subsystem. | Synchronized transition records. | 🟢 PASS |
| **E37** | Automatic UNKNOWN Escalation | `execution/engine.py` | `UNKNOWN` status automatically registers with `ReconciliationEngine` with **ZERO AUTOMATIC RETRIES**. | Queued in pending unknown registry. | 🟢 PASS |
| **E38** | Subsystem Restart Serialization | `execution/engine.py` | Complete state recovery via `to_dict()` and `from_dict()`. Zero duplicate orders/managers post-restart. | 100% state rehydration. | 🟢 PASS |
| **E39** | Execution Lineage Preservation | `execution/engine.py` | Preserves `execution_request_id`, `risk_decision_id`, `signal_id`, `position_id`, and `idempotency_key`. | Full lineage dictionary stored. | 🟢 PASS |
| **E40** | Position Quantity Conservation Equation | `execution/engine.py` | \(Q_{\text{open}} = Q_{\text{entry}} - Q_{\text{exit\_cumulative}}\) and \(0 \le Q_{\text{protected}} \le Q_{\text{open}}\). | Consolidated open quantity. | 🟢 PASS |
| **E41** | Single Protection Manager per Position | `execution/engine.py` | Ensures `position_id` maps to exactly 0 or 1 active `ProtectionLifecycleManager`. | Scale-in updates existing manager. | 🟢 PASS |
