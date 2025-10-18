# analyzer/enhanced_analyzer.py - PRODUCTION-READY VERSION
"""
VERSION: 2.0.0 - FULLY FIXED & ENHANCED

CRITICAL FIXES FROM PEER REVIEWS:
1. ✅ Fixed time import conflict (was causing crashes)
2. ✅ Removed hardcoded API keys (use environment variables)
3. ✅ Added ATR-based stop loss and targets (volatility-aware)
4. ✅ Added fundamentals scoring framework
5. ✅ Fixed duplicate sleep statements
6. ✅ Improved signal validation with momentum checks
7. ✅ Better error handling and logging
8. ✅ Rate limiting to prevent API throttling

PEER REVIEW COMPLIANCE:
- Review 1: ✅ Fixed runtime bugs (time conflict, duplicate sleeps)
- Review 2: ✅ Real market-based signals (not hash-based)
- Review 3: ✅ Security improvements (env vars, input validation)
"""

import sys
import os
import time  # ✅ FIXED: Separate import for time.sleep()
from datetime import datetime, time as dt_time, timedelta  # ✅ FIXED: Renamed to dt_time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.ta import rsi, ema, sma, fibonacci_retracement, bollinger_bands, atr
import pandas as pd
import numpy as np
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import requests

logger = logging.getLogger("EnhancedAnalyzer")


class EnhancedAnalyzer:
    """
    Production-ready analyzer with technical indicators, fundamentals, and sentiment analysis
    """
    
    def __init__(self, data_provider, config_file=None):
        self.data_provider = data_provider
        
        # ✅ FIXED: Load configuration from file or environment
        self.config = self._load_config(config_file)
        
        # Strategy parameters (can be overridden by config)
        self.golden_ratio = self.config.get('golden_ratio', 1.618)
        self.confidence_threshold = self.config.get('confidence_threshold', 0.65)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.volume_threshold = self.config.get('volume_threshold', 1.2)
        self.ema_short_period = self.config.get('ema_short_period', 8)
        self.ema_long_period = self.config.get('ema_long_period', 21)
        self.analysis_period = self.config.get('analysis_period', 50)
        
        # ✅ FIXED: Use environment variable for API key
        self.newsapi_key = os.getenv('NEWSAPI_KEY', None)
        if not self.newsapi_key:
            logger.warning("⚠️ NEWSAPI_KEY not found - sentiment analysis disabled")
        
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        
        # ✅ NEW: Fundamentals analyzer (if available)
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
        """Load configuration from file"""
        if config_file and os.path.exists(config_file):
            import json
            with open(config_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _get_live_price_with_retry(self, symbol, exchange="NSE", max_retries=3):
        """
        Get live price with retry logic
        Returns None if all retries fail
        """
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

    def analyze_symbol(self, symbol, exchange="NSE"):
        """
        Comprehensive analysis with LIVE LTP, technical indicators, and optional fundamentals
        """
        try:
            # ✅ FIXED: Input validation (Peer Review 3)
            if not symbol or not isinstance(symbol, str):
                raise ValueError(f"Invalid symbol: {symbol}")
            
            symbol = symbol.strip().upper()
            if not symbol.replace('-', '').replace('_', '').isalnum():
                raise ValueError(f"Symbol contains invalid characters: {symbol}")
            
            if exchange not in ['NSE', 'BSE', 'NFO', 'MCX', 'CDS']:
                raise ValueError(f"Invalid exchange: {exchange}")

            # Rate limiting for historical data API
            time.sleep(0.5)
            
            # Get historical data for indicators
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

            # Calculate technical indicators
            rsi_values = rsi(close_prices, period=14)
            current_rsi = rsi_values.iloc[-1] if not rsi_values.empty else 50

            ema_short = ema(close_prices, self.ema_short_period)
            ema_long = ema(close_prices, self.ema_long_period)

            current_ema_short = ema_short.iloc[-1] if not ema_short.empty else close_prices.iloc[-1]
            current_ema_long = ema_long.iloc[-1] if not ema_long.empty else close_prices.iloc[-1]

            period_high = high_prices.max()
            period_low = low_prices.min()
            fib_levels = fibonacci_retracement(period_high, period_low)

            # ✅ NEW: Calculate ATR for volatility-based stops (Peer Review recommendation)
            atr_values = atr(high_prices, low_prices, close_prices, period=14)
            current_atr = atr_values.iloc[-1] if not atr_values.empty else close_prices.iloc[-1] * 0.02

            # Get LIVE LTP with retry
            current_price_live = self._get_live_price_with_retry(symbol, exchange)
            if current_price_live is None:
                logger.error(f"❌ Could not fetch live LTP for {symbol} - SKIPPING analysis")
                return None
            
            logger.info(f"Analyzing {symbol} - Live LTP: ₹{current_price_live:.2f}, ATR: ₹{current_atr:.2f}")

            current_volume = volume.iloc[-1]
            avg_volume = volume.mean()
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            bb_upper, bb_middle, bb_lower = bollinger_bands(close_prices)
            current_bb_upper = bb_upper.iloc[-1] if not bb_upper.empty else current_price_live * 1.02
            current_bb_lower = bb_lower.iloc[-1] if not bb_lower.empty else current_price_live * 0.98

            # Get sentiment score
            sentiment = self._get_sentiment(symbol)
            
            # ✅ NEW: Get fundamentals score (if enabled)
            fundamentals_score = 0
            if self.fundamentals_enabled:
                try:
                    fundamentals_score = self.fundamentals_analyzer.analyze_fundamentals(symbol)
                    logger.debug(f"{symbol} fundamentals score: {fundamentals_score}/100")
                except Exception as e:
                    logger.error(f"Fundamentals error for {symbol}: {e}")

            # Calculate price momentum for validation
            price_change_1d = ((current_price_live - close_prices.iloc[-1]) / close_prices.iloc[-1]) * 100
            price_change_5d = ((current_price_live - close_prices.iloc[-5]) / close_prices.iloc[-5]) * 100 if len(close_prices) >= 5 else 0

            # Generate signal with all data
            signal_data = self._generate_golden_ratio_signal(
                symbol=symbol,
                current_price=current_price_live,
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
                price_change_1d=price_change_1d,
                price_change_5d=price_change_5d,
                current_atr=current_atr  # ✅ NEW: Pass ATR for stops
            )

            if signal_data:
                # Validate signal logic
                is_valid = self._validate_signal(signal_data, price_change_1d, price_change_5d)
                
                if not is_valid:
                    logger.warning(f"⚠️ Signal REJECTED for {symbol}: {signal_data['action']} doesn't match momentum")
                    return None
                
                if signal_data['confidence'] >= self.confidence_threshold:
                    logger.info(f"✅ Valid signal for {symbol}: {signal_data['action']} @ ₹{current_price_live:.2f} (confidence: {signal_data['confidence']:.1%})")
                    return signal_data
                else:
                    logger.debug(f"Low confidence for {symbol} ({signal_data['confidence']:.1%})")
                    return None
            
            return None
            
        except Exception as e:
            logger.exception(f"Error analyzing {symbol}: {e}")
            return None

    def _validate_signal(self, signal, price_change_1d, price_change_5d):
        """
        Validate that signal matches price momentum
        """
        action = signal['action']
        
        if action == 'BUY':
            # For BUY: allow if not falling sharply OR strong oversold
            if price_change_1d < -2.0 and signal['rsi'] > 35:
                logger.debug(f"BUY rejected: Price falling {price_change_1d:.2f}% without oversold RSI")
                return False
            
            if price_change_5d < -5.0 and signal['rsi'] > 30:
                logger.debug(f"BUY rejected: Strong downtrend ({price_change_5d:.2f}%)")
                return False
            
            return True
        
        elif action == 'SELL':
            # For SELL: allow if not rising sharply OR strong overbought
            if price_change_1d > 2.0 and signal['rsi'] < 65:
                logger.debug(f"SELL rejected: Price rising {price_change_1d:.2f}% without overbought RSI")
                return False
            
            if price_change_5d > 5.0 and signal['rsi'] < 70:
                logger.debug(f"SELL rejected: Strong uptrend ({price_change_5d:.2f}%)")
                return False
            
            return True
        
        return True

    def _get_sentiment(self, symbol):
        """Fetch sentiment from news"""
        if not self.newsapi_key:
            return 0
        
        try:
            url = f"https://newsapi.org/v2/everything"
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
                return 0
            
            texts = [article.get('title', '') + ' ' + article.get('description', '') 
                    for article in news if article.get('title')]
            
            scores = [self.sentiment_analyzer.polarity_scores(text)['compound'] 
                     for text in texts if text]
            
            avg_sentiment = sum(scores) / len(scores) if scores else 0
            logger.debug(f"Sentiment for {symbol}: {avg_sentiment:.2f}")
            return avg_sentiment
            
        except Exception as e:
            logger.error(f"Sentiment error for {symbol}: {e}")
            return 0

    def _generate_golden_ratio_signal(self, symbol, current_price, current_rsi, ema_short, ema_long, 
                                     fib_levels, volume_ratio, bb_upper, bb_lower, period_high, 
                                     period_low, sentiment, fundamentals_score, price_change_1d, 
                                     price_change_5d, current_atr):
        """
        ✅ ENHANCED: Now includes fundamentals and ATR-based stops
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
            'timestamp': datetime.now().isoformat(),
            'fib_levels': {k: round(v, 2) for k, v in fib_levels.items()},
            'volume_ratio': round(volume_ratio, 2),
            'sentiment': round(sentiment, 2),
            'fundamentals_score': round(fundamentals_score, 1),
            'price_change_1d': round(price_change_1d, 2),
            'price_change_5d': round(price_change_5d, 2),
            'atr': round(current_atr, 2)
        }

        buy_conditions = []
        buy_score = 0

        # Technical scoring
        if current_price <= fib_levels['level_618'] * 1.02:
            buy_conditions.append("Near Golden Ratio (61.8%)")
            buy_score += 25
        elif current_price <= fib_levels['level_500'] * 1.02:
            buy_conditions.append("At Fib 50%")
            buy_score += 20

        if current_rsi <= self.rsi_oversold:
            buy_conditions.append(f"RSI oversold ({current_rsi:.1f})")
            buy_score += 20
        elif current_rsi <= 40:
            buy_conditions.append(f"RSI < 40")
            buy_score += 10

        if ema_short > ema_long:
            buy_conditions.append("EMA uptrend")
            buy_score += 20
        elif ema_short > ema_long * 0.99:
            buy_conditions.append("EMA near crossover")
            buy_score += 10

        if volume_ratio >= self.volume_threshold:
            buy_conditions.append(f"Volume {volume_ratio:.1f}x")
            buy_score += 10

        if current_price <= bb_lower:
            buy_conditions.append("At lower BB")
            buy_score += 8

        if sentiment > 0.2:
            buy_conditions.append(f"Sentiment +{sentiment:.2f}")
            buy_score += 7

        # ✅ NEW: Fundamentals contribution
        if fundamentals_score > 0:
            fundamental_points = int(fundamentals_score * 0.20)  # Max 20 points from fundamentals
            if fundamental_points >= 10:
                buy_conditions.append(f"Strong fundamentals ({fundamentals_score:.0f}/100)")
            buy_score += fundamental_points

        # Sell scoring
        sell_conditions = []
        sell_score = 0

        if current_price >= fib_levels['level_618'] * 0.98:
            sell_conditions.append("Near Golden Ratio resistance")
            sell_score += 25
        elif current_price >= fib_levels['level_786'] * 0.98:
            sell_conditions.append("At Fib 78.6%")
            sell_score += 20

        if current_rsi >= self.rsi_overbought:
            sell_conditions.append(f"RSI overbought ({current_rsi:.1f})")
            sell_score += 20
        elif current_rsi >= 60:
            sell_conditions.append(f"RSI > 60")
            sell_score += 10

        if ema_short < ema_long:
            sell_conditions.append("EMA downtrend")
            sell_score += 20
        elif ema_short < ema_long * 1.01:
            sell_conditions.append("EMA near crossover")
            sell_score += 10

        if volume_ratio >= self.volume_threshold:
            sell_conditions.append(f"Volume {volume_ratio:.1f}x")
            sell_score += 10

        if current_price >= bb_upper:
            sell_conditions.append("At upper BB")
            sell_score += 8

        if sentiment < -0.2:
            sell_conditions.append(f"Sentiment {sentiment:.2f}")
            sell_score += 7

        # ✅ NEW: Weak fundamentals support SELL
        if fundamentals_score > 0 and fundamentals_score < 40:
            sell_conditions.append(f"Weak fundamentals ({fundamentals_score:.0f}/100)")
            sell_score += 10

        # Determine signal
        if buy_score > sell_score and buy_score >= 50:
            signal['action'] = 'BUY'
            signal['confidence'] = min(0.95, buy_score / 100)
            signal['reason'] = ' + '.join(buy_conditions[:3])  # Top 3 reasons
            
            # ✅ FIXED: ATR-based stops (Peer Review recommendation)
            atr_multiplier_sl = self.config.get('atr_stop_loss_multiplier', 1.5)
            atr_multiplier_target = self.config.get('atr_target_multiplier', 3.0)
            
            signal['stop_loss'] = round(current_price - (atr_multiplier_sl * current_atr), 2)
            signal['target'] = round(current_price + (atr_multiplier_target * current_atr), 2)
            
        elif sell_score > buy_score and sell_score >= 50:
            signal['action'] = 'SELL'
            signal['confidence'] = min(0.95, sell_score / 100)
            signal['reason'] = ' + '.join(sell_conditions[:3])
            
            # ✅ FIXED: ATR-based stops for SHORT
            atr_multiplier_sl = self.config.get('atr_stop_loss_multiplier', 1.5)
            atr_multiplier_target = self.config.get('atr_target_multiplier', 3.0)
            
            signal['stop_loss'] = round(current_price + (atr_multiplier_sl * current_atr), 2)
            signal['target'] = round(current_price - (atr_multiplier_target * current_atr), 2)
        else:
            logger.debug(f"No clear signal for {symbol} - Buy: {buy_score}, Sell: {sell_score}")

        return signal

    def analyze_watchlist(self, symbols, exchange="NSE"):
        """Analyze multiple symbols with rate limiting and progress tracking"""
        logger.info(f"Starting watchlist analysis for {len(symbols)} symbols")
        signals = []
        
        total_symbols = len(symbols)
        print(f"📊 Analyzing {total_symbols} stocks with rate limiting...")
        
        for idx, sym in enumerate(symbols):
            if idx > 0 and idx % 10 == 0:
                print(f"  ⏳ Progress: {idx}/{total_symbols} analyzed... ({len(signals)} signals)")
            
            try:
                signal = self.analyze_symbol(sym, exchange)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error analyzing {sym}: {e}")
            
            # ✅ FIXED: Single rate limit delay (removed duplicate)
            if idx < total_symbols - 1:
                time.sleep(0.25)
        
        signals.sort(key=lambda x: x['confidence'], reverse=True)
        logger.info(f"Analysis complete: {len(signals)} valid signals found")
        
        top_signals = signals[:10]
        print(f"✅ Returning top {len(top_signals)} signals")
        return top_signals

    def run_premarket_analysis(self, symbols, exchange="NSE"):
        """Run pre-market analysis (7:00 AM - 9:15 AM IST)"""
        current_time = datetime.now().time()
        premarket_start = dt_time(7, 0)  # ✅ FIXED: Use dt_time
        premarket_end = dt_time(9, 15)
        is_premarket = premarket_start <= current_time <= premarket_end
        
        logger.info(f"Pre-market analysis - Time: {current_time.strftime('%H:%M:%S')}, Is pre-market: {is_premarket}")
        
        signals = self.analyze_watchlist(symbols, exchange)
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'is_premarket_hours': is_premarket,
            'total_symbols_analyzed': len(symbols),
            'signals_found': len(signals),
            'high_confidence_signals': len([s for s in signals if s['confidence'] >= 0.8]),
            'signals': signals
        }
        
        logger.info(f"Pre-market complete: {result['signals_found']} signals, {result['high_confidence_signals']} high confidence")
        return result

    def get_market_overview(self):
        """Get overview of major indices"""
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
                            'trend': 'UP' if change > 0 else 'DOWN' if change < 0 else 'FLAT'
                        }
                        logger.info(f"{index}: ₹{ltp:.2f} ({change_pct:+.2f}%)")
            except Exception as e:
                logger.error(f"Error getting overview for {index}: {e}")
        
        return overview