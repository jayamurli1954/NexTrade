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