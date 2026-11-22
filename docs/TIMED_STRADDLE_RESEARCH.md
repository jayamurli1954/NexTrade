# Timed intraday short straddle — research backtest (V1)

**Status:** research only. Does not authorise paper/live orders.
**Code:** `research/timed_straddle/`, runner `research/run_timed_straddle_backtest.py`, tests `tests/test_timed_straddle_research.py`.
**Date:** 2026-11-22

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

## Reproducing

```
python -m research.run_timed_straddle_backtest --symbol NIFTY --start 2016-01-01
python -m research.run_timed_straddle_backtest --symbol NIFTY --time-blend 0.6
python -m research.run_timed_straddle_backtest --symbol NIFTY --slippage 1.0
python -m research.run_timed_straddle_backtest --sweep
python -m pytest -p no:asyncio tests/test_timed_straddle_research.py
```
Outputs go to `research/data/timed_straddle/` (git-ignored).
