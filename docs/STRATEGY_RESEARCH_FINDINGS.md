# Strategy research findings — paper-trade review & edge validation

_Date: 2026-10-31 · Branch: `feat/dashboard-angel-live-data`_

This note records a review of one month of paper trading and the research that
followed. The short version: **the trading signal has no demonstrated edge, and
a cross-sectional factor alternative that looked promising in-sample failed
out-of-sample.** The only change committed is a set of risk guardrails that stop
the strategy from bleeding money on costs. No alpha engine was validated; do not
risk capital on the current signal.

All analysis scripts referenced below were run against the repo's own data
(`research/data/feature_store/ohlc_cache/*.csv` daily, 87 symbols 2024–2026, and
`research/data/intraday/kaggle_nifty100_5m/*` 5-minute bars).

---

## 1. The paper-trade month (log: 139 trades, 28 Jul – 6 Oct 2026)

| Metric | Value |
|---|---|
| Gross P&L | −₹5,952 (near break-even) |
| Est. charges | −₹24,332 |
| **Net P&L** | **−₹30,284** |
| Win rate | 38.8% gross / 30.9% net |
| Avg win : avg loss | ₹561 : ₹497 (R:R 1.13) |

Three root causes:

1. **Costs dominate.** Trading charges were ~4× the gross loss. Even break-even
   signals lose ~₹24k to fees over 139 trades. The cost model
   (`trading_app/broker_charges.py`) is realistic (~0.19% round-trip), so the
   losses are real, not a bug.
2. **Overtrading, concentrated.** `Golden Ratio Scan` was 94 of 139 trades and
   −₹22,462 net. **6 symbols = 63% of trades and 75% of the loss**; GAIL alone
   was traded 28 times (−₹7,658) — the scanner re-bought the same falling names
   daily.
3. **No reward/risk edge.** 39% win rate at 1.13 R:R loses even before costs.
   Stops hit 24× vs targets 11×; 54 trades expired flat at the 15:15 square-off.

## 2. The Golden Ratio signal has no edge (three independent proofs)

- **Excursion study (197 signals).** After entry, EOD direction was correct only
  **52%** of the time; mean move +0.06% (below the 0.19% cost); median favorable
  excursion (0.49 ATR) ≈ median adverse (0.47 ATR). It is a random walk.
- **Target unreachable intraday.** Stops/targets are scaled to the *daily* ATR
  but held for one session. A 1.5-ATR target is reached intraday only **6%** of
  the time — the mechanical reason targets never fill.
- **Horizon test.** Holding 3/5/10 days makes targets fill more, but losses
  grow (stop-hit 45%→62%), proving the signal is slightly *adverse*, not merely
  edgeless.

## 3. Feature research — do any predictors actually work?

Cross-sectional Information Coefficient (Spearman rank corr vs forward returns),
50,276 rows, 87 symbols. Real but modest edges exist **only at 5–10 day
horizons**, never intraday (best 1-day feature: t≈2.5, IC 0.019):

| Feature (fwd-10d) | Mean IC | t-stat |
|---|---|---|
| turnover expansion (`dollarvol_tr`) | +0.040 | +6.2 |
| 1-month reversal | −0.032 | −4.2 |
| 3-month reversal | −0.034 | −3.5 |
| 12-1 momentum | +0.032 | +3.2 |
| 5-day reversal | +0.021 | +2.8 |

## 4. Portfolio backtest — biweekly ranked basket

A 10-day-rebalanced top-10 long basket on a turnover + reversal + momentum
composite beat the equal-weight universe by **+3.3%/yr net** of delivery costs
in-sample (Sharpe 0.63 vs 0.59). Weekly rebalancing destroyed the edge (12%/yr
cost drag); monthly was too slow (short-term reversal decays).

## 5. Out-of-sample validation — the edge does NOT survive

Weights learned on 2024–mid-2025, frozen, tested on held-out 2025-07 → 2026-08:

| | Annualized | Sharpe | Max DD | vs universe |
|---|---|---|---|---|
| Train (in-sample) | +83.1% | 2.27 | 0% | +74.9% |
| **Test (out-of-sample)** | **−0.7%** | 0.04 | −17.3% | **−3.1%** |
| Test + regime filter | −6.3% | −0.38 | −14.7% | −8.7% |
| Test universe (buy & hold) | +2.4% | 0.27 | −10.1% | — |

The in-sample Sharpe of 2.27 is a textbook overfit artifact; learned weights
were unstable across sub-periods (the strongest full-sample feature collapsed in
the train split); and out-of-sample the basket **underperformed buy-and-hold**
across every N and cost assumption. The +3.3% was in-sample luck.

## 6. Conclusions & recommendations

1. **Keep the guardrails** (commit `60ff8fa`): require a real Fib level + trend
   agreement + a cost-clearing target in `analyzer/enhanced_analyzer.py`;
   tighter gates and intraday-realistic targets in `analyzer_config.json`; and a
   per-symbol concentration guard in `trading_app/opportunity_scanner.py`. These
   are sound risk control.
2. **Do not treat NexTrade's signal engine as an alpha source.** No edge was
   demonstrated; the factor tilt failed out-of-sample. Nothing was wired into
   the app, by design.
3. **Stop parameter-hunting** — the research shows no edge hiding behind better
   thresholds.
4. If pursuing systematic trading further, change the *inputs* (10+ years of
   history, a larger universe, data beyond price such as fundamentals/earnings
   revisions), and always hold ideas to the train/test/out-of-sample discipline
   used here before anything goes live.

## Reproducing

Research scripts (kept outside the repo, in the session scratchpad):
`feature_ic.py`, `edge_study.py`, `backtest_validate.py`, `portfolio_bt.py`,
`oos_validate.py`. Each drives the repo's real analyzer and cost model against
the cached OHLC data.
