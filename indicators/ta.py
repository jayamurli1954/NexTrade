# indicators/ta.py
import pandas as pd
import numpy as np


def ema(series: pd.Series, span: int):
    if len(series) < span:
        return pd.Series([np.nan] * len(series), index=series.index)
    return series.ewm(span=span, adjust=False).mean()

def sma(series: pd.Series, period: int):
    if len(series) < period:
        return pd.Series([np.nan] * len(series), index=series.index)
    return series.rolling(period).mean()

def rsi(series: pd.Series, period: int = 14):
    if len(series) < period + 1:
        return pd.Series([np.nan] * len(series), index=series.index)
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.ewm(com=period-1, adjust=False).mean()
    ma_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ma_up / ma_down
    return 100 - (100/(1+rs))

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def fibonacci_retracement(high, low):
    diff = high - low
    levels = {
        'level_236': low + diff * 0.236,
        'level_382': low + diff * 0.382,
        'level_500': low + diff * 0.500,
        'level_618': low + diff * 0.618,
        'level_786': low + diff * 0.786
    }
    return levels

def bollinger_bands(series: pd.Series, period: int = 20, std_dev: int = 2):
    if len(series) < period:
        return pd.Series([np.nan] * len(series)), pd.Series([np.nan] * len(series)), pd.Series([np.nan] * len(series))
    sma_line = sma(series, period)
    std = series.rolling(period).std()
    upper = sma_line + (std * std_dev)
    lower = sma_line - (std * std_dev)
    return upper, sma_line, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """
    Average True Range (ATR) - Measures volatility
    Higher ATR = Higher volatility
    """
    if len(high) < period + 1:
        return pd.Series([np.nan] * len(high), index=high.index)

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_result = tr.ewm(span=period, adjust=False).mean()
    return atr_result


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    """
    Stochastic Oscillator - Momentum indicator
    %K > 80: Overbought
    %K < 20: Oversold
    """
    if len(close) < period:
        return pd.Series([np.nan] * len(close)), pd.Series([np.nan] * len(close))

    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()

    k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    k = k.rolling(smooth_k).mean()  # Smooth %K
    d = k.rolling(smooth_d).mean()  # %D is SMA of %K

    return k, d


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """
    Average Directional Index (ADX) - Trend strength indicator
    ADX > 25: Strong trend
    ADX < 20: Weak/no trend
    """
    if len(close) < period + 1:
        return pd.Series([np.nan] * len(close))

    # Calculate +DM and -DM
    high_diff = high.diff()
    low_diff = -low.diff()

    plus_dm = high_diff.copy()
    plus_dm[~((high_diff > low_diff) & (high_diff > 0))] = 0

    minus_dm = low_diff.copy()
    minus_dm[~((low_diff > high_diff) & (low_diff > 0))] = 0

    # Calculate ATR
    atr_value = atr(high, low, close, period)

    # Calculate +DI and -DI
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr_value)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr_value)

    # Calculate DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)

    # Calculate ADX (smoothed DX)
    adx_result = dx.ewm(span=period, adjust=False).mean()

    return adx_result


def obv(close: pd.Series, volume: pd.Series):
    """
    On-Balance Volume (OBV) - Volume-based momentum indicator
    Rising OBV = Bullish pressure
    Falling OBV = Bearish pressure
    """
    if len(close) < 2:
        return pd.Series([np.nan] * len(close))

    obv_values = [0]
    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i-1]:
            obv_values.append(obv_values[-1] + volume.iloc[i])
        elif close.iloc[i] < close.iloc[i-1]:
            obv_values.append(obv_values[-1] - volume.iloc[i])
        else:
            obv_values.append(obv_values[-1])

    return pd.Series(obv_values, index=close.index)


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series):
    """
    Volume Weighted Average Price (VWAP)
    Price above VWAP = Bullish
    Price below VWAP = Bearish
    """
    typical_price = (high + low + close) / 3
    vwap_result = (typical_price * volume).cumsum() / volume.cumsum()
    return vwap_result


def support_resistance(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20):
    """
    Calculate support and resistance levels using pivot points
    """
    if len(close) < window:
        return None, None

    # Recent high and low
    resistance = high.rolling(window).max().iloc[-1]
    support = low.rolling(window).min().iloc[-1]

    return support, resistance