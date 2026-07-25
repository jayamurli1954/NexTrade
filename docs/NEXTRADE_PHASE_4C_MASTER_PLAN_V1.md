# NexTrade Sub-Phase 4C — Master Architecture & Sandbox Verification Plan (v1.0)

## Executive Summary

Sub-Phase 4C establishes the **Broker Contract & Sandbox Verification Subsystem** for NexTrade, validating that the canonical broker contracts (`BrokerAdapter`, `BrokerOrderRequest`, `BrokerOrderResult`) and concrete adapter implementations accurately model external broker mechanics (Interactive Brokers paper/sandbox) under strict safety controls.

This document serves as the formal specification for physical port security guards, session management, sandbox harness verification, failure injection results, and the 17-point compatibility matrix established in Sub-Phase 4C baseline (`v3.3-phase-4c-sandbox-verification-complete`).

---

## 1. Physical Security Bounds & Enclosure

Sub-Phase 4C operates under strict physical enclosure guards configured in `config/ibkr_config.py`:

```text
               LIVE_TRADING_ENABLED = False
                            │
                            ▼
              validate_sandbox_config() Guard
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
          ▼                                   ▼
  Paper Ports (7497 / 4002)           Live Ports (7462 / 4001)
  & Paper Accounts (DUxxxxxx)         & Live Accounts (Uxxxxxx)
          │                                   │
          ▼                                   ▼
    🟢 PASSED                           🔴 PermissionError
 (Execution Permitted)               (PHYSICAL BLOCK & FAIL-CLOSED)
```

---

## 2. Sandbox Verification Subsystem Architecture

```text
                     NEXTRADE EXECUTION CORE
                               │
                     Phase 3 E1–E41 Boundary
                               │
                               ▼
                       Live Safety Gate
             (LIVE_TRADING_ENABLED = False Guard)
                               │
                               ▼
                 Domain Translation Boundary
     (ExecutionRequest  ──────►  BrokerOrderRequest)
     (ExecutionResult   ◄──────  BrokerOrderResult)
                               │
                               ▼
                   IBKRBrokerAdapter Boundary
                               │
            ┌──────────────────┴──────────────────┐
            │                                     │
            ▼                                     ▼
   IBKRSandboxHarness                  IBKR Client Socket
   (Offline Test Mode)                 (Paper/Sandbox Port 7497/4002)
            │                                     │
            └──────────────────┬──────────────────┘
                               │
                               ▼
                     IBKR Session Manager
            (Health / Reconnect / Heartbeat)
                               │
                               ▼
            Broker Contract Compatibility Matrix
       (17 Verified Capabilities & Failure Scenarios)
```

---

## 3. Sub-Phase 4C Verification Matrix & Results

All 17 capability domains have been verified across explicit verification levels documented in [NEXTRADE_BROKER_COMPATIBILITY_MATRIX_V1.md](file:///d:/Back_up/NexTrade/docs/NEXTRADE_BROKER_COMPATIBILITY_MATRIX_V1.md):

* `OFFLINE_HARNESS_VERIFIED`: **17 / 17 Domains (100%)**
* `IBKR_PAPER_VERIFIED`: Ready for optional TWS paper socket pairing on ports `7497`/`4002`.
* Production Code Modifications to Phase 3: **0 Mutations**
* Total System Test Baseline: **208 / 208 PASSED (100%)**

---

## 4. Next Step Progression

Following Sub-Phase 4C sign-off, NexTrade moves to:
```text
Sub-Phase 4C (Sandbox Verification) ──► Sub-Phase 4D (Live Gateway Safety Controls)
```
