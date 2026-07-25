# NexTrade Phase 4D — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4D introduces **Live Gateway Safety Controls (`LiveSafetyGate`)**, erecting a non-bypassable, fail-closed safety perimeter between NexTrade's internal execution gateway (`ExecutionGateway`) and external broker adapters (`BrokerAdapter`).

---

## Architectural Separation of Concerns

```text
       STRATEGY / SIGNAL ENGINE
                   │
                   ▼
              RISK ENGINE
       (Decides Risk Compliance)
                   │
                   ▼
           EXECUTION GATEWAY
       (Phase 3 E1–E41 Boundary)
                   │
                   ▼
           LIVE SAFETY GATE (4D)
      (Decides External Authorization)
                   │
                   ▼
             BROKER ADAPTER
      (Executes Broker Operations)
```

---

## 12 Fail-Closed Safety Barriers (S1–S12)

1. **S1 (LIVE_TRADING_ENABLED)**: `LIVE` environment requires `live_trading_enabled == True`.
2. **S2 (Multi-Factor Live Unlock)**: `LIVE` environment requires valid `MultiFactorUnlock` token.
3. **S3 (Kill Switch Mode)**: Rejects all orders on `HARD_HALT`; permits `EXIT`/`CLOSE` only on `REDUCE_ONLY`.
4. **S4 (Daily Loss Limit)**: `daily_loss < max_daily_loss`.
5. **S5 (Order Notional Cap)**: `order_notional <= max_order_notional`.
6. **S6 (Position Exposure Cap)**: `projected_position_exposure <= max_position_exposure`.
7. **S7 (Active Open Orders Limit)**: `active_open_orders < max_open_orders`.
8. **S8 (Atomic Rate Limiter)**: Thread-safe `try_acquire()` token reservation.
9. **S9 (Broker Credential Verification)**: Requires `broker_credentials_status == "VALID"`.
10. **S10 (Broker Connection Health)**: Requires `broker_connection_status in ("CONNECTED", "HEALTHY")`.
11. **S11 (Audit Logger Health)**: Requires `audit_logger_status == "OK"`.
12. **S12 (Environment Permissions)**: `SHADOW` environment explicitly forbids order dispatches (`0` broker dispatches).

---

## Safety Verification Checklist

- [x] All 12 fail-closed barriers implemented and tested.
- [x] Strongly-typed `SafetyEvaluationContext` implemented.
- [x] Thread-safe atomic `SlidingWindowRateLimiter` implemented.
- [x] Multi-level safety isolation tests passed (AST scan, runtime denial, E2E integration).
- [x] Stale context snapshot rejection (>5s) verified.
- [x] Two-stage safety verification (Stage 1 pre-auth & Stage 2 JIT recheck) implemented.
- [x] Phase 3 E1–E41 production code untouched.
