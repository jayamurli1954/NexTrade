# NexTrade — Validation & Observation Operating Charter V1

**Status:** ACTIVE (feature freeze locked)  
**Effective:** 2026-08-04  
**Principle:** Engineering discipline > engineering speed. Evidence > features.

---

## 0. Official phase

The project has entered **Validation & Observation**.

| Area | Score (2026-08-04) | Status |
|------|-------------------|--------|
| Research Platform | **94–95%** | Production-grade for research |
| Validation & Evidence | **45–50%** | Operational; remaining gap = time + ops evidence |
| Execution Platform | **63–65%** | Intentionally deferred / frozen |
| Live Trading Readiness | **Blocked** | Correctly blocked |

ARASS certification remaining **PENDING** (poor backtest metrics) is a **governance success**, not a failure — the framework can say “not yet.”

---

## 1. What is frozen

No net-new product work until explicit unfreeze:

- FI-3 Research Center UI  
- MDW OI / PCR  
- Margin / Capital Allocation / Portfolio Risk expansion  
- BUY/SELL gate or confidence changes  
- LIVE or paper promotion of ARASS / uncertified strategies  

**Allowed:** validation suite runs, paper observation, bug fixes, documentation of evidence, certification updates when evidence changes.

---

## 2. Cadence (next weeks / month)

### Daily
- Run validation when changing code: `python -m research.run_validation_phase` (or DVE alone)
- Continue paper observation / fill integrity hygiene
- Fix defects only (classified — see §3)

### Weekly
Generate / archive:
- Validation report (`validation_phase_latest.*`)
- Certification / checklist status
- Known issues snapshot (`known_gaps.json`)

### Monthly
Review:
- Strategy performance (research + paper)
- Platform stability
- Data quality
- Readiness to unfreeze (only if evidence supports)

### Milestone (when evidence warrants)
Tag:

```text
NexTrade Research Platform v1.0
```

That milestone beats “another sprint completed.”

---

## 3. Bug severity (required classification)

Every defect found during observation:

| Severity | Example | Action |
|----------|---------|--------|
| **Critical** | Wrong calculations / look-ahead / fill integrity break | Fix immediately; re-run full validation |
| **High** | Feature Store inconsistency / validation false PASS | Fix this week; re-run affected tracks |
| **Medium** | UI / display issues (non-gate) | Schedule; no freeze violation |
| **Low** | Cosmetic | Backlog |

Do **not** add unrelated features while fixing.

---

## 4. Component versioning (formal)

Use these labels in manifests and certification `evidence_refs`:

| Component | Version (baseline) |
|-----------|-------------------|
| Research Platform | **v1.0** (candidate — tag after sustained observation) |
| Feature Store | **v1.0** |
| Fundamental Engine | **v1.1** (FI-1/FI-2) |
| Research Query Engine | **v1.0** |
| Validation Pack | **v1.0** |

Certification packages must record feature / platform versions used.

---

## 5. Unfreeze order (later — not now)

1. Execution Platform (Capital → Margin → Risk → Order Lifecycle → Monitoring → Audit)  
2. Market data enrichment (OI / PCR) if still needed for research  
3. InvestMitra IM-V1 (Research Service consumer)  
4. FI-3 UI and presentation features  

---

## 6. Success metric for this phase

Not: features shipped.  
Yes: **evidence that the platform behaves correctly, consistently, and honestly** (including REJECT / PENDING when data says so).

---

## 7. Commands

```bash
python -m research.run_data_validation
python -m research.run_validation_phase
python -m research.certify_arass   # refresh package only when evidence changes
```

Artifacts: `research/data/validation/`

---

## Change log

| Date | Change |
|------|--------|
| 2026-08-04 | Charter created from Validation & Observation sign-off note |
