# NexTrade Phase 4N — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4N serves as the definitive **bridge between NexTrade's 4A–4M Safety Engine and the User Trading Experience**. It establishes a versioned **Broker & Exchange Rule Registry**, a **Dynamic Capability Resolver** (intersecting NexTrade ∩ Broker ∩ Exchange ∩ Risk ∩ Safety), a **Secret Sanitizer** (protecting HMAC keys and credentials), a **Production Activation Manager** (enforcing explicit human production authorization), a **Trade Type Template Engine**, a **Safety-Aware Smart Trade Ticket**, a live **Safety Centre**, a two-level **Safety Passport**, an **Explanatory Rejection Engine**, and an independent **Platform Governance Certificate** prior to Phase 5 Production Release (v4.4 release milestone).

---

## Master Safety Invariants (4N-P1 — 4N-P8)

```text
4N-P1  Capability Truth & Rule Currency (Sourced dynamically from versioned broker/exchange registry)
4N-P2  Production Activation Pending Human Authorization (Activation strictly requires explicit human authorization)
4N-P3  Security & Secret Isolation (0 HMAC keys, tokens, credentials, or internal addresses exposed in UI)
4N-P4  Broker-Aware Capability Registry (Capability matrix dynamically resolves against active broker adapter)
4N-P5  Trade Type Templates & Guidance (CNC, MIS, MTF, Futures, Options templates provided safely)
4N-P6  Governance Evidence Package (Every governance action produces signed SHA-256 evidence package)
4N-P7  UI Consumer Authority Invariant (UI is a consumer of safety decisions; UI cannot bypass safety gates)
4N-P8  Dynamic Capability Intersection (Tradability = NexTrade ∩ Broker ∩ Exchange ∩ Risk ∩ Safety)
```

---

## Architecture Diagram

```text
                        NEXTRADE USER
                             │
                             ▼
                ┌─────────────────────────┐
                │  USER TRADING WORKSPACE │
                │                         │
                │ • Market / Instrument   │
                │ • Trade Type            │
                │ • Order Type            │
                │ • Quantity / Price      │
                │ • Risk Preview          │
                │ • Margin Preview        │
                │ • Safety Status         │
                │ • Human Confirmation    │
                └────────────┬────────────┘
                             │
                             ▼
                ┌─────────────────────────┐
                │ CAPABILITY RESOLVER     │
                │ (Dynamic Intersection)  │
                └────────────┬────────────┘
                             │
                             ▼
                ┌─────────────────────────┐
                │ TRADE TEMPLATE ENGINE   │
                │ (CNC, MIS, MTF, F&O)    │
                └────────────┬────────────┘
                             │
                             ▼
             ┌──────────────────────────────┐
             │      4A – 4M SAFETY STACK    │
             │                              │
             │ Risk → Safety → Authorization│
             │ → Staging → Pilot → Resilience│
             │ → User Safety                │
             └──────────────┬───────────────┘
                            │
                            ▼
                      BROKER ADAPTER
```

---

## Safety & Governance Verification Checklist

- [x] All 9 Sub-Phase 4N unit and integration tests passed.
- [x] `RuleRegistryStore` retrieves versioned broker capability and exchange rules.
- [x] `CapabilityResolver` computes 5-way dynamic tradability intersection.
- [x] `ProductionActivationManager` requires explicit operator signature for activation.
- [x] `SecretSanitizer` strips HMAC secret keys and tokens from text and dictionary outputs.
- [x] `TradeTemplateEngine` manages safe trade type templates.
- [x] `PlatformGovernanceAuditor` consolidates 4A–4N certificates into signed `PlatformGovernanceCertificate`.
- [x] AST scan confirms 0 UI safety bypass calls and 0 broker SDK imports in `governance/` package.
