# NexTrade Broker Contract Compatibility Matrix (v1.0)

## Executive Summary

This document serves as the formal **Broker Contract Compatibility Matrix** for NexTrade Sub-Phase 4C. It evaluates and records the exact verification level of all 17 broker capability domains across NexTrade's canonical broker abstraction (`BrokerAdapter`) and the Interactive Brokers (IBKR) adapter implementation.

---

## Verification Level Taxonomy

Each capability domain is classified under one of the following explicit verification levels:

* 🟢 **OFFLINE_HARNESS_VERIFIED**: Deterministically verified against `IBKRSandboxHarness` and `MockIBKRTransport` unit test suites.
* 🟡 **IBKR_PAPER_VERIFIED**: Verified against actual Interactive Brokers TWS / IB Gateway Paper Trading environment (Ports 7497 / 4002).
* 🔵 **PENDING_LIVE_VERIFICATION**: Invariant and contract handling verified offline, awaiting Phase 4J live market verification.
* ⚪ **NOT_APPLICABLE / NOT_SUPPORTED**: Feature explicitly declared as unsupported in `BrokerCapabilities` matrix.

---

## 17-Point Domain Compatibility Matrix

| # | Capability / Domain | Description & Invariant Enforcement | Verification Level | Test Evidence File | Status |
| :-: | :--- | :--- | :---: | :--- | :---: |
| **1** | **Market Order Execution** | Immediate fill at market price (`BrokerOrderType.MARKET`). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **2** | **Limit Order Execution** | Price-bounded execution (`BrokerOrderType.LIMIT`). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **3** | **Stop Order Execution** | Trigger-bounded exit (`BrokerOrderType.STOP`). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **4** | **Stop-Limit Order Execution** | Dual-bound trigger (`BrokerOrderType.STOP_LIMIT`). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **5** | **Trailing Stop Execution** | Dynamic trailing offset (`BrokerOrderType.TRAILING_STOP`). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **6** | **Partial Fill Accounting** | Monotonic partial fill aggregation (\(0 \le Q_{\text{filled}} \le Q_{\text{total}}\), Invariant E31). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **7** | **Order Cancellation** | Typed cancellation via `cancel_order()`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **8** | **Order Modification** | Typed modification via `modify_order(BrokerOrderModificationRequest)`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **9** | **Pre-Submission Rejection** | Deterministic error classification -> `BrokerOrderStatus.REJECTED` (Invariant E15). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **10** | **Rate Limit Throttling** | Pacing error classification -> `REJECTED` with code `162`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **11** | **Socket Timeout Boundary** | Post-submission timeout -> `BrokerOrderStatus.UNKNOWN` with `requires_reconciliation = True` (Invariants E6, E14, E37). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **12** | **Disconnect Detection** | Connection health state transition to `DISCONNECTED`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **13** | **Automated Reconnection** | Exponential backoff reconnection via `IBKRSessionManager`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **14** | **Account State Query** | Account equity, cash, margin retrieval via `get_account()`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **15** | **Position State Query** | Quantity and entry price retrieval via `get_position()`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **16** | **Open Orders Query** | Snapshot of active orders via `get_open_orders()`. | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |
| **17** | **Authoritative State Sync** | Reconciliation query matching internal vs broker state (`query_execution`). | 🟢 `OFFLINE_HARNESS_VERIFIED` | `tests/test_ibkr_sandbox_verification.py` | 🟢 VERIFIED |

---

## Summary of Verification Status
* Total Capability Domains Evaluated: **17 / 17**
* `OFFLINE_HARNESS_VERIFIED`: **17 / 17** (100%)
* `IBKR_PAPER_VERIFIED`: Environment ready for TWS Paper socket pairing (Sub-Phase 4C optional live socket pass)
* `PENDING_LIVE_VERIFICATION`: 0 (Phase 4J)
* Production Baseline Invariants E1–E41: **100% UNTOUCHED & PASS**
