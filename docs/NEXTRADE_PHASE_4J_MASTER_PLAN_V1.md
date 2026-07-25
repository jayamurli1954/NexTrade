# NexTrade Phase 4J — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4J constructs NexTrade's **Controlled Live Staging Subsystem**, establishing an explicitly authorized, cryptographically bound, fail-closed execution perimeter that enables real-market broker dispatches under strict exposure bounds prior to production hardening (v4.0 milestone).

---

## Master Safety Invariants (4J-P1 — 4J-P12)

```text
4J-P1  Multi-Certificate & Human Intent Authorization Chain (4H + 4I + Git + Config + HMAC)
4J-P2  Bounded Controlled Live Environment Limits (Qty <= 10, Notional <= $1,000, Symbol Allowlist)
4J-P3  Independent Emergency Kill Switch (Forces HARD_HALT or REDUCE_ONLY)
4J-P4  Zero Automatic Escalation to Unrestricted Live
4J-P5  Immutable Order Lineage (Signal -> Risk -> Request -> Gate -> Staging -> Broker -> Recon)
4J-P6  Cryptographic Binding of Configuration & Allowlist Hashes
4J-P7  Finite Authorization Expiry (Expired tokens evaluate to DISPATCH_DENIED)
4J-P8  Configuration Immutability (Runtime edits invalidate token)
4J-P9  Broker Endpoint Identity Binding (Rejects account / port mismatch)
4J-P10 Process Restart Fail-Closed Safety (Restart resets environment to SAFE/DISABLED)
4J-P11 Fail-Closed on State Uncertainty (Network timeouts lock dispatches to REDUCE_ONLY)
4J-P12 Dominant Kill Switch Hierarchy (KILL_SWITCH > HARD_HALT > RECONCILIATION > BREAKER)
```

---

## Architecture Diagram

```text
             AUTHORIZATION & CERTIFICATE INPUTS
┌─────────────────────────────────────────────────────────────┐
│ 4H PROMOTE Certificate  (storage/promotion_decision.db)     │
│ 4I READY Certificate    (storage/readiness_audit.db)        │
│ HMAC Cryptographic Key  (STAGING_AUTHORIZATION_KEY)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                   StagingAuthorizer (4J-2)
        (Validates 4H+4I, Config Hash, Expiry, Broker Binding)
                               │
                               ▼
                   StagingGate Engine (4J-3)
┌─────────────────────────────────────────────────────────────┐
│ LiveSafetyGate S1–S12 Enforcer (4D)                         │
│ Bounded Exposure & Notional Limits (4J-P2)                  │
│ Allowlisted Symbol Enforcer (["AAPL", "MSFT"])              │
│ CircuitBreakerManager (4J-4) -> Kill Switch Dominance        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                   ┌───────────┴───────────┐
                   ▼                       ▼
         AUTHORIZED DISPATCH              DENIED / HALT
          ExecutionGateway           (HARD_HALT / REDUCE_ONLY)
                   │
                   ▼
         BrokerAdapter (IBKR)
                   │
                   ▼
     Order Lineage & Dual Store
(SQLite DB + JSONL Diagnostic Log)
```

---

## Safety & Staging Verification Checklist

- [x] All 13 Sub-Phase 4J unit and integration tests passed.
- [x] Multi-certificate & human intent authorization (4H + 4I + HMAC + human_authorization_id) verified.
- [x] Configuration hash immutability & tampering rejection verified.
- [x] Symbol allowlist (`["AAPL", "MSFT"]`), order quantity (<= 10), and notional (<= $1,000) bounds enforced.
- [x] Emergency kill switch dominance over all authorities verified.
- [x] Process restart fail-closed safety (resets environment to SAFE/DISABLED) verified.
- [x] AST scan confirms 0 unauthorized escalation calls in `staging/` package.
- [x] AST scan confirms 0 broker SDK imports (`ibapi`, `ib_insync`, etc.) in `staging/` package.
- [x] Dual persistence in SQLite (`controlled_live_staging.db`) and JSONL (`controlled_live_staging.jsonl`) verified.
