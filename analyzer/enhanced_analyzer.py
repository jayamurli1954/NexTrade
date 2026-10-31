# analyzer/enhanced_analyzer.py - PRODUCTION-READY VERSION
"""
VERSION: 3.0.1 - HONEST INTRADAY SIGNALS

WHY THIS VERSION EXISTS
This is a paper-trading tool today, but the plan is to trade real money on
these signals in ~6 months. That only works if a BUY/SELL signal here means
the same thing it will mean in live trading — no score inflation, no signals
that only "look" rejected in the logs but were never actually rejected.

CHANGES IN v3.0.0 (over v2.1.0):
1. _validate_signal() now genuinely REJECTS signals when price action badly
   contradicts the signal (e.g. a "BUY" fired while the stock is in freefall).
2. Fibonacci "near level" checks are bounded on BOTH sides
   (level * 0.98 to level * 1.02), not just "at or below" / "at or above".
3. buy_score / sell_score are capped at 100 BEFORE becoming confidence.
4. Minimum confirming conditions (min_confluence_count, default 2).
5. Sentiment lookups cached per symbol per day (NewsAPI quota).
6. Pre-market window uses explicit Asia/Kolkata time.
7. RATE LIMIT: score on last historical close first; fetch live Angel LTP
   only for candidates that already clear min_signal_score + confluence.
   Cuts LTP REST calls on a full watchlist by ~80%+.
8. SAME-DAY EXITS: after a BUY/SELL clears the daily gate, re-size stop/target
   from a short FIVE_MINUTE ATR (candidates only, ~10–15 calls/day). Labels
   stop_target_basis = intraday_5m_atr | daily_atr_fallback so paper logs
   stay honest. Daily ATR alone is multi-day distance; 3:15 PM square-off
   otherwise closes most trades by the clock, not by the signal's own levels.
9. BUY Fibonacci uses support_618 / support_500 (pullback near the low), not
   level_618 (near the high). SELL checks 78.6% resistance before 61.8%.
   Two-sided proximity bands from v3.0.0 are unchanged.

WHAT THIS DOES NOT CHANGE
RSI / EMA / volume / Bollinger / sentiment / fundamentals confluence is
untouched. v3.0.1 only corrects which Fibonacci ladder BUY vs SELL use.

HORIZON NOTE (honest): opportunity scanner feeds ONE_DAY candles for direction
(swing-style confluence). Live LTP times entry; 5m ATR sizes same-day SL/TP.
Not tick scalping or F&O Greeks.
"""

import sys
import os
import time
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.ta import atr, rsi, ema, sma, fibonacci_retracement, bollinger_bands
import pandas as pd
import numpy as np
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import requests

try:
    from utils.input_sanitizer import InputSanitizer, InputValidationError
    INPUT_SANITIZER_AVAILABLE = True
except ImportError:
    INPUT_SANITIZER_AVAILABLE = False
    logging.warning("⚠️ Input sanitizer not available - using basic validation")

logger = logging.getLogger("EnhancedAnalyzer")

IST = ZoneInfo("Asia/Kolkata")


def _safe_print(text):
    try:
        print(text)
    except Exception:
        safe_text = str(text).encode('ascii', errors='replace').decode('ascii')
        print(safe_text)


class EnhancedAnalyzer:
    """
    Production-ready analyzer with technical indicators, fundamentals, and sentiment.
    Tuned to be conservative: it would rather emit HOLD than a weak guess.
    """

    def __init__(self, data_provider, config_file=None):
        self.data_provider = data_provider
        self.config = self._load_config(config_file)

        self.golden_ratio = self.config.get('golden_ratio', 1.618)
        self.confidence_threshold = self.config.get('confidence_threshold', 0.60)
        self.min_signal_score = float(self.config.get('min_signal_score', 60))
        self.min_confluence_count = int(self.config.get('min_confluence_count', 2))
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.volume_threshold = self.config.get('volume_threshold', 1.2)
        self.ema_short_period = self.config.get('ema_short_period', 8)
        self.ema_long_period = self.config.get('ema_long_period', 21)
        self.analysis_period = self.config.get('analysis_period', 50)
        self.atr_period = int(self.config.get('atr_period', 14))
        self.fib_proximity_pct = float(self.config.get('fib_proximity_pct', 0.02))
        # A "Golden Ratio" entry must actually sit at a Fib level, and the trend
        # must agree with the direction (no buying a downtrend on RSI alone).
        self.require_fib_for_entry = bool(self.config.get('require_fib_for_entry', True))
        self.require_trend_agreement = bool(self.config.get('require_trend_agreement', True))
        # Minimum target move (% of price) a signal must project to clear the
        # ~0.2% round-trip cost floor and still pay — else it is not worth taking.
        self.min_target_move_pct = float(self.config.get('min_target_move_pct', 0.8))

        # Momentum-contradiction thresholds used by _validate_signal.
        self.moderate_momentum_1d_pct = float(self.config.get('moderate_momentum_1d_pct', 3.5))
        self.moderate_momentum_5d_pct = float(self.config.get('moderate_momentum_5d_pct', 8.0))
        self.severe_momentum_1d_pct = float(self.config.get('severe_momentum_1d_pct', 5.0))
        self.severe_momentum_5d_pct = float(self.config.get('severe_momentum_5d_pct', 12.0))
        self.rsi_reject_buy = float(self.config.get('rsi_reject_buy', 50))
        self.rsi_reject_sell = float(self.config.get('rsi_reject_sell', 50))

        self.newsapi_key = self.config.get('NEWSAPI_KEY', None)
        if not self.newsapi_key:
            logger.warning("⚠️ NEWSAPI_KEY not found in config - sentiment analysis disabled")

        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        self.sentiment_cache = {}

        self.fundamentals_enabled = self.config.get('enable_fundamentals', False)
        if self.fundamentals_enabled:
            try:
                from analyzer.fundamentals_analyzer import FundamentalsAnalyzer
                self.fundamentals_analyzer = FundamentalsAnalyzer(data_provider)
                logger.info("✅ Fundamentals analysis enabled")
            except ImportError:
                logger.warning("⚠️ FundamentalsAnalyzer not available - install yfinance or similar")
                self.fundamentals_enabled = False

    def _load_config(self, config_file):
        """Load configuration from file(s). Merges config/analyzer_config.json when present."""
        cfg: dict = {}

        def _merge_file(path: str) -> None:
            if not path or not os.path.exists(path):
                return
            import json
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f) or {}
            if not isinstance(raw, dict):
                return
            nested = raw.get("analyzer_config")
            if isinstance(nested, dict):
                cfg.update(nested)
            security = raw.get("security")
            if isinstance(security, dict):
                for k, v in security.items():
                    if k not in cfg or not cfg.get(k):
                        cfg[k] = v
            for k, v in raw.items():
                if k not in ("analyzer_config", "security") and (k not in cfg or not cfg.get(k)):
                    cfg[k] = v

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _merge_file(os.path.join(root, "analyzer_config.json"))
        _merge_file(os.path.join(root, "config", "analyzer_config.json"))
        if config_file:
            _merge_file(config_file)

        env_key = os.getenv("NEWSAPI_KEY")
        if env_key and not cfg.get("NEWSAPI_KEY"):
            cfg["NEWSAPI_KEY"] = env_key
        return cfg

    def _get_live_price_with_retry(self, symbol, exchange="NSE", max_retries=3):
        """Get live price with retry. Returns None if all retries fail."""
        for attempt in range(max_retries):
            try:
                price = self.data_provider.get_ltp(symbol, exchange)
                if price and price > 0:
                    return price

                logger.warning(f"Invalid price for {symbol} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Price fetch error for {symbol} (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)

        return None

    def _is_score_candidate(self, signal_data) -> bool:
        """True if first-pass (historical close) already cleared score + confluence → BUY/SELL."""
        if not signal_data:
            return False
        return str(signal_data.get("action") or "HOLD").upper() in ("BUY", "SELL")

    def analyze_symbol(self, symbol, exchange="NSE"):
        """
        Comprehensive analysis. Scores on last historical close first; fetches live
        Angel LTP only for candidates that already clear the confluence bar.
        Returns None whenever evidence isn't good enough.
        """
        try:
            if INPUT_SANITIZER_AVAILABLE:
                try:
                    sanitizer = InputSanitizer()
                    symbol = sanitizer.sanitize_symbol(symbol)
                    exchange = sanitizer.sanitize_exchange(exchange)
                except InputValidationError as e:
                    logger.error(f"Input validation failed: {e}")
                    return None
            else:
                if not symbol or not isinstance(symbol, str):
                    raise ValueError(f"Invalid symbol: {symbol}")

                symbol = symbol.strip().upper()
                if not symbol.replace('-', '').replace('_', '').isalnum():
                    raise ValueError(f"Symbol contains invalid characters: {symbol}")

                if exchange not in ['NSE', 'BSE', 'NFO', 'MCX', 'CDS']:
                    raise ValueError(f"Invalid exchange: {exchange}")

            # Rate limiting for historical data API (opportunity scanner may override)
            time.sleep(0.5)

            df = self.data_provider.get_historical(
                symbol=symbol,
                exchange=exchange,
                period_days=self.analysis_period
            )

            if df is None or df.empty or len(df) < 30:
                logger.warning(f"Insufficient data for {symbol}")
                return None

            close_prices = df['close'].astype(float)
            high_prices = df['high'].astype(float)
            low_prices = df['low'].astype(float)
            volume = df['volume'].astype(float)

            rsi_values = rsi(close_prices, period=14)
            current_rsi = rsi_values.iloc[-1] if not rsi_values.empty else 50

            ema_short = ema(close_prices, self.ema_short_period)
            ema_long = ema(close_prices, self.ema_long_period)

            current_ema_short = ema_short.iloc[-1] if not ema_short.empty else close_prices.iloc[-1]
            current_ema_long = ema_long.iloc[-1] if not ema_long.empty else close_prices.iloc[-1]

            period_high = high_prices.max()
            period_low = low_prices.min()
            fib_levels = fibonacci_retracement(period_high, period_low)

            atr_values = atr(high_prices, low_prices, close_prices, period=self.atr_period)
            try:
                atr_last = float(atr_values.iloc[-1]) if atr_values is not None and len(atr_values) else float("nan")
            except (TypeError, ValueError, IndexError):
                atr_last = float("nan")
            if atr_last != atr_last or atr_last <= 0:
                current_atr = float(close_prices.iloc[-1]) * 0.02
            else:
                current_atr = atr_last

            last_close = float(close_prices.iloc[-1])
            current_volume = volume.iloc[-1]
            avg_volume = volume.mean()
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            bb_upper, bb_middle, bb_lower = bollinger_bands(close_prices)
            current_bb_upper = bb_upper.iloc[-1] if not bb_upper.empty else last_close * 1.02
            current_bb_lower = bb_lower.iloc[-1] if not bb_lower.empty else last_close * 0.98

            sentiment = self._get_sentiment(symbol)

            fundamentals_score = 0
            fundamentals_highlights = []
            fundamentals_source = None
            investment_thesis = []
            factor_scores = None
            factor_badges = None
            factor_trends = None
            valuation_relatives = None
            fundamentals_meta = None
            display_source = None
            if self.fundamentals_enabled:
                try:
                    f_bundle = self.fundamentals_analyzer.analyze_fundamentals_bundle(symbol)
                    fundamentals_score = int(f_bundle.get("score") or 0)
                    fundamentals_highlights = list(f_bundle.get("highlights") or [])
                    fundamentals_source = f_bundle.get("source")
                    investment_thesis = list(f_bundle.get("investment_thesis") or [])
                    factor_scores = f_bundle.get("factor_scores")
                    factor_badges = f_bundle.get("factor_badges")
                    factor_trends = f_bundle.get("factor_trends")
                    valuation_relatives = f_bundle.get("valuation_relatives")
                    fundamentals_meta = f_bundle.get("fundamentals_meta")
                    display_source = f_bundle.get("display_source")
                except Exception as e:
                    logger.error(f"Fundamentals error for {symbol}: {e}")

            signal_kwargs = dict(
                symbol=symbol,
                current_rsi=current_rsi,
                ema_short=current_ema_short,
                ema_long=current_ema_long,
                fib_levels=fib_levels,
                volume_ratio=volume_ratio,
                bb_upper=current_bb_upper,
                bb_lower=current_bb_lower,
                period_high=period_high,
                period_low=period_low,
                sentiment=sentiment,
                fundamentals_score=fundamentals_score,
                fundamentals_highlights=fundamentals_highlights,
                fundamentals_source=fundamentals_source,
                investment_thesis=investment_thesis,
                factor_scores=factor_scores,
                factor_badges=factor_badges,
                factor_trends=factor_trends,
                valuation_relatives=valuation_relatives,
                fundamentals_meta=fundamentals_meta,
                display_source=display_source,
                current_atr=current_atr,
            )

            # First pass: score on last close — no Angel LTP yet (rate-limit savings).
            pre_signal = self._generate_golden_ratio_signal(
                current_price=last_close,
                price_change_1d=0.0,
                price_change_5d=(
                    ((last_close - float(close_prices.iloc[-5])) / float(close_prices.iloc[-5])) * 100
                    if len(close_prices) >= 5 else 0.0
                ),
                **signal_kwargs,
            )
            if not self._is_score_candidate(pre_signal):
                logger.debug(
                    "%s skipped LTP (first-pass %s score=%.0f)",
                    symbol,
                    (pre_signal or {}).get("action"),
                    float((pre_signal or {}).get("score") or 0),
                )
                return None

            current_price_live = self._get_live_price_with_retry(symbol, exchange)
            if current_price_live is None:
                logger.error(f"❌ Could not fetch live LTP for {symbol} - SKIPPING analysis")
                return None

            logger.info(f"Analyzing {symbol} - Live LTP: ₹{current_price_live:.2f}, ATR: ₹{current_atr:.2f}")

            price_change_1d = ((current_price_live - last_close) / last_close) * 100
            price_change_5d = (
                ((current_price_live - float(close_prices.iloc[-5])) / float(close_prices.iloc[-5])) * 100
                if len(close_prices) >= 5 else 0.0
            )

            signal_data = self._generate_golden_ratio_signal(
                current_price=current_price_live,
                price_change_1d=price_change_1d,
                price_change_5d=price_change_5d,
                **signal_kwargs,
            )

            if signal_data:
                is_valid = self._validate_signal(signal_data, price_change_1d, price_change_5d)
                if not is_valid:
                    return None

                if (
                    signal_data['action'] != 'HOLD'
                    and float(signal_data.get('confidence') or 0) >= float(self.confidence_threshold)
                ):
                    # Daily scan picks direction; same-day square-off needs session-scale
                    # stop/target. Only fetch 5m ATR for symbols that already cleared the gate.
                    intraday_atr = self._get_intraday_stop_target_atr(symbol, exchange)
                    if intraday_atr:
                        sl_mult = self.config.get('atr_stop_loss_multiplier', 1.5)
                        tgt_mult = self.config.get('atr_target_multiplier', 3.0)
                        if signal_data['action'] == 'BUY':
                            signal_data['stop_loss'] = round(
                                current_price_live - (sl_mult * intraday_atr), 2
                            )
                            signal_data['target'] = round(
                                current_price_live + (tgt_mult * intraday_atr), 2
                            )
                        else:  # SELL
                            signal_data['stop_loss'] = round(
                                current_price_live + (sl_mult * intraday_atr), 2
                            )
                            signal_data['target'] = round(
                                current_price_live - (tgt_mult * intraday_atr), 2
                            )
                        signal_data['intraday_atr'] = round(intraday_atr, 2)
                        signal_data['stop_target_basis'] = 'intraday_5m_atr'
                    else:
                        signal_data['stop_target_basis'] = 'daily_atr_fallback'

                    logger.info(
                        f"✅ Signal found for {symbol}: {signal_data['action']} @ ₹{current_price_live:.2f} "
                        f"(confidence: {signal_data['confidence']:.1%}, "
                        f"stop/target basis: {signal_data['stop_target_basis']})"
                    )
                    return signal_data
                return None

            return None

        except Exception as e:
            logger.exception(f"Error analyzing {symbol}: {e}")
            return None

    def _get_intraday_stop_target_atr(self, symbol, exchange):
        """
        Short-interval (5-min) ATR for stop/target sizing — candidates only.
        Returns None if unavailable or Angel REST is in cooldown (daily ATR fallback).
        """
        try:
            try:
                from trading_app.angel_rest_limiter import rest_in_cooldown
                if rest_in_cooldown():
                    return None
            except Exception:
                pass
            df = self.data_provider.get_historical(
                symbol=symbol,
                exchange=exchange,
                period_days=2,
                interval="FIVE_MINUTE",
            )
            if df is None or df.empty or len(df) < self.atr_period + 1:
                return None
            atr_series = atr(
                df['high'].astype(float),
                df['low'].astype(float),
                df['close'].astype(float),
                period=self.atr_period,
            )
            if atr_series is None or len(atr_series) == 0:
                return None
            val = float(atr_series.iloc[-1])
            if val != val or val <= 0:
                return None
            # Pace candidate 5m fetches so a burst of signals doesn't trip Angel hist limits
            time.sleep(0.45)
            return val
        except Exception as e:
            logger.debug(f"Intraday ATR unavailable for {symbol}: {e}")
            return None

    def _validate_signal(self, signal, price_change_1d, price_change_5d):
        """
        Honest momentum gate.
        - SEVERE contradiction -> REJECT (False); analyze_symbol drops the signal.
        - MODERATE contradiction -> confidence penalty only.
        """
        action = signal['action']
        rsi_val = signal['rsi']
        symbol = signal.get('symbol', '?')

        if action == 'BUY':
            severe = (
                (price_change_1d < -self.severe_momentum_1d_pct and rsi_val > self.rsi_reject_buy)
                or (price_change_5d < -self.severe_momentum_5d_pct and rsi_val > self.rsi_reject_buy)
            )
            if severe:
                logger.warning(
                    f"⚠️ Signal REJECTED for {symbol}: BUY but price fell {price_change_1d:.1f}% (1d) / "
                    f"{price_change_5d:.1f}% (5d) while RSI is {rsi_val:.1f} — falling knife, not support."
                )
                return False

            moderate = (
                (price_change_1d < -self.moderate_momentum_1d_pct and rsi_val > 45)
                or (price_change_5d < -self.moderate_momentum_5d_pct and rsi_val > 45)
            )
            if moderate:
                signal['confidence'] = max(0.40, round(signal['confidence'] - 0.15, 2))
            return True

        if action == 'SELL':
            severe = (
                (price_change_1d > self.severe_momentum_1d_pct and rsi_val < self.rsi_reject_sell)
                or (price_change_5d > self.severe_momentum_5d_pct and rsi_val < self.rsi_reject_sell)
            )
            if severe:
                logger.warning(
                    f"⚠️ Signal REJECTED for {symbol}: SELL but price rose {price_change_1d:.1f}% (1d) / "
                    f"{price_change_5d:.1f}% (5d) while RSI is {rsi_val:.1f} — real strength, not exhaustion."
                )
                return False

            moderate = (
                (price_change_1d > self.moderate_momentum_1d_pct and rsi_val < 55)
                or (price_change_5d > self.moderate_momentum_5d_pct and rsi_val < 55)
            )
            if moderate:
                signal['confidence'] = max(0.40, round(signal['confidence'] - 0.15, 2))
            return True

        return True

    def _get_sentiment(self, symbol):
        """Fetch sentiment from news, cached per symbol per IST day."""
        if not self.newsapi_key:
            return 0

        cache_key = f"{symbol}_{datetime.now(IST).strftime('%Y-%m-%d')}"
        if cache_key in self.sentiment_cache:
            return self.sentiment_cache[cache_key]

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f"{symbol} stock",
                'apiKey': self.newsapi_key,
                'pageSize': 5,
                'sortBy': 'relevancy',
                'language': 'en'
            }

            response = requests.get(url, params=params, timeout=5)
            news = response.json().get('articles', [])

            if not news:
                self.sentiment_cache[cache_key] = 0
                return 0

            texts = [
                (article.get('title', '') + ' ' + (article.get('description') or ''))
                for article in news if article.get('title')
            ]
            scores = [
                self.sentiment_analyzer.polarity_scores(text)['compound']
                for text in texts if text
            ]
            avg_sentiment = sum(scores) / len(scores) if scores else 0
            logger.debug(f"Sentiment for {symbol}: {avg_sentiment:.2f}")
            self.sentiment_cache[cache_key] = avg_sentiment
            return avg_sentiment

        except Exception as e:
            logger.error(f"Sentiment error for {symbol}: {e}")
            return 0

    def _generate_golden_ratio_signal(
        self,
        symbol,
        current_price,
        current_rsi,
        ema_short,
        ema_long,
        fib_levels,
        volume_ratio,
        bb_upper,
        bb_lower,
        period_high,
        period_low,
        sentiment,
        fundamentals_score,
        fundamentals_highlights,
        fundamentals_source,
        investment_thesis=None,
        factor_scores=None,
        factor_badges=None,
        factor_trends=None,
        valuation_relatives=None,
        fundamentals_meta=None,
        display_source=None,
        price_change_1d=0,
        price_change_5d=0,
        current_atr=0,
    ):
        """
        Score BUY/SELL confluence; require score AND min confirming conditions.
        FI-2: factor display fields attached; gate math uses fundamentals_score only.
        """
        signal = {
            'symbol': symbol,
            'current_price': round(current_price, 2),
            'rsi': round(current_rsi, 2),
            'action': 'HOLD',
            'confidence': 0.0,
            'reason': 'No clear signal',
            'target': 0,
            'stop_loss': 0,
            'timestamp': datetime.now(IST).isoformat(),
            'fib_levels': {k: round(v, 2) for k, v in fib_levels.items()},
            'volume_ratio': round(volume_ratio, 2),
            'sentiment': round(sentiment, 2),
            'fundamentals_score': round(fundamentals_score, 1),
            'fundamentals_highlights': list(fundamentals_highlights or []),
            'fundamentals_source': fundamentals_source,
            'investment_thesis': list(investment_thesis or []),
            'factor_scores': factor_scores,
            'factor_badges': factor_badges,
            'factor_trends': factor_trends,
            'valuation_relatives': valuation_relatives,
            'fundamentals_meta': fundamentals_meta,
            'display_source': display_source,
            'price_change_1d': round(price_change_1d, 2),
            'price_change_5d': round(price_change_5d, 2),
            'atr': round(current_atr, 2),
        }

        buy_weights = self.config.get('strategy_weights', {}).get('buy', {})
        sell_weights = self.config.get('strategy_weights', {}).get('sell', {})

        tol = self.fib_proximity_pct
        fib_support_618 = fib_levels['support_618']
        fib_support_500 = fib_levels['support_500']
        fib_resist_618 = fib_levels['level_618']
        fib_resist_786 = fib_levels.get('level_786', fib_resist_618)

        buy_conditions = []
        buy_score = 0
        buy_fib_hit = False

        if fib_support_618 * (1 - tol) <= current_price <= fib_support_618 * (1 + tol):
            buy_conditions.append("Near Golden Ratio support (61.8% retracement)")
            buy_score += buy_weights.get('fib_618', 25)
            buy_fib_hit = True
        elif fib_support_500 * (1 - tol) <= current_price <= fib_support_500 * (1 + tol):
            buy_conditions.append("At Fib 50% retracement")
            buy_score += buy_weights.get('fib_500', 20)
            buy_fib_hit = True

        if current_rsi <= self.rsi_oversold:
            buy_conditions.append(f"RSI oversold ({current_rsi:.1f})")
            buy_score += buy_weights.get('rsi_oversold', 20)
        elif current_rsi <= 40:
            buy_conditions.append("RSI < 40")
            buy_score += buy_weights.get('rsi_mid', 10)

        if ema_short > ema_long:
            buy_conditions.append("EMA uptrend")
            buy_score += buy_weights.get('ema_uptrend', 20)
        elif ema_short > ema_long * 0.99:
            buy_conditions.append("EMA near crossover")
            buy_score += buy_weights.get('ema_crossover', 10)

        if volume_ratio >= self.volume_threshold:
            buy_conditions.append(f"Volume {volume_ratio:.1f}x")
            buy_score += buy_weights.get('volume_spike', 10)

        if current_price <= bb_lower:
            buy_conditions.append("At lower BB")
            buy_score += buy_weights.get('bb_lower', 8)

        if sentiment > 0.2:
            buy_conditions.append(f"Sentiment +{sentiment:.2f}")
            buy_score += buy_weights.get('sentiment_positive', 7)

        if fundamentals_score > 0:
            fundamental_points = int(fundamentals_score * (buy_weights.get('fundamentals_strong', 20) / 100.0))
            if fundamental_points >= 10:
                buy_conditions.append(f"Strong fundamentals ({fundamentals_score:.0f}/100)")
            buy_score += fundamental_points

        sell_conditions = []
        sell_score = 0
        sell_fib_hit = False

        if fib_resist_786 * (1 - tol) <= current_price <= fib_resist_786 * (1 + tol):
            sell_conditions.append("At Fib 78.6% resistance")
            sell_score += sell_weights.get('fib_786', 20)
            sell_fib_hit = True
        elif fib_resist_618 * (1 - tol) <= current_price <= fib_resist_618 * (1 + tol):
            sell_conditions.append("Near Golden Ratio resistance (61.8%)")
            sell_score += sell_weights.get('fib_618', 25)
            sell_fib_hit = True

        if current_rsi >= self.rsi_overbought:
            sell_conditions.append(f"RSI overbought ({current_rsi:.1f})")
            sell_score += sell_weights.get('rsi_overbought', 20)
        elif current_rsi >= 60:
            sell_conditions.append("RSI > 60")
            sell_score += sell_weights.get('rsi_mid', 10)

        if ema_short < ema_long:
            sell_conditions.append("EMA downtrend")
            sell_score += sell_weights.get('ema_downtrend', 20)
        elif ema_short < ema_long * 1.01:
            sell_conditions.append("EMA near crossover")
            sell_score += sell_weights.get('ema_crossover', 10)

        if volume_ratio >= self.volume_threshold:
            sell_conditions.append(f"Volume {volume_ratio:.1f}x")
            sell_score += sell_weights.get('volume_spike', 10)

        if current_price >= bb_upper:
            sell_conditions.append("At upper BB")
            sell_score += sell_weights.get('bb_upper', 8)

        if sentiment < -0.2:
            sell_conditions.append(f"Sentiment {sentiment:.2f}")
            sell_score += sell_weights.get('sentiment_negative', 7)

        if fundamentals_score > 0 and fundamentals_score < 40:
            sell_conditions.append(f"Weak fundamentals ({fundamentals_score:.0f}/100)")
            sell_score += sell_weights.get('fundamentals_weak', 10)

        buy_score = min(buy_score, 100)
        sell_score = min(sell_score, 100)

        atr_multiplier_sl = self.config.get('atr_stop_loss_multiplier', 1.5)
        atr_multiplier_target = self.config.get('atr_target_multiplier', 3.0)
        min_score = float(getattr(self, "min_signal_score", 60) or 60)
        min_confluence = int(getattr(self, "min_confluence_count", 2) or 2)
        atr_px = float(current_atr or 0) or (float(current_price) * 0.02)

        prefer_buy = buy_score > sell_score
        prefer_sell = sell_score > buy_score
        winning_score = max(buy_score, sell_score)

        # Golden-Ratio entries must actually be at a Fib level when required.
        buy_fib_ok = buy_fib_hit or not self.require_fib_for_entry
        sell_fib_ok = sell_fib_hit or not self.require_fib_for_entry

        # Trend must agree with direction — never buy a downtrend (or sell an
        # uptrend) on an oscillator alone. This is what stopped the daily
        # falling-knife re-entries into the same losing names.
        buy_trend_ok = (ema_short > ema_long) or not self.require_trend_agreement
        sell_trend_ok = (ema_short < ema_long) or not self.require_trend_agreement

        # Cost hurdle: the projected target move must beat the round-trip cost
        # floor, else the trade cannot pay even when it works.
        expected_move_pct = (atr_multiplier_target * atr_px / current_price * 100.0) if current_price else 0.0
        target_move_ok = expected_move_pct >= self.min_target_move_pct

        buy_ok = (
            prefer_buy and buy_score >= min_score and len(buy_conditions) >= min_confluence
            and buy_fib_ok and buy_trend_ok and target_move_ok
        )
        sell_ok = (
            prefer_sell and sell_score >= min_score and len(sell_conditions) >= min_confluence
            and sell_fib_ok and sell_trend_ok and target_move_ok
        )

        if buy_ok:
            signal['action'] = 'BUY'
            signal['confidence'] = min(0.95, round(buy_score / 100.0, 2))
            signal['reason'] = ' + '.join(buy_conditions[:3]) if buy_conditions else "EMA Uptrend + Momentum Support"
            signal['stop_loss'] = round(current_price - (atr_multiplier_sl * atr_px), 2)
            signal['target'] = round(current_price + (atr_multiplier_target * atr_px), 2)
            signal['score'] = round(buy_score, 1)
        elif sell_ok:
            signal['action'] = 'SELL'
            signal['confidence'] = min(0.95, round(sell_score / 100.0, 2))
            signal['reason'] = ' + '.join(sell_conditions[:3]) if sell_conditions else "EMA Downtrend + Resistance"
            signal['stop_loss'] = round(current_price + (atr_multiplier_sl * atr_px), 2)
            signal['target'] = round(current_price - (atr_multiplier_target * atr_px), 2)
            signal['score'] = round(sell_score, 1)
        else:
            signal['action'] = 'HOLD'
            signal['confidence'] = min(0.95, round(winning_score / 100.0, 2)) if winning_score else 0.0
            if winning_score >= min_score and max(len(buy_conditions), len(sell_conditions)) < min_confluence:
                signal['reason'] = (
                    f"Score cleared the bar ({winning_score:.0f}) but only "
                    f"{max(len(buy_conditions), len(sell_conditions))} confirming factor(s) fired "
                    f"(need ≥{min_confluence}) — too reliant on a single factor to trust."
                )
            else:
                signal['reason'] = (
                    f"Insufficient confluence (buy={buy_score:.0f} sell={sell_score:.0f}, "
                    f"need ≥{min_score:.0f})"
                )
            signal['score'] = round(winning_score, 1)

        return signal

    def analyze_watchlist(self, symbols, exchange="NSE"):
        """Analyze multiple symbols with rate limiting and progress tracking."""
        logger.info(f"Starting watchlist analysis for {len(symbols)} symbols")
        signals = []

        total_symbols = len(symbols)
        _safe_print(f"[ANALYZER] Analyzing {total_symbols} stocks...")

        for idx, sym in enumerate(symbols):
            if idx > 0 and idx % 10 == 0:
                _safe_print(f"  [PROGRESS] {idx}/{total_symbols} analyzed... ({len(signals)} signals)")

            try:
                signal = self.analyze_symbol(sym, exchange)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error analyzing {sym}: {e}")

            if idx < total_symbols - 1:
                time.sleep(0.05)

        signals.sort(key=lambda x: x['confidence'], reverse=True)
        logger.info(f"Analysis complete: {len(signals)} valid signals found")

        top_signals = signals[:10]
        _safe_print(f"[OK] Returning top {len(top_signals)} signals")
        return top_signals

    def run_premarket_analysis(self, symbols, exchange="NSE"):
        """Run pre-market analysis (7:00 AM - 9:15 AM IST)."""
        current_time = datetime.now(IST).time()
        premarket_start = dt_time(7, 0)
        premarket_end = dt_time(9, 15)
        is_premarket = premarket_start <= current_time <= premarket_end

        logger.info(
            f"Pre-market analysis - IST Time: {current_time.strftime('%H:%M:%S')}, "
            f"Is pre-market: {is_premarket}"
        )

        signals = self.analyze_watchlist(symbols, exchange)

        result = {
            'timestamp': datetime.now(IST).isoformat(),
            'is_premarket_hours': is_premarket,
            'total_symbols_analyzed': len(symbols),
            'signals_found': len(signals),
            'high_confidence_signals': len([s for s in signals if s['confidence'] >= 0.8]),
            'signals': signals,
        }

        logger.info(
            f"Pre-market complete: {result['signals_found']} signals, "
            f"{result['high_confidence_signals']} high confidence"
        )
        return result

    def get_market_overview(self):
        """Get overview of major indices."""
        indices = ['NIFTY', 'SENSEX', 'BANKNIFTY']
        overview = {}

        for index in indices:
            try:
                ltp = self.data_provider.get_ltp(index, "NSE")
                if ltp:
                    df = self.data_provider.get_historical(index, period_days=5)
                    if not df.empty:
                        prev_close = df['close'].iloc[-2] if len(df) > 1 else ltp
                        change = ltp - prev_close
                        change_pct = (change / prev_close) * 100
                        overview[index] = {
                            'ltp': round(ltp, 2),
                            'change': round(change, 2),
                            'change_pct': round(change_pct, 2),
                            'trend': 'UP' if change > 0 else 'DOWN' if change < 0 else 'FLAT',
                        }
                        logger.info(f"{index}: ₹{ltp:.2f} ({change_pct:+.2f}%)")
            except Exception as e:
                logger.error(f"Error getting overview for {index}: {e}")

        return overview
