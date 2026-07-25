# NexTrade Phase 4D — Safety Invariants Specification (v1.0)

This document formally defines the **Safety Invariants (S1–S12)** enforced by the `LiveSafetyGate` perimeter engine during Sub-Phase 4D.

---

## Safety Invariant Registry (S1–S12)

| Invariant | Name | Safety Rule & Fail-Closed Criterion | Enforcement Mechanism |
| :--- | :--- | :--- | :--- |
| **S1** | **LIVE_TRADING_ENABLED Gate** | `context.environment == LIVE` requires `live_trading_enabled == True`. Defaults to `False`. | `LiveSafetyGate.authorize_dispatch` |
| **S2** | **Multi-Factor Live Unlock** | `context.environment == LIVE` requires a valid, unexpired `MultiFactorUnlock` token. | `LiveSafetyGate.authorize_dispatch` |
| **S3** | **Kill Switch & Hard Halt** | `kill_switch_mode == HARD_HALT` rejects all orders. `REDUCE_ONLY` permits `EXIT`/`CLOSE` only. | `LiveSafetyGate.authorize_dispatch` |
| **S4** | **Daily Loss Limit** | `context.daily_loss < max_daily_loss`. Exceeding or meeting cap returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S5** | **Maximum Order Notional** | `order_quantity * price <= max_order_notional`. Exceeding cap returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S6** | **Maximum Position Exposure**| `projected_position_exposure <= max_position_exposure`. Exceeding cap returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S7** | **Active Open Orders Limit** | `active_open_orders < max_open_orders`. Reaching cap returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S8** | **Atomic Rate Limiter** | Atomic `SlidingWindowRateLimiter.try_acquire()` check + reservation. Exhaustion returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S9** | **Broker Credentials Status**| `context.broker_credentials_status == VALID`. Any degraded state returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S10**| **Broker Connection Health** | `context.broker_connection_status` in `(CONNECTED, HEALTHY)`. Disconnections return `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S11**| **Audit Logger Health** | `context.audit_logger_status == OK`. Any logger corruption or outage returns `DENY`. | `LiveSafetyGate.authorize_dispatch` |
| **S12**| **Environment Permissions** | `SHADOW` environment explicitly forbids external order dispatches (`0` broker dispatches). | `LiveSafetyGate.authorize_dispatch` |

---

## Fail-Closed Rules

1. **Deny-By-Default**: If ANY barrier S1–S12 evaluates to `DENY` or `UNKNOWN`, the overall decision evaluates strictly to **`is_authorized = False`**.
2. **Stale Snapshot Rejection**: If `SafetyEvaluationContext` timestamp age exceeds `max_state_age_seconds` (default 5.0s), the context is marked stale -> evaluates to `UNKNOWN` -> **`DENY`**.
3. **Exception Safety**: Any unhandled exception during barrier evaluation yields `SafetyBarrierStatus.UNKNOWN` -> **`DENY`**.
