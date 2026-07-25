# NexTrade Sub-Phase 4B — Master Architecture & Integration Contract (v1.0)

## Executive Summary

Sub-Phase 4B constructs the **broker-neutral external integration boundary** for NexTrade, completing the abstraction layer between NexTrade's Phase 3 execution control subsystem and external broker APIs.

This document serves as the formal specification for the canonical broker domain contracts, error normalization taxonomy, capability validation model, and IBKR adapter boundary implemented in Sub-Phase 4B baseline (`v3.2-phase-4b-broker-boundary-complete`).

---

## 1. Domain Translation Architecture

```text
                     NEXTRADE EXECUTION CORE
                               │
                               ▼
                       Execution Gateway
                               │
                     Phase 3 E1–E41 Boundary
                               │
                               ▼
                        Live Safety Gate
                               │
                               ▼
                   Domain Translation Boundary
     (ExecutionRequest  ──────►  BrokerOrderRequest)
     (ExecutionResult   ◄──────  BrokerOrderResult)
                               │
                               ▼
                  Broker Integration Boundary
                               │
       ┌───────────────────────┴───────────────────────┐
       │                                               │
       ▼                                               ▼
BrokerAdapter                                   BrokerEventStream
(Sync Operations)                               (Async Callbacks)
       │                                               │
       ├───────────────────────┬───────────────────────┤
       ▼                       ▼                       ▼
PaperBrokerAdapter      IBKRBrokerAdapter        Future Adapters
(Conforms 100%)         (Skeleton + Mock Trans.) (Neutral Extensibility)
       │                       │                       │
       ▼                       ▼                       ▼
  PaperTrader            Mocked IBKR Trans.       Other Mock
```

### Architectural Guarantees:
1. **One-Way Request Translation**: `ExecutionRequest` (Phase 3 model) is translated to `BrokerOrderRequest` at the gateway boundary. `BrokerAdapter` implementations handle `BrokerOrderRequest` only.
2. **Reverse Result Normalization**: `BrokerOrderResult` returned by an adapter is normalized and translated to `ExecutionResult`.
3. **Identity Separation**: `nextrade_execution_id` and `idempotency_key` (NexTrade identity) are strictly distinguished from `broker_order_id` and `broker_fill_id` (external broker identity).
4. **Zero SDK Coupling**: `core/`, `execution/`, `risk/`, `protection/`, and `contracts/` packages contain 0 imports of external broker SDKs (`ibapi`, `ib_insync`, `alpaca_trade_api`, etc.). Verified via `tests/test_broker_isolation.py`.

---

## 2. Canonical Domain Contracts Summary

| Module | Contract / Class | Purpose & Definition |
| :--- | :--- | :--- |
| `contracts/broker_domain.py` | `BrokerOrderRequest` | Frozen dataclass representing order placement request (`nextrade_execution_id`, `idempotency_key`, `symbol`, `side`, `order_type`, `quantity`, `limit_price`, `stop_price`). |
| `contracts/broker_domain.py` | `BrokerOrderModificationRequest` | Frozen dataclass representing order parameter changes (`nextrade_execution_id`, `broker_order_id`, `new_quantity`, `new_limit_price`, `new_stop_price`). |
| `contracts/broker_domain.py` | `BrokerOrderResult` | Frozen dataclass representing execution outcome (`nextrade_execution_id`, `idempotency_key`, `broker_order_id`, `status`, `filled_quantity`, `remaining_quantity`, `average_fill_price`, `error_code`, `error_message`, `requires_reconciliation`). |
| `contracts/broker_domain.py` | `BrokerOrder`, `BrokerFill`, `BrokerPosition`, `BrokerAccount`, `BrokerEvent` | Normalized domain snapshots for state querying and event streaming. |
| `contracts/broker_adapter_v1.py` | `BrokerAdapter` | Abstract base class for synchronous broker operations (`submit_order`, `get_order`, `cancel_order`, `modify_order`, `get_position`, `get_account`, `get_open_orders`, `health_check`, `get_capabilities`). |
| `contracts/broker_adapter_v1.py` | `BrokerEventStream` | Abstract base class for asynchronous callback events (`subscribe`, `unsubscribe`, `poll_events`). |

---

## 3. Error Normalization Taxonomy & UNKNOWN Boundary

Errors are categorized into a deterministic taxonomy (`BrokerErrorType`) in `contracts/broker_error.py`:

```text
Deterministic Pre-Submission Failure
(AUTHENTICATION_ERROR, INSUFFICIENT_FUNDS, UNSUPPORTED_ORDER, MARKET_CLOSED)
          │
          ▼
    BrokerOrderStatus.REJECTED
    (requires_reconciliation = False)

Post-Submission Socket / Network Uncertainty
(TIMEOUT, CONNECTION_ERROR, UNKNOWN_BROKER_ERROR)
          │
          ▼
    BrokerOrderStatus.UNKNOWN
    (requires_reconciliation = True)
    (ZERO automatic retries permitted without ReconciliationEngine)
```

---

## 4. Dual-Layer Capability Validation

Order feasibility is validated in two defense-in-depth layers:
- **Layer 1 (Central Generic Validation)**: `CapabilityValidator.validate(capabilities, request)` checks if the requested order type, trailing stop, or fractional quantity is supported by the target adapter's `BrokerCapabilities` matrix before dispatching network calls.
- **Layer 2 (Adapter-Specific Validation)**: Concrete adapter implementations perform custom parameter checks.

---

## 5. Sub-Phase 4B Deliverables & Verification Matrix

| Work Package | Implementation File | Verification Test Case | Result |
| :--- | :--- | :--- | :---: |
| **4B-1 & 4B-2 Domain Contracts** | `contracts/broker_domain.py`, `contracts/broker_translation.py` | `test_one_way_translation_request_and_lineage_preservation` | 🟢 PASSED |
| **4B-3 Error Taxonomy** | `contracts/broker_error.py` | `test_error_taxonomy_classification` | 🟢 PASSED |
| **4B-4 Capability Model** | `contracts/broker_capabilities.py` | `test_capability_validator_enforces_supported_types` | 🟢 PASSED |
| **4B-5 Abstract Interfaces** | `contracts/broker_adapter_v1.py` | `test_paper_broker_adapter_conformance` | 🟢 PASSED |
| **4B-6 Core SDK Isolation** | `core/`, `execution/`, `risk/`, `protection/`, `contracts/` | `test_no_broker_sdk_imports_in_core_subsystems` | 🟢 PASSED |
| **4B-7 Paper Adapter Conformance** | `brokers/paper_adapter.py` | `test_paper_broker_adapter_conformance` | 🟢 PASSED |
| **4B-8 IBKR Adapter Skeleton** | `brokers/ibkr_adapter.py`, `brokers/ibkr_translator.py`, `brokers/ibkr_mock.py` | `test_ibkr_adapter_clean_order_submission` | 🟢 PASSED |
| **4B-9 Failure Injection & UNKNOWN** | `brokers/ibkr_adapter.py` | `test_ibkr_adapter_post_submission_timeout_yields_unknown_status` | 🟢 PASSED |
| **4B-10 Full Subsystem Regression** | Entire Codebase | `python -m pytest tests/ -v` (203/203 PASSED) | 🟢 PASSED |
