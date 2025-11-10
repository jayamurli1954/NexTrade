"""
Candlestick Pattern Detection Module

Detects common bullish and bearish candlestick patterns:
- Doji (Indecision)
- Hammer (Bullish reversal)
- Shooting Star (Bearish reversal)
- Bullish/Bearish Engulfing
- Morning Star (Bullish reversal)
- Evening Star (Bearish reversal)
- Hanging Man (Bearish at top)
- Inverted Hammer (Bullish at bottom)

Each pattern returns:
- Pattern name
- Signal (BULLISH/BEARISH/NEUTRAL)
- Strength (0-15 points for scoring)
"""

import pandas as pd
import numpy as np


class CandlestickPatterns:
    """
    Comprehensive candlestick pattern detection

    Pattern Strength Levels:
    - Strong reversal patterns: 12-15 points (Morning/Evening Star)
    - Medium reversal patterns: 8-10 points (Engulfing)
    - Weak reversal patterns: 5-7 points (Hammer, Shooting Star)
    - Indecision patterns: 3-5 points (Doji)
    """

    @staticmethod
    def detect_doji(open_price, high, low, close):
        """
        Doji: Open H Close (body < 10% of range)

        Indicates indecision in the market
        - At support: Potential bullish reversal
        - At resistance: Potential bearish reversal

        Returns: True if Doji detected
        """
        body = abs(close - open_price)
        range_size = high - low

        if range_size == 0:
            return False

        # Body is less than 10% of total range
        is_doji = body <= (range_size * 0.1)

        return is_doji

    @staticmethod
    def detect_hammer(open_price, high, low, close, trend='DOWN'):
        """
        Hammer (Bullish reversal at bottom of downtrend):
        - Small body at top of range
        - Long lower shadow (at least 2x body size)
        - Little or no upper shadow
        - Body color doesn't matter much

        Returns: True if Hammer detected
        """
        body = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)

        if body == 0:
            body = 0.01  # Avoid division by zero

        is_hammer = (
            lower_shadow >= (body * 2) and  # Long lower shadow
            upper_shadow <= (body * 0.5) and  # Small/no upper shadow
            body > 0 and  # Has a body
            trend == 'DOWN'  # Should appear in downtrend
        )

        return is_hammer

    @staticmethod
    def detect_inverted_hammer(open_price, high, low, close, trend='DOWN'):
        """
        Inverted Hammer (Bullish reversal at bottom):
        - Small body at bottom of range
        - Long upper shadow (at least 2x body size)
        - Little or no lower shadow

        Returns: True if Inverted Hammer detected
        """
        body = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low

        if body == 0:
            body = 0.01

        is_inverted_hammer = (
            upper_shadow >= (body * 2) and
            lower_shadow <= (body * 0.5) and
            body > 0 and
            trend == 'DOWN'
        )

        return is_inverted_hammer

    @staticmethod
    def detect_shooting_star(open_price, high, low, close, trend='UP'):
        """
        Shooting Star (Bearish reversal at top of uptrend):
        - Small body at bottom of range
        - Long upper shadow (at least 2x body size)
        - Little or no lower shadow
        - Appears after uptrend

        Returns: True if Shooting Star detected
        """
        body = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low

        if body == 0:
            body = 0.01

        is_shooting_star = (
            upper_shadow >= (body * 2) and
            lower_shadow <= (body * 0.5) and
            body > 0 and
            trend == 'UP'  # Should appear in uptrend
        )

        return is_shooting_star

    @staticmethod
    def detect_hanging_man(open_price, high, low, close, trend='UP'):
        """
        Hanging Man (Bearish reversal at top):
        Same structure as Hammer but appears at top of uptrend

        Returns: True if Hanging Man detected
        """
        body = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)

        if body == 0:
            body = 0.01

        is_hanging_man = (
            lower_shadow >= (body * 2) and
            upper_shadow <= (body * 0.5) and
            body > 0 and
            trend == 'UP'  # Must appear in uptrend
        )

        return is_hanging_man

    @staticmethod
    def detect_engulfing(df, idx):
        """
        Bullish Engulfing: Small red candle followed by large green candle
        Bearish Engulfing: Small green candle followed by large red candle

        Args:
            df: DataFrame with OHLC data
            idx: Current candle index

        Returns:
            'BULLISH_ENGULFING', 'BEARISH_ENGULFING', or None
        """
        if idx < 1:
            return None

        prev_open = df['open'].iloc[idx-1]
        prev_close = df['close'].iloc[idx-1]
        curr_open = df['open'].iloc[idx]
        curr_close = df['close'].iloc[idx]

        # Bullish engulfing (reversal pattern at bottom)
        if prev_close < prev_open and curr_close > curr_open:  # Prev red, curr green
            if curr_open <= prev_close and curr_close >= prev_open:  # Current engulfs previous
                return 'BULLISH_ENGULFING'

        # Bearish engulfing (reversal pattern at top)
        if prev_close > prev_open and curr_close < curr_open:  # Prev green, curr red
            if curr_open >= prev_close and curr_close <= prev_open:  # Current engulfs previous
                return 'BEARISH_ENGULFING'

        return None

    @staticmethod
    def detect_morning_star(df, idx):
        """
        Morning Star (Strong bullish reversal - 3-candle pattern):

        Day 1: Large bearish candle (downtrend continues)
        Day 2: Small body (doji or spinning top) - indecision
        Day 3: Large bullish candle (reversal confirmed)

        Returns: True if Morning Star detected
        """
        if idx < 2:
            return False

        day1_open = df['open'].iloc[idx-2]
        day1_close = df['close'].iloc[idx-2]
        day1_high = df['high'].iloc[idx-2]
        day1_low = df['low'].iloc[idx-2]

        day2_open = df['open'].iloc[idx-1]
        day2_close = df['close'].iloc[idx-1]
        day2_high = df['high'].iloc[idx-1]
        day2_low = df['low'].iloc[idx-1]

        day3_open = df['open'].iloc[idx]
        day3_close = df['close'].iloc[idx]
        day3_high = df['high'].iloc[idx]
        day3_low = df['low'].iloc[idx]

        # Day 1: Large bearish candle
        day1_body = abs(day1_close - day1_open)
        if not (day1_close < day1_open and day1_body > 0):
            return False

        # Day 2: Small body (indecision)
        day2_body = abs(day2_close - day2_open)
        if day2_body > day1_body * 0.3:  # Body should be small (< 30% of day 1)
            return False

        # Day 2 should gap down or be within day 1 range
        if day2_high > day1_close:
            return False

        # Day 3: Large bullish candle
        day3_body = abs(day3_close - day3_open)
        if not (day3_close > day3_open and day3_body > day1_body * 0.5):
            return False

        # Day 3 should close well into day 1's body
        if day3_close <= (day1_open + day1_close) / 2:
            return False

        return True

    @staticmethod
    def detect_evening_star(df, idx):
        """
        Evening Star (Strong bearish reversal - 3-candle pattern):

        Day 1: Large bullish candle (uptrend continues)
        Day 2: Small body (indecision)
        Day 3: Large bearish candle (reversal confirmed)

        Returns: True if Evening Star detected
        """
        if idx < 2:
            return False

        day1_open = df['open'].iloc[idx-2]
        day1_close = df['close'].iloc[idx-2]
        day1_high = df['high'].iloc[idx-2]
        day1_low = df['low'].iloc[idx-2]

        day2_open = df['open'].iloc[idx-1]
        day2_close = df['close'].iloc[idx-1]
        day2_high = df['high'].iloc[idx-1]
        day2_low = df['low'].iloc[idx-1]

        day3_open = df['open'].iloc[idx]
        day3_close = df['close'].iloc[idx]
        day3_high = df['high'].iloc[idx]
        day3_low = df['low'].iloc[idx]

        # Day 1: Large bullish candle
        day1_body = abs(day1_close - day1_open)
        if not (day1_close > day1_open and day1_body > 0):
            return False

        # Day 2: Small body (indecision)
        day2_body = abs(day2_close - day2_open)
        if day2_body > day1_body * 0.3:
            return False

        # Day 2 should gap up or be within day 1 range
        if day2_low < day1_close:
            return False

        # Day 3: Large bearish candle
        day3_body = abs(day3_close - day3_open)
        if not (day3_close < day3_open and day3_body > day1_body * 0.5):
            return False

        # Day 3 should close well into day 1's body
        if day3_close >= (day1_open + day1_close) / 2:
            return False

        return True

    @staticmethod
    def determine_trend(df, idx, period=10):
        """
        Determine if current position is in uptrend or downtrend

        Args:
            df: DataFrame with close prices
            idx: Current index
            period: Lookback period for trend

        Returns:
            'UP', 'DOWN', or 'NEUTRAL'
        """
        if idx < period:
            return 'NEUTRAL'

        # Compare recent prices to earlier prices
        recent_avg = df['close'].iloc[idx-5:idx].mean()
        earlier_avg = df['close'].iloc[idx-period:idx-5].mean()

        if recent_avg > earlier_avg * 1.02:  # 2% higher
            return 'UP'
        elif recent_avg < earlier_avg * 0.98:  # 2% lower
            return 'DOWN'
        else:
            return 'NEUTRAL'

    @staticmethod
    def analyze_patterns(df):
        """
        Analyze entire dataframe and return detected patterns

        Args:
            df: DataFrame with OHLC data (open, high, low, close)

        Returns:
            List of detected patterns with:
            - pattern: Pattern name
            - signal: BULLISH/BEARISH/NEUTRAL
            - strength: Points to add to signal score (0-15)
            - description: Human-readable description
        """
        if len(df) < 3:
            return []

        patterns = []
        idx = len(df) - 1  # Current (latest) candle

        # Get current candle OHLC
        curr_open = df['open'].iloc[idx]
        curr_high = df['high'].iloc[idx]
        curr_low = df['low'].iloc[idx]
        curr_close = df['close'].iloc[idx]

        # Determine trend
        trend = CandlestickPatterns.determine_trend(df, idx)

        # Check for 3-candle patterns first (strongest signals)
        if CandlestickPatterns.detect_morning_star(df, idx):
            patterns.append({
                'pattern': 'MORNING_STAR',
                'signal': 'BULLISH',
                'strength': 15,
                'description': 'Strong bullish reversal (3-candle pattern)'
            })

        if CandlestickPatterns.detect_evening_star(df, idx):
            patterns.append({
                'pattern': 'EVENING_STAR',
                'signal': 'BEARISH',
                'strength': 15,
                'description': 'Strong bearish reversal (3-candle pattern)'
            })

        # Check for 2-candle patterns (medium strength)
        engulfing = CandlestickPatterns.detect_engulfing(df, idx)
        if engulfing == 'BULLISH_ENGULFING':
            patterns.append({
                'pattern': 'BULLISH_ENGULFING',
                'signal': 'BULLISH',
                'strength': 10,
                'description': 'Bullish engulfing pattern - reversal signal'
            })
        elif engulfing == 'BEARISH_ENGULFING':
            patterns.append({
                'pattern': 'BEARISH_ENGULFING',
                'signal': 'BEARISH',
                'strength': 10,
                'description': 'Bearish engulfing pattern - reversal signal'
            })

        # Check for single-candle patterns
        if CandlestickPatterns.detect_hammer(curr_open, curr_high, curr_low, curr_close, trend):
            patterns.append({
                'pattern': 'HAMMER',
                'signal': 'BULLISH',
                'strength': 7,
                'description': 'Hammer - bullish reversal at bottom'
            })

        if CandlestickPatterns.detect_inverted_hammer(curr_open, curr_high, curr_low, curr_close, trend):
            patterns.append({
                'pattern': 'INVERTED_HAMMER',
                'signal': 'BULLISH',
                'strength': 6,
                'description': 'Inverted Hammer - potential bullish reversal'
            })

        if CandlestickPatterns.detect_shooting_star(curr_open, curr_high, curr_low, curr_close, trend):
            patterns.append({
                'pattern': 'SHOOTING_STAR',
                'signal': 'BEARISH',
                'strength': 7,
                'description': 'Shooting Star - bearish reversal at top'
            })

        if CandlestickPatterns.detect_hanging_man(curr_open, curr_high, curr_low, curr_close, trend):
            patterns.append({
                'pattern': 'HANGING_MAN',
                'signal': 'BEARISH',
                'strength': 6,
                'description': 'Hanging Man - bearish reversal at top'
            })

        if CandlestickPatterns.detect_doji(curr_open, curr_high, curr_low, curr_close):
            # Doji signal depends on context (trend)
            if trend == 'UP':
                signal = 'BEARISH'
                desc = 'Doji at top - potential reversal'
            elif trend == 'DOWN':
                signal = 'BULLISH'
                desc = 'Doji at bottom - potential reversal'
            else:
                signal = 'NEUTRAL'
                desc = 'Doji - indecision'

            patterns.append({
                'pattern': 'DOJI',
                'signal': signal,
                'strength': 4 if signal != 'NEUTRAL' else 2,
                'description': desc
            })

        return patterns


# Example usage and testing
if __name__ == "__main__":
    # Test with sample data
    import pandas as pd

    # Create sample OHLC data
    data = {
        'open': [100, 98, 97, 95, 94, 95, 96, 98, 99, 101],
        'high': [102, 100, 98, 97, 95, 97, 98, 100, 102, 104],
        'low': [99, 97, 96, 94, 93, 94, 95, 97, 98, 100],
        'close': [98, 97, 95, 94, 95, 96, 98, 99, 101, 103]
    }

    df = pd.DataFrame(data)

    patterns = CandlestickPatterns.analyze_patterns(df)

    print("Detected Patterns:")
    for pattern in patterns:
        print(f"- {pattern['pattern']}: {pattern['signal']} ({pattern['strength']} pts)")
        print(f"  {pattern['description']}")
