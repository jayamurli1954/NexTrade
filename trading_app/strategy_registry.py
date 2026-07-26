"""
NexTrade Strategy Registry & Automation Tier Specification.

Defines the complete canonical strategy library across Equity, Futures, and Options segments,
assigning strategy metadata, market regime suitability, and Tier 1-3 automation controls.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum, auto


class AutomationTier(Enum):
    TIER_1_FULLY_AUTOMATED = auto()      # Equity & Futures Intraday/Swing Strategies
    TIER_2_CONTROLLED_AUTOMATION = auto() # Defined-Risk Options Spreads
    TIER_3_ADVANCED_RESTRICTED = auto()   # Complex Multi-Leg Options (Requires Governance Override)


class MarketRegimeType(Enum):
    MODERATELY_BULLISH = "MODERATELY_BULLISH"
    STRONG_BULLISH_TREND = "STRONG_BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    SIDEWAYS_RANGEBOUND = "SIDEWAYS_RANGEBOUND"
    HIGH_VOLATILITY_UNSTABLE = "HIGH_VOLATILITY_UNSTABLE"


@dataclass
class StrategyMetadata:
    strategy_id: str
    name: str
    trading_style: str           # Intraday, Scalping, Swing, Futures, Options
    segment: str                 # EQUITY, FUTURES, OPTIONS
    suitable_regimes: List[MarketRegimeType]
    timeframe: str               # 5m, 15m, 1h, Daily
    risk_level: str              # LOW, MEDIUM, HIGH
    automation_tier: AutomationTier
    description: str
    default_stop_loss_pct: float
    default_target_pct: float
    min_risk_reward_ratio: float = 1.5
    is_active: bool = True


class StrategyRegistry:
    """Canonical Registry of all approved NexTrade strategies."""

    def __init__(self):
        self._strategies: Dict[str, StrategyMetadata] = {}
        self._initialize_canonical_library()

    def _initialize_canonical_library(self):
        # --- TIER 1: FULLY AUTOMATED EQUITY & FUTURES ---
        self.register(StrategyMetadata(
            strategy_id="str_momentum_breakout",
            name="Momentum Breakout",
            trading_style="Intraday",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.MODERATELY_BULLISH, MarketRegimeType.STRONG_BULLISH_TREND],
            timeframe="15m",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Identifies volume-backed price breakouts above key resistance or VWAP.",
            default_stop_loss_pct=1.5,
            default_target_pct=3.0,
            min_risk_reward_ratio=2.0
        ))

        self.register(StrategyMetadata(
            strategy_id="str_vwap_reversion",
            name="VWAP Mean Reversion",
            trading_style="Intraday",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.SIDEWAYS_RANGEBOUND],
            timeframe="5m",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Capitalizes on price overextension away from VWAP during rangebound markets.",
            default_stop_loss_pct=1.0,
            default_target_pct=2.0,
            min_risk_reward_ratio=2.0
        ))

        self.register(StrategyMetadata(
            strategy_id="str_orb_breakout",
            name="Opening Range Breakout (ORB)",
            trading_style="Intraday",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.STRONG_BULLISH_TREND, MarketRegimeType.BEARISH_TREND],
            timeframe="15m",
            risk_level="HIGH",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Trades directional expansion outside the first 15-minute high/low range.",
            default_stop_loss_pct=1.2,
            default_target_pct=2.5,
            min_risk_reward_ratio=2.08
        ))

        self.register(StrategyMetadata(
            strategy_id="str_adx_trend",
            name="ADX Trend Acceleration",
            trading_style="Intraday",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.STRONG_BULLISH_TREND, MarketRegimeType.BEARISH_TREND],
            timeframe="15m",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Captures trend momentum acceleration when ADX crosses above 25 with DI+ confirmation.",
            default_stop_loss_pct=1.2,
            default_target_pct=2.8,
            min_risk_reward_ratio=2.33
        ))

        self.register(StrategyMetadata(
            strategy_id="str_rsi_reversion",
            name="RSI Oversold/Overbought Reversion",
            trading_style="Intraday",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.SIDEWAYS_RANGEBOUND],
            timeframe="5m",
            risk_level="LOW",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Mean reversion trigger when RSI(14) crosses back inside 30/70 boundary levels.",
            default_stop_loss_pct=1.0,
            default_target_pct=2.0,
            min_risk_reward_ratio=2.0
        ))

        self.register(StrategyMetadata(
            strategy_id="str_bollinger_reversion",
            name="Bollinger Band Band-Touch Bounce",
            trading_style="Intraday",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.SIDEWAYS_RANGEBOUND],
            timeframe="15m",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Executes counter-trend bounce when candle closes outside 20-period 2SD Bollinger Band.",
            default_stop_loss_pct=1.1,
            default_target_pct=2.2,
            min_risk_reward_ratio=2.0
        ))

        self.register(StrategyMetadata(
            strategy_id="str_trend_following",
            name="Moving Average Trend Following",
            trading_style="Swing",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.STRONG_BULLISH_TREND, MarketRegimeType.BEARISH_TREND],
            timeframe="1h",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Rides sustained multi-day directional moves along 20/50 EMA cross paths.",
            default_stop_loss_pct=2.0,
            default_target_pct=5.0,
            min_risk_reward_ratio=2.5
        ))

        self.register(StrategyMetadata(
            strategy_id="str_breakout_volume",
            name="Breakout + Volume Surge",
            trading_style="Swing",
            segment="EQUITY",
            suitable_regimes=[MarketRegimeType.MODERATELY_BULLISH, MarketRegimeType.STRONG_BULLISH_TREND],
            timeframe="Daily",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Multi-day breakout swing trade confirmed by 2.5x 20-day average volume spike.",
            default_stop_loss_pct=2.5,
            default_target_pct=6.5,
            min_risk_reward_ratio=2.6
        ))

        self.register(StrategyMetadata(
            strategy_id="str_futures_momentum",
            name="Futures Momentum Drive",
            trading_style="Futures",
            segment="FUTURES",
            suitable_regimes=[MarketRegimeType.STRONG_BULLISH_TREND, MarketRegimeType.BEARISH_TREND],
            timeframe="15m",
            risk_level="HIGH",
            automation_tier=AutomationTier.TIER_1_FULLY_AUTOMATED,
            description="Leveraged futures directional breakout with tight intraday risk stops.",
            default_stop_loss_pct=1.0,
            default_target_pct=2.5,
            min_risk_reward_ratio=2.5
        ))

        # --- TIER 2: CONTROLLED AUTOMATION (OPTIONS) ---
        self.register(StrategyMetadata(
            strategy_id="str_options_buying_ce",
            name="Options Buying (Call Option Drive)",
            trading_style="Options",
            segment="OPTIONS",
            suitable_regimes=[MarketRegimeType.STRONG_BULLISH_TREND],
            timeframe="15m",
            risk_level="HIGH",
            automation_tier=AutomationTier.TIER_2_CONTROLLED_AUTOMATION,
            description="Out-of-the-money Call option purchase for strong bullish momentum.",
            default_stop_loss_pct=25.0,
            default_target_pct=60.0,
            min_risk_reward_ratio=2.4
        ))

        self.register(StrategyMetadata(
            strategy_id="str_options_buying_pe",
            name="Options Buying (Put Option Drive)",
            trading_style="Options",
            segment="OPTIONS",
            suitable_regimes=[MarketRegimeType.BEARISH_TREND],
            timeframe="15m",
            risk_level="HIGH",
            automation_tier=AutomationTier.TIER_2_CONTROLLED_AUTOMATION,
            description="Out-of-the-money Put option purchase for strong bearish trend momentum.",
            default_stop_loss_pct=25.0,
            default_target_pct=60.0,
            min_risk_reward_ratio=2.4
        ))

        self.register(StrategyMetadata(
            strategy_id="str_bull_call_spread",
            name="Bull Call Spread",
            trading_style="Options",
            segment="OPTIONS",
            suitable_regimes=[MarketRegimeType.MODERATELY_BULLISH],
            timeframe="Daily",
            risk_level="LOW",
            automation_tier=AutomationTier.TIER_2_CONTROLLED_AUTOMATION,
            description="Defined-risk bullish options spread buying ITM call and selling OTM call.",
            default_stop_loss_pct=30.0,
            default_target_pct=70.0,
            min_risk_reward_ratio=2.33
        ))

        self.register(StrategyMetadata(
            strategy_id="str_bear_put_spread",
            name="Bear Put Spread",
            trading_style="Options",
            segment="OPTIONS",
            suitable_regimes=[MarketRegimeType.BEARISH_TREND],
            timeframe="Daily",
            risk_level="LOW",
            automation_tier=AutomationTier.TIER_2_CONTROLLED_AUTOMATION,
            description="Defined-risk bearish options spread buying ITM put and selling OTM put.",
            default_stop_loss_pct=30.0,
            default_target_pct=70.0,
            min_risk_reward_ratio=2.33
        ))

        # --- TIER 3: ADVANCED / RESTRICTED MULTI-LEG ---
        self.register(StrategyMetadata(
            strategy_id="str_iron_condor",
            name="Iron Condor (Range-Bound Neutral)",
            trading_style="Options",
            segment="OPTIONS",
            suitable_regimes=[MarketRegimeType.SIDEWAYS_RANGEBOUND],
            timeframe="Daily",
            risk_level="MEDIUM",
            automation_tier=AutomationTier.TIER_3_ADVANCED_RESTRICTED,
            description="4-leg neutral options spread generating theta decay in tight ranges.",
            default_stop_loss_pct=40.0,
            default_target_pct=50.0,
            min_risk_reward_ratio=1.25
        ))

        self.register(StrategyMetadata(
            strategy_id="str_straddle_strangle",
            name="Long Straddle/Strangle Volatility Surge",
            trading_style="Options",
            segment="OPTIONS",
            suitable_regimes=[MarketRegimeType.HIGH_VOLATILITY_UNSTABLE],
            timeframe="15m",
            risk_level="HIGH",
            automation_tier=AutomationTier.TIER_3_ADVANCED_RESTRICTED,
            description="Buys both Call and Put options before major earnings or binary macroeconomic events.",
            default_stop_loss_pct=35.0,
            default_target_pct=90.0,
            min_risk_reward_ratio=2.57
        ))

    def register(self, metadata: StrategyMetadata):
        self._strategies[metadata.strategy_id] = metadata

    def get_strategy(self, strategy_id: str) -> Optional[StrategyMetadata]:
        return self._strategies.get(strategy_id)

    def get_all_strategies(self) -> List[StrategyMetadata]:
        return list(self._strategies.values())

    def get_eligible_strategies(
        self,
        regime: MarketRegimeType,
        max_tier: AutomationTier = AutomationTier.TIER_2_CONTROLLED_AUTOMATION
    ) -> List[StrategyMetadata]:
        """Filters strategies by market regime and permitted automation tier."""
        eligible = []
        for s in self._strategies.values():
            if not s.is_active:
                continue
            if regime in s.suitable_regimes and s.automation_tier.value <= max_tier.value:
                eligible.append(s)
        return eligible
