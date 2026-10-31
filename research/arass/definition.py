"""ARASS v1.0 strategy definition — research hypothesis + draft (not live)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from contracts.strategy_research import (
    ResearchHypothesis,
    ResearchSource,
    StrategyDefinitionDraft,
)


@dataclass(frozen=True)
class ArassParams:
    """Parameter-light defaults — intentionally not over-optimized."""

    strategy_id: str = "ARASS"
    version: str = "1.0.0"
    universe_primary: str = "NIFTY"
    universe_secondary: str = "BANKNIFTY"
    timeframe: str = "5m"

    # Calendar
    trade_weekdays: Tuple[int, ...] = (1, 2, 3)  # Tue=1 ... Thu=3 (Mon=0)
    thursday_morning_only: bool = True
    entry_start_hm: Tuple[int, int] = (10, 30)
    entry_end_hm: Tuple[int, int] = (10, 45)
    time_exit_hm: Tuple[int, int] = (15, 10)
    opening_range_end_hm: Tuple[int, int] = (10, 0)

    # Filters
    vix_min: float = 12.0
    vix_max: float = 18.0
    vwap_band_pct: float = 0.30
    # Spec text said "~equal" / ADX<20; 0.15%/20 is so tight it yields ~8 signals/decade on NIFTY.
    # Research defaults stay selective but usable; override for stricter replication.
    ema_align_pct: float = 0.40  # |EMA20-EMA50|/price * 100
    adx_max: float = 25.0
    opening_range_max_pct: float = 1.0
    gap_max_pct: float = 0.50
    trade_score_min: float = 75.0

    # Risk / exits
    max_risk_pct_capital: float = 1.0
    premium_atr_sl_mult: float = 1.5
    profit_take_1_pct: float = 50.0
    profit_take_2_pct: float = 75.0
    trail_after_pt1: bool = True
    max_losses_per_day: int = 2
    daily_loss_limit_pct: float = 2.0
    weekly_loss_limit_pct: float = 5.0
    monthly_drawdown_pause_pct: float = 10.0

    # Costs (INR / bps assumptions)
    brokerage_per_order: float = 20.0
    slippage_premium_pct: float = 0.05
    exchange_txn_bps: float = 0.53  # approx NSE F&O combined charge proxy
    stt_sell_bps: float = 6.25  # STT on sell premium (approx, research)
    gst_on_brokerage_pct: float = 18.0
    sebi_bps: float = 0.10
    stamp_duty_bps: float = 0.003  # buy-side stamp (proxy)

    # Capital / lots
    initial_capital: float = 1_000_000.0
    default_lot_size: int = 65
    strike_step: float = 50.0

    # Synthetic pricing
    risk_free_rate: float = 0.065
    use_synthetic_premiums: bool = True

    extras: Dict[str, Any] = field(default_factory=dict)


ARASS_PARAMS = ArassParams()


def build_arass_hypothesis() -> ResearchHypothesis:
    return ResearchHypothesis(
        hypothesis_id="H-ARASS-V1",
        title="AI Regime Adaptive Short Straddle (ARASS v1.0)",
        summary=(
            "Sell ATM weekly CE+PE only when regime filters indicate range-bound, "
            "moderate-VIX conditions; size by 1% capital risk; never overnight."
        ),
        source=ResearchSource.INTERNAL,
        asset_universe="NSE_INDEX_OPTIONS",
        economic_rationale=(
            "Short premium edge exists mainly in non-trending, mid-VIX regimes; "
            "avoiding high-ADX / event / large-gap sessions reduces left-tail risk."
        ),
        known_limitations=(
            "Requires quality options OHLC or clearly labeled synthetic BS premiums",
            "AI score layer is rule-based proxy until PCR/OI/breadth history is wired",
            "Event calendar must be maintained for hard avoids",
            "Research-only — not certified for paper/live",
        ),
        metadata={"family": "VOLATILITY", "structure": "SHORT_STRADDLE"},
    )


def build_arass_strategy_draft(params: ArassParams = ARASS_PARAMS) -> StrategyDefinitionDraft:
    return StrategyDefinitionDraft(
        strategy_id=params.strategy_id,
        version=params.version,
        name="AI Regime Adaptive Short Straddle",
        hypothesis_id="H-ARASS-V1",
        family="VOLATILITY",
        entry_rules_summary=(
            "Tue–Thu; entry 10:30–10:45; VIX in [12,18]; price near VWAP; "
            "EMA20≈EMA50; ADX<20; OR<1%; gap<0.5%; TradeScore>75; sell ATM CE+PE weekly"
        ),
        exit_rules_summary=(
            "SL=1.5×premium ATR; PT 50%/75% with trail; hard exit 15:10; "
            "2 losses/day or daily −2% / weekly −5% / monthly −10% pause"
        ),
        universe="NIFTY_WEEKLY_OPTIONS",
        timeframe=params.timeframe,
        data_requirements=(
            "INDEX_OHLCV_5M",
            "INDIA_VIX",
            "OPTIONS_OHLC_OR_SYNTHETIC_BS",
            "EVENT_CALENDAR",
        ),
        features=("VIX", "VWAP", "EMA20", "EMA50", "ADX", "GAP", "OPENING_RANGE", "TRADE_SCORE"),
        position_sizing_summary="lots from max risk = 1% capital vs SL distance on straddle premium",
        risk_model_summary="daily/weekly/monthly loss circuit breakers; no overnight",
        transaction_cost_model="NSE_FO_BROKERAGE_STT_GST_SEBI",
        slippage_model="PREMIUM_PCT_PER_LEG",
    )
