# NexTrade Phase 4M — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4M consolidates NexTrade's **4A–4L Safety & Resilience Architecture** into a transparent, user-facing **Production Readiness & User Safety Framework**. It establishes a trading capability product model (Equity, F&O, Commodities / CNC, MIS, MTF / Market, Limit, SL, SL-M, GTT), a live **Safety Centre**, an **Explanatory Rejection & Hold Engine**, a **Smart Trade Ticket with Pre-Trade Risk Preview**, a two-level **Safety Passport**, and an independent **Production Readiness Certificate** prior to production authorization (v4.3 release milestone).

---

## Master Safety Invariants (4M-P1 — 4M-P9)

```text
4M-P1  User Transparency Without Safety Bypass (UI presents safety controls, NEVER bypasses S1–S12/StagingGate)
4M-P2  Trading Product & Order Type Matrix Enforcement (Segment/product/order type validated against matrix)
4M-P3  Explanatory Rejection & Hold Engine (Denied/held orders produce clear user-readable explanations)
4M-P4  Safety Centre & Operational Transparency (Real-time display of active environment, 12 barriers, token expiry)
4M-P5  Pre-Trade Risk & Margin Preview (Trade ticket calculates SPAN + Exposure margin & safety checks)
4M-P6  Independent Production Readiness Certificate (100% pass on 4A–4L evidence packages)
4M-P7  Explainability of Safety Decisions (Deterministic explanation identifying blocking/holding reasons)
4M-P8  Safety State Transparency (UI accurately represents backend safety state)
4M-P9  Capability Truthfulness (UI advertises only enabled and supported broker capabilities)
```

---

## Architecture Diagram

```text
┌──────────────────────────────────────────────────────────┐
│                    NEXTRADE USER LAYER                   │
│                                                          │
│  Smart Trade Ticket (4M-5)                               │
│  • Segment: Equity / F&O / Commodities                   │
│  • Product: CNC / MIS / MTF                              │
│  • Order Type: Market / Limit / SL / SL-M / GTT          │
│  • Pre-Trade Risk & Margin Preview (4M-4)                │
│                                                          │
│  Safety Centre (4M-3) & Safety Passport (4M-7)          │
│  • Active Environment & Token Expiry                     │
│  • 12 Protection Layers Status                           │
│  • 4A–4L Certification Evidence Dashboard                 │
│  • Position Reconciliation State                         │
│  • Explanatory Rejection Engine (4M-2)                   │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                 NEXTRADE SAFETY & CONTROL                │
│                                                          │
│  4A–4L Safety & Resilience Architecture                  │
│  LiveSafetyGate S1–S12                                  │
│  RiskEngine & StagingGate                                │
│  IncidentManager & DisconnectHandler                     │
│  IdempotencyGuard & PositionReconciler                   │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│               PRODUCTION READINESS AUDIT                 │
│                                                          │
│  ProductionReadinessAuditor (4M-8)                       │
│  • Validates 4H + 4I + 4J + 4K + 4L Evidence Certificates│
│  • Issues ProductionReadinessCertificate (v4.3 Tag)     │
└──────────────────────────────────────────────────────────┘
```

---

## Safety & Governance Verification Checklist

- [x] All 9 Sub-Phase 4M unit and integration tests passed.
- [x] `TradingProductMatrix` validates capability matrix and rejects unsupported combinations.
- [x] `SafetyExplainer` translates technical barrier denials into actionable user explanations.
- [x] `SafetyCentre` generates transparent `SafetyCentreSnapshot` displaying 12 active barriers and token expiry.
- [x] `RiskPreviewCalculator` computes SPAN + Exposure margin estimates and pre-trade safety checks.
- [x] `TradeTicket` prepares order previews and rejects invalid capability requests.
- [x] `SafetyPassport` generates Level 1 user protections and Level 2 4A–4L evidence stack.
- [x] `ProductionReadinessAuditor` consolidates 4A–4M certificates into signed `ProductionReadinessCertificate`.
- [x] AST scan confirms 0 UI safety bypass calls and 0 broker SDK imports in `ui_new/` package.
