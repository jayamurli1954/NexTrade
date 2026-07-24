# NexTrade V1 Baseline Verification Report

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Git Branch:** `main`  
**Git Commit Hash:** `0ae4326Merge pull request #2 from jayamurli1954/claude/review-trading-bot-analyzer-011CUxbcRHqnt9Ze58PJiBej`  
**Python Runtime:** Python 3.11.9  

---

## 1. System Baseline Summary

This document records the exact state of NexTrade V1 prior to commencing Phase 0 changes.

| Baseline Aspect | Status / Value | Notes |
| :--- | :--- | :--- |
| **Working Tree** | `Clean` | No uncommitted changes on `main` branch. |
| **Active Credentials** | ⚠️ **EXPOSED IN GIT** | `config.json`, `config/security.key`, `config/encrypted_credentials.dat` currently tracked in Git history. |
| **Test Suite Execution** | ❌ **FAIL (Collection Error)** | `pytest tests` fails due to `ModuleNotFoundError: No module named 'logzero'`. |
| **Missing Dependencies** | `logzero` | Imported in `capital_tracker.py`, `cumulative_trade_logger.py`, `price_provider.py` but absent from `requirements.txt`. |
| **Paper Trading System** | 🟢 **FUNCTIONAL** | `paper_trader.py` initializes successfully; manages JSON/Excel trade logs. |
| **UI Launch Status** | 🟢 **FUNCTIONAL** | PyQt5 GUI (`ui_new/main_window.py`) opens without crash. |

---

## 2. Detailed Findings & Phase 0 Roadmap

### 2.1 Git Security Audit Findings (Phase 0A Result)
* **`config.json`**: Tracked in Git since commit `19c5c559c7f09cc3152a7a7808ae7a512c1e1da0`. Contains plaintext credentials (`api_key`, `client_id`, `password`, `totp_token`).
* **`config/security.key`**: Tracked in Git since commit `fb059c59cd2c646b9d8d3cab76207be04b55bded`. Contains plaintext Fernet key.
* **`config/encrypted_credentials.dat`**: Tracked in Git since commit `fb059c59cd2c646b9d8d3cab76207be04b55bded`.
* **Action Required**:
  1. Rotate Angel One SmartAPI credentials immediately.
  2. Run `git rm --cached` on `config.json`, `config/security.key`, and `config/encrypted_credentials.dat`.
  3. Update `.gitignore` to block `*.key`, `*.dat`, `config.json`, and `.env*`.

### 2.2 Dependency & Test Suite Findings
* Add `logzero>=1.7.0` to `requirements.txt`.
* Ensure standard fallback to standard `logging` library if `logzero` is unavailable.

---

## 3. Approval & Transition Gate

With this V1 Baseline recorded, the project moves to **Phase 0A — Security Audit & Credential Consolidation**.
