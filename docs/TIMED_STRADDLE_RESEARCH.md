# Timed intraday short straddle — research backtest (V1)

**Status:** research only. Does not authorise paper/live orders.
**Code:** `research/timed_straddle/`, runner `research/run_timed_straddle_backtest.py`, tests `tests/test_timed_straddle_research.py`.
**Date:** 2026-11-22

> **Correction (2026-11-22, later the same day):** NIFTY weekly options only exist from **2019-02-11**. Runs in §3, §5
> and the first tables of §6 used rule-based weekly Thursdays for 2016–2019, i.e. contracts that did not exist.
> The calendar now uses the monthly expiry before that date (days > 7 calendar days from it are not traded).
> Re-run headline numbers with the fixed calendar: straddle base **+₹2.94 L** (1,961 days, PF 1.19, Sharpe 1.18);
> premium strangle base **+₹8.00 L** (1,940 days, PF 2.51, Sharpe 5.37). The 2016–2018 years were flat in every run,
> so conclusions are unchanged; sensitivity tables and grids were not re-run.

## 1. What is tested

A common retail intraday options-selling template:

| Rule | Default |
|---|---|
| Underlying / expiry | NIFTY, nearest weekly expiry (traded every weekday) |
| Entry | 09:20 — sell ATM CE + PE (strangle: ±`points` from ATM) |
| Per-leg stop | entry × (1 + 25%) on each short leg |
| Trail SL to cost | after one leg stops, the other leg's stop moves to its entry price |
| Wings (optional) | buy CE/PE `wing_points` beyond the shorts first |
| Position exits | optional MTM target / max loss; hard exit 15:15 |
| Size | 1 lot at today's lot size (65), every year — so years are comparable |

## 2. Method

* **Data:** Kaggle 5m NIFTY 50 / NIFTY BANK / INDIA VIX, 2015-01 → 2026-04 (regular session only).
* **Option prices are synthetic** — there is no historical *intraday* option data in the repo.
  Black-Scholes with IV = India VIX × ratio; the ratio table (by CE/PE, calendar DTE 0–7,
  moneyness in 0.5% steps) is fitted on **~70k real NSE daily option prices** (2020–2026)
  from `research/data/options/nifty_options_daily.csv`. ATM median abs error 12.9%, p90 44%.
* **Intraday theta (the critical assumption):** time-to-expiry is a blend of trading-time and
  calendar-time. Validated against 1,018 real ATM weekly straddles by predicting each day's real
  close from its real open:

  | Clock | Median bias (pred − real, % of opening straddle) |
  |---|---|
  | Calendar time | **+9.1%** (decays far too slowly → sellers look terrible) |
  | Trading time | −1.6% (decays slightly too fast → sellers look too good) |
  | **Blend 0.75 (default)** | **+0.2%** (mean −0.6%) |

* **Stops:** checked on the adverse intrabar extreme (bar high for short CE, bar low for short PE);
  fills at max(stop, price at bar open) + slippage, so gaps through stops are paid.
* **Costs:** brokerage ₹20/order, STT 0.1% on sells, NSE txn 0.03503%, SEBI, stamp, GST (Oct-2024 rates),
  plus **0.5 pt adverse slippage per leg per fill** (NIFTY default).
* **Expiries:** real NSE expiry dates 2020+ (captures the 2025 Thu→Tue switch); Thursday rule with
  holiday shift before 2020. BANKNIFTY: Thu, Wed from 2023-09-04, none after 2024-11-20.

## 3. Results — NIFTY, 2016-01 → 2026-04, 2,516 trading days, 1 lot (65)

### Base case (09:20 entry, 25% SL, trail to cost, 0.5 pt slippage)

| Metric | Value |
|---|---|
| Net P&L (after all costs) | **+₹2.98 L** (~₹119/day) |
| Costs paid | ₹2.88 L (≈ half of gross profit) |
| Win rate | 48.4% |
| Profit factor | 1.17 |
| Sharpe (daily, annualised) | 1.03 |
| Max drawdown | −₹53.7k |
| Return on ~₹2.3 L margin | ~12.6%/yr |
| Worst day | 2024-06-04 (election result) −₹8.8k |
| Both legs stopped | 44% of days |

Losing years: 2017, 2018, 2023, (2026 YTD). Best: 2021, 2024 (+₹1.05 L each).

### Sensitivity — the edge is thin

| Change | Net P&L | Sharpe |
|---|---|---|
| Theta blend 0.60 (less decay) | +₹1.53 L | 0.54 |
| **Theta blend 0.75 (base)** | **+₹2.98 L** | **1.03** |
| Theta blend 0.85 (more decay) | +₹4.22 L | 1.44 |
| Slippage 0.25 pt/leg | +₹5.06 L | 1.74 |
| **Slippage 1.0 pt/leg** | **−₹0.51 L** | **−0.18** |

**One extra half-point of slippage per fill wipes out ten years of profit.** Real SL-limit fills
on fast moves, and execution from a retail laptop app polling every few seconds, are more likely
to be ≥1 pt than 0.25 pt.

### Regime hints (base case)

| India VIX at entry | Avg P&L/day | Win rate |
|---|---|---|
| ≤ 12 | −₹4 | 43.8% |
| 12–15 | ₹97 | 48.6% |
| 15–18 | ₹109 | 48.1% |
| 18–22 | ₹190 | 50.5% |
| 22–30 | ₹316 | 51.4% |
| > 30 | ₹53 | 52.4% |

Low-VIX days earn nothing after costs; mid/high-VIX days carry the strategy. This is the
natural starting point for a regime filter (cf. ARASS hypothesis in `research/arass/`).

## 4. Limitations (read before trusting any number)

1. **Synthetic premiums.** No intraday option data. Smile dynamics, bid/ask widening in fast markets
   and IV spikes inside a 5-minute bar are not modelled; stops use VIX at bar close.
2. **Theta clock** is fitted on daily open→close only; the *shape* of decay within the day is assumed.
3. **Margin** is a rough 2026 figure (₹2.3 L naked / ₹0.9 L hedged per lot); pre-2024 margins differed.
4. **Lot size fixed at 65** for all years; historical lot sizes not replayed.
5. **In-sample:** calibration and theta blend use 2020–2026 data that the backtest also covers.
6. Results are **per 1 lot**; scaling up increases slippage.

## 5. Parameter grid (64 runs, NIFTY 2016–2026, base costs/slippage, theta blend 0.75)

Grid: entry {09:20, 09:45, 10:30, 12:00} × SL {20, 30, 40, 60}% × straddle/100-pt strangle × trail on/off.
Full table: `research/data/timed_straddle/sweep_nifty.csv`.

| Median Sharpe by… | |
|---|---|
| Entry 09:20 / 09:45 / 10:30 / 12:00 | 1.74 / 2.84 / **3.48** / 2.66 |
| SL 20 / 30 / 40 / 60 % | 1.94 / 2.66 / 2.92 / **3.08** |
| Straddle / 100-pt strangle | 2.60 / 2.79 |
| Trail to cost off / on | 2.62 / 2.69 (no real difference) |

Top: 09:45, 60% SL, 100-pt strangle, trail on — +₹8.6 L, PF 2.25, Sharpe 4.35, max DD −₹51k.
Bottom: 09:20, 20% SL, strangle — −₹1.1 L. **The common 09:20 / tight-SL template is among the weakest settings.**

**Do not take the top rows at face value.** Sharpe > 3 for ten years of daily short straddles is not
credible from real markets; it points at what the synthetic model leaves out:
* IV inside a 5-minute bar is the bar's closing VIX, so sudden IV spikes and bid/ask blow-outs
  (which are exactly what hits wide stops) are smoothed away. Wider stops look better than they are.
* Picking the best of 64 combinations adds selection bias.

What the grid *does* support, directionally: entering after the opening 15–60 minutes and
using stops wider than 20–25% helped in every slice. Treat these as hypotheses for the paper lane
(OPT-P1/P2), which records real fills and the model price side by side.


---

## 6. Premium-based short strangle with premium-matching re-entries (V1, 2026-11-22)

**Code:** `research/timed_straddle/strangle.py` (`PremiumStrangleEngine`), runner `--strategy premium_strangle`.

| Rule | Default |
|---|---|
| Strikes | CE and PE whose premium is closest to ₹40 within [₹20, ₹60], searched OTM from ATM |
| Entry / exit | 09:20 / 15:15, every weekday, nearest weekly expiry |
| Per-leg stop | entry × 1.40 (40%) |
| Re-entry ("adjustment") | when a leg stops out, re-sell that side at the strike whose premium matches the surviving leg's current premium; max 2 per day |
| Stop to cost | survivor's stop moves to its entry after the first stop |
| Optional | per-leg profit target, hedge wings at ATM ± X, MTM target / max loss |

### Model check specific to this strategy
Predicting each day's real close from its real open for **7,053 real OTM NIFTY options priced ₹20–60 at the open**
(2020–2026): median real change −31.0% vs model −28.2% (mean −1.0% vs −0.6%). By DTE the model is within a few
points except DTE 3 (real −24.7% vs model −15.7%) — i.e. the model does **not** overstate OTM decay; if anything
it is slightly conservative. Opening level: model premiums are ~6% above real, which scales P&L by ~6% but does
not create it. **Not testable with daily data:** intraday IV/skew spikes in sell-offs, which hit stops harder in
reality than in the model.

### Results — NIFTY 2016-01 → 2026-04, 1 lot (65), after costs

| Case | Net P&L | PF | Max DD | Sharpe |
|---|---|---|---|---|
| **Base (₹40, 40% SL, 2 re-entries, 0.5 pt slip)** | **+₹7.94 L** | 2.18 | −₹22k | 4.48 |
| No re-entries | +₹7.04 L | 1.90 | −₹21k | 4.11 |
| Slippage 1.0 pt / fill | +₹2.20 L | 1.23 | −₹2.02 L | 1.22 |
| Slippage 1.5 pt / fill | **−₹3.97 L** | 0.70 | −₹4.37 L | −2.15 |
| Hedge wings ATM ± 500 | −₹4.65 L | 0.65 | −₹4.73 L | −1.89 |
| Hedge wings ATM ± 1000 | +₹0.34 L | 1.03 | −₹1.28 L | 0.17 |

By year (base): flat 2016–2018 (−₹5k, ₹0, −₹1.5k), strong 2019–2025 (best 2022 +₹2.04 L), 2026 YTD +₹14k.
By DTE: expiry day carries the most (₹742/day avg); DTE 6 (day after expiry) barely positive (₹44/day).
By VIX: every bucket positive; VIX > 18 days earn 3–5× the low-VIX days.

### Reading these numbers
* **Slippage is the whole story.** Each fill on a ₹40 option costs 1–2.5% of premium per point of slippage, and the
  strategy fills 4–8 times a day. At 0.5 pt it looks excellent, at 1 pt it is ordinary, at 1.5 pt it loses.
  Real fills must be measured (options paper lane) before believing any of this.
* Sharpe 4.5 is not a real-world expectation; the missing intraday IV spikes make stops look cheaper than they are.
* Wings at a fixed ATM ± X distance can sit *inside* the premium-selected short strikes (₹40 options are often
  300–600 pts OTM), turning the hedge into a losing debit spread. A hedge, if used, should be placed relative to the
  short strike.
* Re-entries add ~₹0.9 L over ten years for ~₹1.5 L more costs — marginal.

### Parameter grid (36 runs: entry 09:20/10:00 × premium ₹20/40/70 × SL 30/50/80% × 0/2 re-entries)

All 36 combinations are profitable in the model; median Sharpe by entry 09:20 / 10:00 = 4.1 / 5.5; by SL 30 / 50 / 80% =
3.5 / 5.1 / 5.3; re-entries 0 vs 2 = 4.88 vs 4.89 (no benefit). Top row: 10:00, ₹20, 80% SL, no re-entries — Sharpe 7.6.

**A Sharpe of 7 is a model artefact, not an opportunity.** The pattern "wider stops always better" is exactly what a
model without intraday IV/skew spikes produces: stops rarely fire, and when real markets gap, the model's prices move
smoothly. The grid confirms the same direction as the straddle (later entry, wider stops) but its magnitudes cannot be
trusted. Full table: `research/data/timed_straddle/sweep_strangle_nifty.csv`.


---

## 7. Expiry-day premium strangle with premium-based hedges (V1, 2026-11-22)

Same engine (`PremiumStrangleEngine`) with `--expiry-day-only` and `--hedge-premium`. Rules as tested (NIFTY):

| Rule | Value |
|---|---|
| Days | **expiry day only** (DTE 0), from 2019-02-11 (first NIFTY weekly) |
| Entry / exit | 10:00 / 15:00 |
| Shorts | CE and PE priced closest to ₹50 (band ₹25–75) |
| Hedges | CE and PE beyond the shorts priced closest to ₹0.8, bought first |
| Per-leg stop / target | +30% / −99% of entry; a leg that exits is **not** re-entered; no stop-to-cost |
| Position exits | MTM ≥ +₹3,250 or ≤ −₹3,250 (₹1,250 per 25 qty scaled to 65), else 15:00 |

Model check: on expiry day real OTM ₹20–60 options lose a median 98.8% open→close vs model 99.7% (§6 check).

| Case (NIFTY 2019-02 → 2026-04, 355 expiry days, 1 lot of 65) | Net P&L | PF | Max DD | Sharpe |
|---|---|---|---|---|
| **Base (0.5 pt slippage)** | **+₹1.53 L** | 1.69 | −₹13.5k | 3.82 |
| Slippage 1.0 pt / fill | +₹0.89 L | 1.37 | −₹17.3k | 2.23 |
| Slippage 1.5 pt / fill | +₹0.26 L | 1.10 | −₹25.9k | 0.65 |
| No hedges | +₹2.33 L | 2.17 | −₹10.3k | 5.84 |

By year: every full year positive (2023–24 weakest at ~₹9–11k); 2026 YTD −₹1.8k. 70% win rate; avg win ₹1.5k vs avg loss ₹2.1k.

Notes:
* Fewer fills (one entry per week) make it **the most slippage-tolerant** of the three tested so far.
* The hedge costs ~₹0.8 L over seven years in the model, but the flat 0.5 pt slippage per fill overstates the
  cost of buying a ₹0.8 option (real spreads there are ~₹0.05). The hedge's value is margin: since Nov-2024 expiry-day
  naked selling carries extra ELM, and a hedged position needs a fraction of the margin.
* Expiry-day gamma is real in the data (spot moves), but sudden IV spikes inside 5-minute bars are not.

---

## 8. Automating paper trading (options paper lane)

* **Config:** `config/options_paper.json` lists strategies (`timed_straddle` or `premium_strangle`, keys mirror the
  backtest flags). Enabled by default: `timed_straddle_nifty` (09:20, 25% SL) and `expiry_strangle_nifty` (§7 rules,
  `expiry_day_only`). `premium_strangle_nifty` (daily, §6) is present but disabled.
* **Runner:** `python -m trading_app.options_paper.runner --config config/options_paper.json` — one Angel login, one
  quote poll (every 5 s, chunked at 50 tokens) for all strategies; each has its own ledger
  (`logs/options_paper/<date>_<name>_events.jsonl`, shared `summary.csv`). Never places orders.
  Expiry-only strategies skip themselves on other days; weekends and holidays (stale exchange feed) exit early.
* **Premium strangle paper V1:** shorts/hedges chosen from live quotes (shorts: ATM−3…ATM+12 strikes; hedges: 1–24
  strikes beyond the shorts); no re-entries yet.
* **Dashboard:** menu item **📊 Options Paper** (`/options`) — Start / Stop & square off, per-strategy on/off switches,
  live legs and MTM, today's events, daily results. Runs inside the dashboard process on its existing Angel connection
  (no second login). A heartbeat lock (`logs/options_paper/runner.lock`) ensures only one of dashboard / scheduled task
  runs the lane; the other refuses and the page shows where it is running.
* **One Angel login:** the dashboard owns the login. With `"auto_start": true` (switch on the Options Paper page) it
  starts the lane itself at 09:00 on weekdays (window 09:00–14:30, once per day; Stop keeps it stopped for the day), so
  equity paper trading and options paper share one session. The 09:05 scheduled task runs `run_options_paper.ps1`:
  if the dashboard is open it does nothing; otherwise it **opens the dashboard** (minimised, console to
  `logs/options_paper/dashboard_<date>.log`), which logs in once and auto-starts the lane. `-Standalone` keeps the
  old separate-process runner. The PC must be on, logged in and online until ~15:30.

---

## 9. MTM profit lock (trailing profit) — V1, 2026-11-22

**Code:** `research/timed_straddle/profit_lock.py` (`ProfitLockRule`, `ProfitLockTracker`), used by both backtest
engines (`--profit-lock trigger,lock,step,increment`) and both paper strategies (`"profit_lock": {...}` in
`config/options_paper.json`). Once position MTM reaches *trigger*, *lock* rupees are locked; every further *step*
above the trigger raises the lock by *increment*; MTM falling to the lock closes everything. The lock never moves down
and its peak survives paper-runner restarts. Backtests check it at 5-minute bar closes; the paper lane every poll.

| Strategy (1 lot) | Lock (trigger, lock, step, inc) | Net P&L | PF | Max DD | Times hit |
|---|---|---|---|---|---|
| Straddle 09:20 / 25% (2016–26) | off | +₹2.94 L | 1.19 | −₹53.7k | — |
| | 1000, 250, 500, 250 | +₹1.48 L | 1.11 | −₹53.0k | 350 |
| | 2000, 500, 500, 250 | +₹2.52 L | 1.17 | −₹57.0k | 92 |
| | 3000, 1000, 1000, 500 | +₹2.81 L | 1.18 | −₹55.3k | 25 |
| Expiry strangle (§7, 2019–26) | off | +₹1.53 L | 1.69 | −₹13.5k | — |
| | 1000, 250, 500, 250 | +₹1.54 L | 1.76 | −₹14.9k | 31 |
| | 1500, 500, 500, 250 | +₹1.58 L | 1.73 | −₹13.5k | 11 |
| | 2000, 1000, 500, 250 | +₹1.54 L | 1.70 | −₹13.5k | 5 |
| Daily premium strangle (§6) | off | +₹8.00 L | 2.51 | −₹20.5k | — |
| | 2000, 500, 500, 250 | +₹7.87 L | 2.49 | −₹20.5k | 16 |

**Verdict:** for these premium-selling strategies the lock does **not** add edge. Their profit builds into the close
(theta), so intraday give-backs usually recover; a tight lock exits good days early and halves the straddle's profit.
On the strangles it is neutral. The model smooths sudden intraday reversals — the one case a lock is designed for — so
real-market value may be somewhat higher than shown. Left **off** by default; available per strategy for paper testing
(e.g. 1500/500/500/250 on the expiry strangle is neutral-to-slightly-positive with unchanged drawdown).

---

## 10. 11:00 short straddle and hedged variants (V1, 2026-11-22)

Rules from a set of retail "Streak" templates: sell ATM CE + PE on the current weekly at **11:00**, independent per-leg
stop **40%**, no profit target, exit ~15:05; optional "hedge" = long CE/PE 9 strikes away held all day (iron fly).
BANKNIFTY template: 09:30, 35% stop. New engine flag `--keep-wings` (`sell_wing_on_stop=False`) holds hedges to the end.

| NIFTY 2016–2026 (fixed calendar), 1 lot | Net P&L | Win % | PF | Max DD | Sharpe |
|---|---|---|---|---|---|
| **11:00, 40% SL, no trail, exit 15:05** | **+₹8.73 L** | 72.3 | 2.10 | −₹28.5k | 4.36 |
| same, slippage 1.0 pt | +₹6.27 L | 68.4 | 1.72 | −₹46.3k | 3.13 |
| 11:00 + ±450 hedges kept (iron fly) | −₹2.49 L | 52.7 | 0.81 | −₹3.75 L | −1.07 |
| 09:20, 25% SL, trail (current paper config) | +₹2.94 L | 49.1 | 1.19 | −₹53.7k | 1.18 |
| 09:20, 25% SL, slippage 1.0 pt | +₹0.28 L | 46.5 | 1.02 | −₹1.01 L | 0.11 |
| *Isolation:* 09:20, 40% SL, no trail | +₹5.71 L | 69.6 | 1.40 | −₹81.4k | 2.01 |
| *Isolation:* 11:00, 25% SL, trail | +₹8.20 L | 61.3 | 1.89 | −₹36.6k | 4.09 |

* **Entry time is the main driver**: moving 09:20 → 11:00 at the same 25% stop takes +₹2.9 L to +₹8.2 L; widening the
  stop at 09:20 helps less (+₹5.7 L) and nearly doubles drawdown. Skipping the opening 1¾ hours avoids the most
  volatile part of the day while still collecting most of the day's decay.
* By year (11:00 base): every year positive except 2017 (−₹3.9k, monthly-expiry era, 67 days); 2024 best (+₹2.12 L).
  Expiry day averages ₹913/day. Positive in every VIX bucket.
* **Hedges don't pay here**: two ±450 wings cost more per day than the straddle earns on average; their real-world role
  is margin reduction, not P&L.
* **BANKNIFTY template (09:30, 35%) — not reliably testable**: −₹6.66 L (2016-05 → 2024-11), but the model prices
  BANKNIFTY options with NIFTY's VIX calibration, which underprices them; treat as unknown, not as negative.
* Same caveats as §3–§6: synthetic premiums, no intraday IV spikes, so absolute levels (Sharpe > 4) are optimistic.
  The *relative* gap vs 09:20 is large and consistent across slippage settings.

## Reproducing

```
python -m research.run_timed_straddle_backtest --symbol NIFTY --start 2016-01-01
python -m research.run_timed_straddle_backtest --symbol NIFTY --time-blend 0.6
python -m research.run_timed_straddle_backtest --symbol NIFTY --slippage 1.0
python -m research.run_timed_straddle_backtest --sweep
python -m research.run_timed_straddle_backtest --strategy premium_strangle --target-premium 40 --adjustments 2
python -m research.run_timed_straddle_backtest --strategy premium_strangle --sweep
python -m research.run_timed_straddle_backtest --strategy premium_strangle --start 2019-02-11 --expiry-day-only     --entry 10:00 --exit 15:00 --target-premium 50 --sl-pct 30 --leg-target-pct 99 --adjustments 0 --no-trail     --hedge-premium 0.8 --target 3250 --max-loss 3250
python -m pytest -p no:asyncio tests/test_timed_straddle_research.py
```
Outputs go to `research/data/timed_straddle/` (git-ignored).
