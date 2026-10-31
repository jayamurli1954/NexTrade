# Strategy research findings — paper-trade review & edge validation

_Date: 2026-10-31 · Branch: `feat/dashboard-angel-live-data`_

This note records a review of one month of paper trading and the research that
followed. The short version: **the intraday signal has no edge; price-based
factors are genuinely real over a decade but can only be captured long-short,
which a retail cash account can't practically do; and a long-only factor basket
loses to simply holding the universe.** The only change committed is a set of
risk guardrails that stop the strategy from bleeding money on costs. No alpha
engine was validated for a long-only setup; do not risk capital on the current
signal.

Analysis used two datasets: the repo's own cache (`ohlc_cache/*.csv` daily, 87
symbols 2024–2026; `kaggle_nifty100_5m/*` 5-minute bars) for the intraday work,
and a **10–16 year daily history (99 symbols, 2010–2026)** pulled via yfinance
(NSE `.NS`) for the factor validation in sections 3–5.

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

## 3. Feature research — which predictors actually work (decade data)

Cross-sectional Information Coefficient (Spearman rank corr vs forward returns),
**362,735 rows, 99 symbols, 2010–2026**. Real edges exist at the 5–10 day
horizon, never intraday (best 1-day feature t≈8 but IC ~0.02 — too small to
beat cost). The decade is decisive about which are genuine:

| Feature (fwd-5d) | Mean IC | t-stat | Verdict |
|---|---|---|---|
| 5-day reversal (`rev_5d`) | +0.032 | +12.0 | **robust** |
| 12-1 momentum (`mom_12_1`) | +0.032 | +9.1 | **robust** |
| 1-day reversal (`rev_1d`) | +0.022 | +8.8 | robust |
| dist from SMA20 | −0.023 | −8.3 | **robust** (mean reversion) |
| Bollinger %b | −0.021 | −8.1 | robust (mean reversion) |
| RSI-14 | −0.014 | −5.4 | robust |
| turnover expansion (`dollarvol_tr`) | −0.003 | −1.4 | **FAKE** — a 2-year artifact |
| 3-month momentum | +0.002 | +0.7 | fake |

Lesson: on the thin 2024–26 window `dollarvol_tr` looked like the strongest
signal (t=+6.2); over a decade it is noise. Long history is what separates a
real factor from a short-window fluke.

## 4. Portfolio backtest — biweekly ranked basket

A 10-day-rebalanced top-10 long basket on the robust composite (reversal +
momentum + mean-reversion) is the right *horizon*: weekly rebalancing is
destroyed by ~12%/yr cost drag, monthly is too slow (short-term reversal
decays). But horizon alone does not create net return — see section 5.

## 5. Out-of-sample validation — real factors, but long-only still loses

Composite built from the decade-robust factors (`rev_5d` + `mom_12_1` +
`dist_sma20`), weights learned on **2010–2019**, frozen, tested on unseen
**2020–2026**:

| | Annualized | Sharpe | Max DD | vs universe |
|---|---|---|---|---|
| Train (in-sample) | +28.4% | 1.24 | −23.6% | +11.7% |
| **Test (out-of-sample)** | **+24.2%** | 0.94 | −42.9% | **−2.9%** |
| Test + regime filter | +12.9% | 0.64 | −38.5% | −14.2% |
| **Test universe (buy & hold)** | **+27.1%** | **1.33** | **−33.9%** | — |

This time the weights were stable and the in-sample result sane (no overfit
blow-up), so the factors are genuinely real. **Yet the long-only basket still
underperformed simply holding the universe** — by ~3%/yr and with a worse
drawdown (−43% vs −34%) — across every N and cost assumption. The regime filter
made it worse (it sat out the 2020–21 recovery).

Why: the factors' predictive power is **cross-sectional/relative** ("top-ranked
beats bottom-ranked") — a *long-short* statement. A long-only basket can't
separate that thin relative edge from market beta, so it ends up holding
higher-beta names that fall harder in crashes. Capturing the alpha requires
also shorting the bottom-ranked names (market-neutral), which for Indian retail
means single-stock futures or stock lending — not practical in a cash account.

## 6. Conclusions & recommendations

1. **Keep the guardrails** (commit `60ff8fa`): real Fib level + trend agreement
   + cost-clearing target in `analyzer/enhanced_analyzer.py`; tighter gates and
   intraday-realistic targets in `analyzer_config.json`; per-symbol
   concentration guard in `trading_app/opportunity_scanner.py`. Sound risk
   control.
2. **Abandon intraday** — no edge at the 1-day horizon, and the most cost.
3. **Do not port the Golden Ratio signal to a slower clock** — it has no edge at
   any horizon.
4. **For a long-only retail setup, a broad low-cost hold of the universe/index
   is the honest benchmark and is hard to beat after costs** — the decade proves
   it beat the best validated active strategy on both return and drawdown. The
   defensible path is low-cost broad exposure as the core, optionally with a
   *modest* factor tilt (slightly overweight reversal/momentum-ranked names),
   treating NexTrade as a disciplined execution/risk tool, not an alpha engine.
5. If ever pursuing the factor alpha properly: it requires a **long-short /
   market-neutral** book (long top decile, short bottom decile) and shorting
   capability, plus data beyond price (fundamentals, earnings revisions) — always
   held to the train/test/out-of-sample discipline used here.

## Reproducing

Research scripts (kept outside the repo, in the session scratchpad):
`feature_ic.py`, `edge_study.py`, `backtest_validate.py`, `portfolio_bt.py`,
`oos_validate.py`, plus `fetch_history.py` (pulls the 10–16 year yfinance
daily history into `hist_cache/`). Each drives the repo's real analyzer and
cost model against the cached OHLC data.
