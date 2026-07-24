# NexTrade Risk Audit Trail Engine Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [risk/audit_logger.py](file:///d:/Back_up/NexTrade/risk/audit_logger.py)  

---

## 1. Architectural Scope & Cryptographic Integrity

`RiskAuditLogger` provides an append-only, thread-safe, tamper-evident audit logging engine that captures pre-trade `RiskDecision` objects evaluated by `RiskEngine`.

```text
               Phase 2E RiskEngine
                         │
                         │ RiskDecision
                         ▼
        ┌──────────────────────────────────┐
        │   PHASE 2F RISK AUDIT LOGGER     │ (risk/audit_logger.py)
        └────────────────┬─────────────────┘
                         │
  ┌──────────────────────┼──────────────────────┬──────────────────────┐
  ▼                      ▼                      ▼                      ▼
Unique Event ID      Monotonic Sequence    SHA-256 Hash Chain   Atomic Disk Flush
(audit_event_id)     (sequence_number)     (previous_hash)      (flush + os.fsync)
  │                      │                      │                      │
  └──────────────────────┼──────────────────────┴──────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
Authoritative JSONL Event Log      CSV Reporting Projection
(logs/audit/risk_decisions.jsonl)  (logs/audit/risk_decisions.csv)
        │
        ▼
Integrity Verifier (verify_integrity())
```

---

## 2. Key Rules & Guarantees

1. **Dual Storage Model**:
   * **JSONL (`logs/audit/risk_decisions.jsonl`)**: Authoritative, machine-parseable event log containing full nested decision traces and hash chain.
   * **CSV (`logs/audit/risk_decisions.csv`)**: Best-effort human-readable reporting projection. CSV write failures transition logger to `DEGRADED` health without invalidating authoritative JSONL records.
2. **SHA-256 Hash Chaining**:
   * Each record computes:
     $$\text{event\_hash} = \text{SHA256}(\text{canonical\_json\_payload} + \text{previous\_hash})$$
   * Genesis event uses `previous_hash = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"`.
3. **Monotonic Sequence Numbers**:
   * `sequence_number` starts at 1 and increments sequentially ($1, 2, 3...$).
4. **Crash-Safe Durability**:
   * Every write executes `f.flush()` followed by `os.fsync(f.fileno())`.
5. **Integrity Verification (`verify_integrity()`)**:
   * Verifies sequence monotonicity, hash chain continuity, genesis hash, and recomputed SHA-256 payload integrity across all logged records.

---

## 3. Data Structures & Interface ([risk/audit_logger.py](file:///d:/Back_up/NexTrade/risk/audit_logger.py))

* **`AuditEvent`**: Immutable canonical audit event payload.
* **`AuditIntegrityResult`**: Output of `verify_integrity()`.
* **`AuditHealthStatus`**: Output of `health()` (`HEALTHY`, `DEGRADED`, `FAILED`).
* **`RiskAuditLogger`**: Logger class managing append-only storage and hash chaining.
