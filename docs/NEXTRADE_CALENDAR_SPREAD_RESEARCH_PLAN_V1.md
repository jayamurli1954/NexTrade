# NexTrade — NIFTY Calendar / Rollover Spread Research Plan V1

**Status:** CAL-0 **LOCKED** (2026-08-24); CAL-1 research download approved. **Not** approved for paper/live strategy wiring under Validation Phase freeze.  
**Intent:** Port a Chirag Jain–style Nifty calendar / rollover edge onto NexTrade: multi-year research backtest first, paper second.  
**Authority:** Research sandbox only until observation unfreeze + explicit user go-ahead. Does not change frozen equity paper strategies, risk, or execution.

---

## 1. Strategy thesis (to formalize)

| Rule (as described) | Research formalization needed |
|---------------------|-------------------------------|
| Calendar spreads on Nifty options | Define legs: buy farther expiry, sell nearer; CE and/or PE |
| Rollover edge ~70–80 pts/leg | Entry filter on near–far premium differential (pts or % of spot); measure vs claim |
| 3:1:1 monthly buy vs weekly sells | Structure: 3× monthly long lots vs 1+1 weekly shorts (or equivalent ratio); document lot sizing |
| Nifty zone lean | Spot “zone” (support/resistance / range) biases CE vs PE calendar or strike lean |
| Rollover gap rule | Skip or resize when gap / overnight move exceeds threshold |
| Target 2–4%/month | KPI for capital-normalized P&L after costs — not a live mandate |

### CAL-0 LOCKED defaults (2026-08-24)

User confirmed research-only go-ahead. These are **research defaults** for CAL-2; they are not live/paper mandates.

| Rule | Locked default |
|------|----------------|
| Universe | NIFTY OPTIDX only (BANKNIFTY deferred) |
| Structure **3:1:1** | **Buy 3 lots** far/monthly same-strike option; **sell 1 lot** near weekly + **sell 1 lot** next weekly (same strike, same CE or PE). Net: 3 long monthly : 1 short near : 1 short next |
| Legs | Same-strike calendar; side from zone lean (CE **or** PE per trade — not both on same entry) |
| Rollover pts band | **Amended 2026-08-25:** default differential = **far − near** in **[200, 300]** (store median ≈245; original [70,80] almost never fired). Alt mode `next_minus_near` keeps **[70, 80]** for weekly-roll hypothesis. CLI: `--diff-mode` / `--pts-band` |
| Zone lean | Zone = prior **20** session high/low range. Spot in upper third → lean **CE** calendar; lower third → lean **PE**; middle third → **no new entry**. Strike = ATM rounded to strike step, then optional ±1 step toward zone extreme (research flag) |
| Gap rule | **Skip** new entry if overnight gap `abs(open − prior_close) / prior_close ≥ 0.80%` |
| Exit (research) | Near weekly expiry / rollover window; or calendar P&L stop at **−40 pts**/lot-equivalent; or differential mean-revert below **150** (far−near) / **40** (next−near) |
| Cost model | Report V1/V2/V3 FO costs from tariff catalog (C2 policy); no silent ledger default change |
| KPI (acceptance, not mandate) | Capital-normalized research P&L target **2–4%/month** after V2 costs; document pts-band hit-rate |

**Out of scope for V1 research:** LIVE promotion, broker SPAN as authority, discretionary overrides in UI.

---

## 2. Fit on this platform

### What already exists

| Piece | Location | Relevance |
|-------|----------|-----------|
| Options OHLC store + schema | `research/arass/options_store.py` | Reuse for calendar lookups (extend beyond ATM straddle) |
| Downloader (jugaad-data) | `research/download_nifty_options.py` | Extend plan: weekly **and** monthly, multi-strike / zone |
| Research backtest protocol | `research/backtest_protocol.py`, ARASS engine | Pattern for CAL research engine (OIE-001-safe) |
| Options cost sketch | `research/arass/costs.py` + `trading_app/tariff_catalog.py` | Prefer FO statutory + brokerage profiles for research P&L |
| Strategy registry stubs | `trading_app/strategy_registry.py` | Metadata only (verticals/IC); no calendar engine |
| Paper path | equity MIS–centric; fill ≈ ₹1L notional | **Not** ready for multi-leg FO calendars |

### Freeze / governance

| Gate | Implication |
|------|-------------|
| VAL-PHASE freeze ACTIVE | No new strategy in paper/live risk/execution |
| ARASS = research precedent | CAL must stay research-only until cert package + unfreeze |
| M6 F&O margin BLOCKED | Paper FO sizing cannot claim true broker margin |
| C2 cost policy | Research reports V1/V2/V3-style cost transparency; do not silently change ledger defaults |

**Verdict:** Platform **can** host this as an **ARASS-class research workstream**. Paper trading is a **later** gate, not the next coding step.

---

## 3. Data readiness audit

### Pre-CAL-1 (2026-08-24 morning)

Source: `research/data/options/nifty_options_daily.csv` (+ manifest).

| Metric | Observed | Need for 5–6y calendar |
|--------|----------|------------------------|
| Trade dates | 2024-01-01 → 2026-07-28 (~2.5y) | ~2019/2020 → present |
| Rows | ~15.6k | Much larger (multi-strike × weekly+monthly) |
| Expiries / day | typically 1–4 | Near weekly + true monthly far |
| Max DTE / day | median ~18, **max 27**, **0 days ≥28** | Far monthly often ≥28–45 DTE |
| Near≤10 & far≥21 same strike | **192** strike-days | Dense daily coverage for both legs |
| Strike set | ATM-centric (~99 unique) | Zone lean needs OTM/ITM around zone |

**Blocker (pre-CAL-1):** Store was **insufficient**. Downloader default favored nearest weekly ATM.

### CAL-1 in progress (2026-08-24)

Command (resume-safe):

```text
python -m research.download_nifty_options --mode calendar --start 2020-01-01 --end 2026-07-31 --sleep 1.0 --strike-width-steps 4 --min-far-dte 28
```

- Source: **jugaad-data / NSE** (research path; not Angel live API).
- Target window: **2020-01-01 → 2026-07-31** (~6.5y; Excel spot available from 2015).
- Mid-run store already shows **date_min 2020-01-01**, **max_dte 45**, days with max DTE≥28 growing; ~14.2k CE/PE jobs planned.
- Log: `research/data/options/cal1_download.log`
- Coverage check: `python -m research.download_nifty_options --report-only`
- Note: recent NSE bhavcopy zip failures → Thursday calendar expiry fallback for affected weeks.

---

## 4. Workstream IDs

| ID | Item | Status | Depends on |
|----|------|--------|------------|
| CAL-0 | Formalize rules + acceptance metrics (pts edge, 3:1:1, zone, gap, cost model) | **DONE / LOCKED** (2026-08-24) | See §1 locked defaults |
| CAL-1 | Expand options store: history ≥5y, weekly+monthly, strike grid for zone | **DONE (data pass)** (2026-08-25) | Jugaad/NSE; 312,787 rows; 2020-01-01→2026-07-28 |
| CAL-2 | Research engine `research/calendar_spread/` (or sibling of ARASS): signals, fills, costs, metrics | **DONE (scaffold + CLI)** (2026-08-25) | `python -m research.run_calendar_spread_backtest`; tests `tests/test_calendar_spread_research.py`. Research-only. |
| CAL-3 | Certification package (PENDING/LIVE_ELIGIBLE=false) like ARASS | BLOCKED on CAL-2 evidence | Validation Gate |
| CAL-4 | Paper multi-leg FO adapter + risk binding | **BLOCKED** | Unfreeze + M6 + execution lane |
| CAL-5 | Live / broker FO | **BLOCKED** | CAL-4 cert + observation |

---

## 5. Proposed research design (CAL-2 sketch)

1. **Universe:** NIFTY OPTIDX only (BANKNIFTY optional later).  
2. **Legs:** Same strike calendar (CE and/or PE); ratio from CAL-0 (e.g. buy 3 monthly / sell 1+1 weekly).  
3. **Entry:** Rollover differential in [L, U] pts; zone lean selects CE vs PE / strike offset; gap rule veto.  
4. **Exit:** Near expiry / rollover window, premium target, or hard stop on calendar debit/credit.  
5. **Costs:** Round-trip FO charges from tariff catalog (options STT/exchange/GST) + optional slip (V3).  
6. **Outputs:** Trade log, monthly return distribution, drawdown, hit rate of “70–80 pts” filter, cost sensitivity.  
7. **Non-goals:** No web_dashboard strategy switch; no paper blotter until CAL-4.

---

## 6. Paper path (CAL-4) — prerequisites

- Explicit unfreeze for strategy/execution (or narrow freeze exception like TT-*).  
- Multi-leg paper orders (atomic calendar) + partial-fill policy.  
- M6 options margin (buy premium vs sell margin) — else label paper **non-certification**.  
- U1–U4 / SafetyControlPlane product gates for OPTIONS.  
- Tariff preview already exists (TT-1…T3); ledger cutover still separate.

---

## 7. Next actions (post CAL-0 lock)

1. ~~Confirm CAL-0~~ — **LOCKED** §1.  
2. ~~CAL-1 download~~ — **DONE** (2026-08-25): 312,787 rows.  
3. ~~CAL-2 scaffold~~ — **DONE** (2026-08-25): `research/calendar_spread/` + `python -m research.run_calendar_spread_backtest`.  
4. **Evidence runs:** full 2020–2026 sample.  
   - Locked v1 **[70,80]** on far−near: **not supported** (0.24% hit rate; med≈245).  
   - **Amended default:** far−near **[200,300]** (`CAL-2-V1.1`).  
   - Alt: `--diff-mode next_minus_near` keeps [70,80] on weekly roll.  
5. CAL-3 cert package only after evidence review (still PENDING / not LIVE).

---

## 8. Explicit non-goals

- Do not register a live/paper calendar strategy during freeze.  
- Do not treat external YouTube/Telegram rules as certified without CAL-0 + CAL-2 evidence.  
- Do not use equity MIS paper fill (`qty_for_scrip_allocation`) as FO lot authority.  
- Awesome Systematic / external engines are discovery only — never risk/execution authority.
