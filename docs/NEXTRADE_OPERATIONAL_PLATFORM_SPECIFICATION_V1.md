# NexTrade Operational Platform Specification (v1.0)

## Executive Summary

This document specifies the operational platform architecture, governance framework, trading product capability models, safety explanation mechanics, and user transparency controls for the **NexTrade Algorithmic Trading Platform**.

---

## 1. Supported Market Segments & Trading Products

NexTrade supports multi-segment market access and trading products resolved dynamically against broker capability records:

| Segment | Product | Product Name | Margin Model | Typical Horizon | Status |
| --- | --- | --- | --- | --- | --- |
| Equity | CNC_DELIVERY | Cash & Carry Delivery | 100% Upfront Cash | Long-term investment | 🟢 Enabled |
| Equity | MIS_INTRADAY | Intraday Square-Off | 15% SPAN + 5% Exposure | Same-day session | 🟢 Enabled |
| Equity | MTF_MARGIN | Margin Trading Facility | ~25% Upfront Margin | Leveraged delivery | 🟢 Enabled |
| Derivatives (F&O) | MIS_INTRADAY | Futures & Options Intraday | SPAN + Exposure Margin | Contract expiry | 🟢 Enabled |
| Commodities | MIS_INTRADAY | Commodity Futures | SPAN + Exposure Margin | Session / Expiry | 🟡 Roadmap (Phase 5) |

---

## 2. Supported Order Types & Execution Variations

NexTrade enforces precision order execution variations validated against segment and product capability matrices:

* **Market Order**: Immediate execution at prevailing market price.
* **Limit Order**: Execution restricted to specified target limit price or better.
* **Stop Loss (SL)**: Triggers limit order upon market breaching defined stop price.
* **Stop Loss Market (SL-M)**: Triggers market order upon breaching stop price.
* **Immediate or Cancel (IOC)**: Instant partial or full execution; unfilled balance canceled.
* **After Market Order (AMO)**: Queued order for market open execution.
* **Good Till Triggered (GTT)**: Long-term limit order triggered on target price hit.

---

## 3. Dynamic Capability Resolver Architecture

NexTrade enforces a 5-way tradability intersection:

```text
Tradable Capability = NexTrade Matrix ∩ Broker Capabilities ∩ Exchange Rules ∩ Risk Limits ∩ Safety Gate Status
```

If any condition fails, the order is rejected at the ticket level with a deterministic explanation.

---

## 4. User Safety & Security Isolation (Invariants 4N-P1 — 4N-P8)

- **4N-P1**: Capability truth derived dynamically from versioned broker/exchange rule registry.
- **4N-P2**: Production activation strictly requires explicit human operator signature (`ProductionActivationManager`).
- **4N-P3**: Zero HMAC secret keys, tokens, or credentials exposed to UI screens (`SecretSanitizer`).
- **4N-P7**: UI is a consumer of safety decisions; UI cannot bypass backend safety gates (S1–S12, StagingGate).
- **4N-P8**: Every visible capability is dynamically derived from 5-way capability intersection.
