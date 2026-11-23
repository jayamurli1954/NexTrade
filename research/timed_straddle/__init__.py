"""
Timed intraday short straddle/strangle — research backtest only.

Synthetic option premiums (Black-Scholes, IV = India VIX x ratio calibrated on real NSE
option prices) replayed over 5m index bars. Does not place or authorise any orders.
"""

from research.timed_straddle.engine import TimedStraddleEngine
from research.timed_straddle.params import TimedStraddleParams

__all__ = ["TimedStraddleEngine", "TimedStraddleParams"]
