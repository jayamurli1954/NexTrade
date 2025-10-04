# analyzer/enhanced_analyzer.py - COMPLETE FILE WITH LIVE LTP
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.ta import rsi, ema, sma, fibonacci_retracement, bollinger_bands
import pandas as pd
import numpy as np
import logging
from datetime import datetime, time, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import requests

logger = logging.getLogger("EnhancedAnalyzer")


class EnhancedAnalyzer:
    def __init__(self, data_provider):
        self.data_provider = data_provider
        self.golden_ratio = 1.618
        self.confidence_threshold = 0.65
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.volume_threshold = 1.2
        self.ema_short_period = 8
        self.ema_long_period = 21
        self.analysis_period = 50
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        self.newsapi_key = "your_newsapi_key"  # Replace with real key from newsapi.org

    def analyze_symbol(self, symbol, exchange="NSE"):
        """Analyze a single symbol with LIVE LTP"""
        try:
            # Get historical data for indicators
            df = self.data_provider.get_historical(symbol=symbol, exchange=exchange, period_days=self.analysis_period)
            if df is None or df.empty or len(df) < 30:
                logger.warning(f"Insufficient data for {symbol}")
                return None

            close_prices = df['close'].astype(float)
            high_prices = df['high'].astype(float)
            low_prices = df['low'].astype(float)
            volume = df['volume'].astype(float)

            # Calculate indicators
            rsi_values = rsi(close_prices, period=14)
            current_rsi = rsi_values.iloc[-1] if not rsi_values.empty else 50

            ema_short = ema(close_prices, self.ema_short_period)
            ema_long = ema(close_prices, self.ema_long_period)

            current_ema_short = ema_short.iloc[-1] if not ema_short.empty else close_prices.iloc[-1]
            current_ema_long = ema_long.iloc[-1] if not ema_long.empty else close_prices.iloc[-1]

            period_high = high_prices.max()
            period_low = low_prices.min()
            fib_levels = fibonacci_retracement(period_high, period_low)

            # CRITICAL FIX: Get LIVE LTP instead of using historical close
            current_price_live = self.data_provider.get_ltp(symbol, exchange)
            if current_price_live is None:
                logger.warning(f"Could not fetch live LTP for {symbol}, using last close price")
                current_price_live = close_prices.iloc[-1]
            
            logger.info(f"Analyzing {symbol} - Live LTP: ₹{current_price_live:.2f}")

            current_volume = volume.iloc[-1]
            avg_volume = volume.mean()
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            bb_upper, bb_middle, bb_lower = bollinger_bands(close_prices)
            current_bb_upper = bb_upper.iloc[-1] if not bb_upper.empty else current_price_live * 1.02
            current_bb_lower = bb_lower.iloc[-1] if not bb_lower.empty else current_price_live * 0.98

            sentiment = self._get_sentiment(symbol)

            signal_data = self._generate_golden_ratio_signal(
                symbol=symbol,
                current_price=current_price_live,  # Using LIVE price
                current_rsi=current_rsi,
                ema_short=current_ema_short,
                ema_long=current_ema_long,
                fib_levels=fib_levels,
                volume_ratio=volume_ratio,
                bb_upper=current_bb_upper,
                bb_lower=current_bb_lower,
                period_high=period_high,
                period_low=period_low,
                sentiment=sentiment
            )

            if signal_data and signal_data['confidence'] >= self.confidence_threshold:
                logger.info(f"Signal found for {symbol}: {signal_data['action']} @ ₹{current_price_live:.2f} (confidence: {signal_data['confidence']:.1%})")
                return signal_data
            else:
                logger.info(f"No high-confidence signal for {symbol} (confidence: {signal_data['confidence'] if signal_data else 0:.1%})")
                return None
        except Exception as e:
            logger.exception(f"Error analyzing {symbol}: {e}")
            return None

    def _get_sentiment(self, symbol):
        """Fetch sentiment from news (requires NewsAPI key)"""
        if self.newsapi_key == "your_newsapi_key":
            # logger.debug("Using neutral sentiment - set real NewsAPI key for live sentiment")
            return 0
        try:
            url = f"https://newsapi.org/v2/everything?q={symbol}&apiKey={self.newsapi_key}&pageSize=10"
            response = requests.get(url, timeout=5)
            news = response.json().get('articles', [])
            
            if not news:
                return 0
            
            texts = [article.get('title', '') for article in news if article.get('title')]
            scores = [self.sentiment_analyzer.polarity_scores(text)['compound'] for text in texts]
            
            avg_sentiment = sum(scores) / len(scores) if scores else 0
            logger.debug(f"Sentiment for {symbol}: {avg_sentiment:.2f}")
            return avg_sentiment
        except Exception as e:
            logger.error(f"Sentiment error for {symbol}: {e}")
            return 0

    def _generate_golden_ratio_signal(self, symbol, current_price, current_rsi, ema_short, ema_long, 
                                     fib_levels, volume_ratio, bb_upper, bb_lower, period_high, 
                                     period_low, sentiment):
        """Generate trading signal based on Golden Ratio and technical indicators"""
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
            'sentiment': round(sentiment, 2)
        }

        buy_conditions = []
        buy_score = 0

        # Buy condition checks
        if current_price <= fib_levels['level_618'] * 1.02:
            buy_conditions.append("Near Golden Ratio support (61.8%)")
            buy_score += 30
        elif current_price <= fib_levels['level_382'] * 1.02:
            buy_conditions.append("At Fibonacci 38.2% support")
            buy_score += 20

        if current_rsi <= self.rsi_oversold:
            buy_conditions.append(f"RSI oversold ({current_rsi:.1f})")
            buy_score += 25

        if ema_short > ema_long:
            buy_conditions.append("EMA uptrend confirmed")
            buy_score += 20

        if volume_ratio >= self.volume_threshold:
            buy_conditions.append(f"High volume ({volume_ratio:.1f}x avg)")
            buy_score += 15

        if current_price <= bb_lower:
            buy_conditions.append("Price at lower Bollinger Band")
            buy_score += 10

        if sentiment > 0.2:
            buy_conditions.append(f"Positive sentiment ({sentiment:.2f})")
            buy_score += 10

        # Sell condition checks
        sell_conditions = []
        sell_score = 0

        if current_price >= fib_levels['level_618'] * 0.98:
            sell_conditions.append("Near Golden Ratio resistance (61.8%)")
            sell_score += 30

        if current_rsi >= self.rsi_overbought:
            sell_conditions.append(f"RSI overbought ({current_rsi:.1f})")
            sell_score += 25

        if ema_short < ema_long:
            sell_conditions.append("EMA downtrend confirmed")
            sell_score += 20

        if volume_ratio >= self.volume_threshold:
            sell_conditions.append(f"High volume ({volume_ratio:.1f}x avg)")
            sell_score += 15

        if current_price >= bb_upper:
            sell_conditions.append("Price at upper Bollinger Band")
            sell_score += 10

        if sentiment < -0.2:
            sell_conditions.append(f"Negative sentiment ({sentiment:.2f})")
            sell_score += 10

        # Determine signal
        if buy_score > sell_score and buy_score >= 50:
            signal['action'] = 'BUY'
            signal['confidence'] = min(0.95, buy_score / 100)
            signal['reason'] = ' + '.join(buy_conditions) or "Multiple buy conditions met"
            signal['target'] = round(max(fib_levels['level_618'], current_price * 1.05), 2)
            signal['stop_loss'] = round(min(fib_levels['level_382'], current_price * 0.95), 2)
        elif sell_score > buy_score and sell_score >= 50:
            signal['action'] = 'SELL'
            signal['confidence'] = min(0.95, sell_score / 100)
            signal['reason'] = ' + '.join(sell_conditions) or "Multiple sell conditions met"
            signal['target'] = round(min(fib_levels['level_382'], current_price * 0.95), 2)
            signal['stop_loss'] = round(max(fib_levels['level_618'], current_price * 1.05), 2)
        else:
            logger.debug(f"No clear signal for {symbol} - Buy: {buy_score}, Sell: {sell_score}")

        return signal

    def analyze_watchlist(self, symbols, exchange="NSE"):
        """Analyze multiple symbols and return sorted signals"""
        logger.info(f"Starting watchlist analysis for {len(symbols)} symbols")
        signals = []
        
        for sym in symbols:
            signal = self.analyze_symbol(sym, exchange)
            if signal:
                signals.append(signal)
        
        signals.sort(key=lambda x: x['confidence'], reverse=True)
        logger.info(f"Watchlist analysis complete. Found {len(signals)} signals.")
        return signals

    def run_premarket_analysis(self, symbols, exchange="NSE"):
        """Run pre-market analysis (7:00 AM - 9:15 AM)"""
        current_time = datetime.now().time()
        premarket_start = time(7, 0)
        premarket_end = time(9, 15)
        is_premarket = premarket_start <= current_time <= premarket_end
        
        logger.info(f"Pre-market analysis started. Current time: {current_time.strftime('%H:%M:%S')}")
        logger.info(f"Pre-market hours: {'YES' if is_premarket else 'NO'}")
        
        signals = self.analyze_watchlist(symbols, exchange)
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'is_premarket_hours': is_premarket,
            'total_symbols_analyzed': len(symbols),
            'signals_found': len(signals),
            'high_confidence_signals': len([s for s in signals if s['confidence'] >= 0.8]),
            'signals': signals[:10]  # Top 10 signals
        }
        
        logger.info(f"Pre-market analysis complete: {result['signals_found']} signals, {result['high_confidence_signals']} high confidence")
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
                logger.exception(f"Error getting overview for {index}: {e}")
        
        return overview