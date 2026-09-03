"""Regression tests for analyzer Fibonacci support/resistance, ATR, config, rejection."""
from __future__ import annotations

import os
import unittest

import numpy as np
import pandas as pd

from indicators.ta import atr, fibonacci_retracement
from analyzer.enhanced_analyzer import EnhancedAnalyzer
from backtesting.backtest_engine import BacktestEngine
from backtesting.backtest_engine_v2 import BacktestEngineV2


class _DummyProvider:
    def get_ltp(self, *args, **kwargs):
        return None

    def get_historical(self, *args, **kwargs):
        return None


class TestFibonacciLadders(unittest.TestCase):
    def test_support_618_is_near_the_low_not_the_high(self):
        levels = fibonacci_retracement(high=200.0, low=100.0)
        self.assertAlmostEqual(levels["level_618"], 161.8, places=5)
        self.assertAlmostEqual(levels["support_618"], 138.2, places=5)
        self.assertLess(levels["support_618"], levels["level_500"])
        self.assertGreater(levels["level_618"], levels["level_500"])
        self.assertAlmostEqual(levels["support_618"], levels["level_382"], places=5)

    def test_atr_tracks_volatility_not_flat_two_percent(self):
        n = 40
        idx = pd.RangeIndex(n)
        quiet_close = pd.Series(np.linspace(100.0, 101.0, n), index=idx)
        quiet_high = quiet_close + 0.2
        quiet_low = quiet_close - 0.2
        wild_close = pd.Series(np.linspace(100.0, 101.0, n), index=idx)
        wild_high = wild_close + 8.0
        wild_low = wild_close - 8.0

        quiet_atr = float(atr(quiet_high, quiet_low, quiet_close, period=14).iloc[-1])
        wild_atr = float(atr(wild_high, wild_low, wild_close, period=14).iloc[-1])
        stub = float(quiet_close.iloc[-1]) * 0.02

        self.assertGreater(wild_atr, quiet_atr * 5)
        self.assertLess(quiet_atr, stub)


class TestEnhancedAnalyzerFixes(unittest.TestCase):
    def setUp(self):
        self.analyzer = EnhancedAnalyzer(_DummyProvider())

    def _fib_kwargs(self, price, rsi_val=45.0, ema_short=101.0, ema_long=100.0):
        levels = fibonacci_retracement(high=200.0, low=100.0)
        return dict(
            symbol="TEST",
            current_price=price,
            current_rsi=rsi_val,
            ema_short=ema_short,
            ema_long=ema_long,
            fib_levels=levels,
            volume_ratio=1.0,
            bb_upper=180.0,
            bb_lower=120.0,
            period_high=200.0,
            period_low=100.0,
            sentiment=0.0,
            fundamentals_score=0,
            fundamentals_highlights=[],
            fundamentals_source=None,
            current_atr=2.0,
        )

    def test_config_auto_loads_nested_analyzer_section(self):
        self.assertGreaterEqual(self.analyzer.confidence_threshold, 0.5)
        buy_w = (self.analyzer.config.get("strategy_weights") or {}).get("buy") or {}
        self.assertEqual(buy_w.get("fib_618"), 25)
        self.assertTrue(
            os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "analyzer_config.json"))
            or os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), "analyzer_config.json"))
        )

    def test_buy_golden_ratio_uses_support_not_resistance(self):
        levels = fibonacci_retracement(high=200.0, low=100.0)
        near_support = self.analyzer._generate_golden_ratio_signal(
            **self._fib_kwargs(levels["support_618"], rsi_val=28.0, ema_short=101.0, ema_long=100.0)
        )
        near_resistance = self.analyzer._generate_golden_ratio_signal(
            **self._fib_kwargs(levels["level_618"], rsi_val=75.0, ema_short=99.0, ema_long=100.0)
        )

        self.assertEqual(near_support["action"], "BUY")
        self.assertIn("Golden Ratio support", near_support["reason"])
        self.assertEqual(near_resistance["action"], "SELL")
        self.assertNotIn("Golden Ratio support", near_resistance["reason"])
        self.assertIn("resistance", near_resistance["reason"].lower())

    def test_mid_range_price_does_not_get_golden_ratio_buy(self):
        mid = self.analyzer._generate_golden_ratio_signal(**self._fib_kwargs(150.0))
        self.assertNotIn("Golden Ratio", mid["reason"])

    def test_validate_signal_rejects_falling_knife_buy(self):
        signal = {
            "action": "BUY",
            "rsi": 62.0,
            "confidence": 0.80,
            "symbol": "TEST",
        }
        self.assertFalse(self.analyzer._validate_signal(signal, price_change_1d=-6.0, price_change_5d=-2.0))

    def test_validate_signal_only_dampens_moderate_mismatch(self):
        signal = {
            "action": "BUY",
            "rsi": 48.0,
            "confidence": 0.80,
            "symbol": "TEST",
        }
        self.assertTrue(self.analyzer._validate_signal(signal, price_change_1d=-4.0, price_change_5d=-2.0))
        self.assertLess(signal["confidence"], 0.80)


class TestBacktestFibAlignment(unittest.TestCase):
    def test_v1_buy_scores_support_618_not_level_618(self):
        engine = BacktestEngine(_DummyProvider())
        levels = fibonacci_retracement(high=200.0, low=100.0)
        buy_near_support = engine._generate_signal(
            "TEST", levels["support_618"], 40, 101, 100, levels, 1.0, 180, 120, 2.0
        )
        buy_mid = engine._generate_signal("TEST", 150.0, 40, 101, 100, levels, 1.0, 180, 120, 2.0)
        self.assertIsNotNone(buy_near_support)
        self.assertEqual(buy_near_support["action"], "BUY")
        self.assertIsNone(buy_mid)

    def test_v2_buy_scores_support_618_not_mid_range(self):
        try:
            engine = BacktestEngineV2()
        except ImportError:
            self.skipTest("yfinance not installed")
        levels = fibonacci_retracement(high=200.0, low=100.0)
        buy_near_support = engine._generate_signal(
            "TEST", levels["support_618"], 40, 101, 100, levels, 1.0, 180, 120, 2.0
        )
        buy_mid = engine._generate_signal("TEST", 150.0, 40, 101, 100, levels, 1.0, 180, 120, 2.0)
        self.assertIsNotNone(buy_near_support)
        self.assertEqual(buy_near_support["action"], "BUY")
        self.assertIsNone(buy_mid)


if __name__ == "__main__":
    unittest.main()
