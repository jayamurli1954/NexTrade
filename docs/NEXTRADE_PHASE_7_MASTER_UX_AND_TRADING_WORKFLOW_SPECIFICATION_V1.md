# NEXTRADE PHASE 7 MASTER UX & TRADING WORKFLOW SPECIFICATION (V1.0)

```text
╔═══════════════════════════════════════════════════════════════════════════════════════════╗
║                  NEXTRADE WORKSTREAM 7 MASTER UX SPECIFICATION                            ║
║                User Experience & Intelligent Trading Workflow Architecture                ║
╠═══════════════════════════════════════════════════════════════════════════════════════════╣
║ Authority:   NEXTRADE_PHASE_7_IMPLEMENTATION_PLAN_V1.0 / PHASE_6_MASTER_PLAN_V1.0          ║
║ Objective:   Convert certified Phase 1-6 safety core into a simple, visual, user-first   ║
║              trading application (Product A) in INR (₹) currency while isolating          ║
║              the Control Plane (Product B).                                               ║
║ Principle:   Complexity Underneath. Clarity On Top.                                       ║
╚═══════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## 1. Product Architecture & Navigation Hierarchy

NexTrade explicitly separates the user experience into two distinct product surfaces, formatted in **Indian Rupees (₹)**:

### Product A: NexTrade Trader (Primary User Interface)

#### Primary Trading Navigation
1. 🏠 **Home Dashboard:** Capital Summary, Today's P&L, **Active Risk (₹)**, Risk Capacity, Engine Controls.
2. 🔎 **Opportunities:** Actionable trade cards with Signal Strength %, "Why This Trade?", Invalidation Rules, and 1-click Trade Plan population.
3. 🎟️ **Trade Ticket & Plan:** Universal Trade Plan setup, Pre-Trade Summary Modal, and protection policy binding.
4. 🧪 **Paper Simulator (4 Modes):** Manual, Assisted, Strategy-Driven, and Automated Simulation with live TSL tracking.
5. 📈 **Live Positions & Protection:** Active positions with visual SL/TP/TSL distance gauges in **₹**.
6. 💼 **Holdings & Portfolio:** Portfolio value, Cash, Utilized Margin, 10 Stock Holdings table.

#### Secondary Utility Navigation
- 👁️ **Watchlist Monitor (86+ Stocks):** Search, Add stock, Remove stock, LTP, Change, Volume.
- 📜 **Trade History:** Objective system truth record (Executions, Slippage, Exit reasons).
- 📔 **Trading Journal (7J):** Human decision reasoning, strategy win rates %, P&L breakdown by style.
- 🌅 **Pre-Market Brief:** Morning market outlook, NIFTY trend, focus stock catalysts.
- ⚙️ **Settings:** User risk preferences, default trading styles, broker connection.

### Product B: NexTrade Control Plane (Operations & Audit Console)
Accessible via Profile/Admin menu.
- Phase 6G Master Certification Status & SHA-256 Manifest Digest.
- SafetyControlPlane 8-state ladder & multi-tier kill-switch matrix.
- Multi-account isolation & zero cross-account leakage registry (`ACC_PROD_MULTI_01`..`03`).
- Tamper-evident SHA-256 hash-chained audit log stream.

---

## 2. Phase 7 UX Safety Invariants (U1, U2, U3, U4)

To ensure that the user interface never compromises the certified Phase 1–6 safety core, Phase 7 enforces four mandatory architectural invariants:

> [!IMPORTANT]
> **Invariant U1 — UI Safety Boundary:**
> No user interface component or user action may bypass the certified Risk Engine, Authorization Gate, Execution Gateway, Protection Lifecycle, or Reconciliation Chain. All UI requests must pass through `SafetyControlPlane`.

> [!IMPORTANT]
> **Invariant U2 — Versioned Protection Policy Binding:**
> Every active Trade Plan (Paper or Live) MUST have a persisted, immutable-at-activation Protection Policy containing at minimum: Stop Loss, Target, Trailing Stop Loss, Auto-Exit rules, Activation timestamp, and Trade Plan ID.

> [!IMPORTANT]
> **Invariant U3 — Paper/Live Behavioural Parity:**
> Paper Trading and Live Trading must utilize the exact same Trade Plan, Risk Engine, Protection Lifecycle, Trailing Stop, and Auto-Exit state machines. The only permitted difference is the execution adapter destination (Paper Simulation Engine vs Live Broker Gateway).

> [!IMPORTANT]
> **Invariant U4 — User Intent Integrity:**
> No UI transformation, default value, strategy recommendation, or automated workflow may alter a user's explicitly confirmed Trade Plan parameters without creating a new versioned Trade Plan requiring explicit re-validation.

---

## 3. Universal Trade Plan Schema (INR ₹)

```json
{
  "trade_plan_id": "tp_20260726_001",
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "currency": "INR (₹)",
  "instrument_type": "EQUITY",
  "trading_style": "INTRADAY",
  "strategy": "MOMENTUM_BREAKOUT",
  "direction": "BUY",
  "entry_price": 2742.00,
  "quantity": 10,
  "capital_required": 27420.00,
  "stop_loss_price": 2690.00,
  "target_price": 2850.00,
  "trailing_stop": {
    "enabled": true,
    "trail_amount": 20.00,
    "current_trigger_price": 2745.00
  },
  "auto_exit": {
    "exit_on_stop_loss": true,
    "exit_on_target": true,
    "exit_on_trailing_stop": true,
    "exit_on_market_close": true
  },
  "risk_metrics": {
    "max_loss_amount": 520.00,
    "potential_profit_amount": 1080.00,
    "risk_reward_ratio": 2.08,
    "signal_confidence_pct": 87.0
  },
  "execution_mode": "PAPER_TRADING"
}
```

---

## 4. Signal Strength & Transparency Policy

Signal confidence is explicitly presented as **Signal Strength %** (e.g. 87%), broken down into 5 factors:
- **Trend Alignment:** 95%
- **Momentum Strength:** 88%
- **Volume Surge:** 94%
- **VWAP Confirmation:** 90%
- **Risk Assessment:** 78%

> [!NOTE]
> **Regulatory & Safety Disclaimer:**
> `Signal Strength ≠ Probability of Profit`. Signal strength measures technical alignment with strategy rules.
