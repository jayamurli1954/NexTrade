# NexTrade Phase 7P — Observation Integrity Exception OIE-001
#
# Title: Authenticated Market Data & Broker API Reliability Hardening
# ID: 7P-OBS-INTEGRITY-EXCEPTION-001 / OIE-001
# Date: 2026-07-28
# Status: AUTHORISED FOR IMPLEMENTATION
#
# ## Freeze posture
#
# The Phase 7P development freeze remains in force. This exception authorises
# work solely to correct market-data integrity defects that affect the validity
# of paper-trading observation evidence.
#
# ## Permitted under OIE-001
#
# - Authenticated Angel One WebSocket market-data integration
# - Tick-freshness validation and data-authority state machine
# - REST rate limiting / backoff and holdings/reference caching
# - Secret redaction in logs
# - Operational reliability (single WS ownership, reconnect backoff)
# - Per-fill quote provenance for observation evidence
#
# ## Forbidden under OIE-001
#
# - Strategy definitions, ML models/parameters, scoring mechanisms
# - Risk limits, execution decision logic, trading rules
#
# ## Data authority rules
#
# - WebSocket = authoritative real-time execution price
# - REST LTP = degraded reference/display fallback only (never paper fill)
# - yfinance = research/reference only (never execution or performance measurement)
#
# ## Observation clock
#
# Prior observations obtained using non-authoritative, delayed, or hard-coded
# market prices are classified as **pre-correction evidence** and shall NOT
# count toward the formal 15-trading-day observation gate.
#
# After OIE-001 verification, take a new immutable baseline snapshot and
# restart the 15-trading-day valid observation clock.
#
# ## Architecture (authoritative path)
#
#   ANGEL ONE → SmartAPI Auth → SmartWebSocketV2 → Angel Market Data Bridge
#     → Thread-Safe LTP Cache → Web UI (display) / Paper Execution (WS-fresh only)
#     → Observation Logger → Evidence Record
#
#   Angel REST (beside path): Holdings / Positions / Slow reference — rate-limited
#
