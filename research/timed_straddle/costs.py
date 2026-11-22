"""NSE index-options transaction costs (per fill), current statutory rates — research approximation."""

from __future__ import annotations

# Rates effective from Oct/Nov 2024 (NSE circular + Finance Act 2024).
STT_SELL_PCT = 0.10          # % of premium on option SELL
EXCHANGE_TXN_PCT = 0.03503   # % of premium turnover (NSE options)
SEBI_PER_CRORE = 10.0        # INR per crore of turnover
STAMP_BUY_PCT = 0.003        # % of premium on BUY
GST_PCT = 18.0               # on brokerage + exchange txn + SEBI fee


def fill_cost(price: float, qty: int, side: str, brokerage: float = 20.0) -> float:
    """Charges in INR for one option fill. ``side`` is 'BUY' or 'SELL'."""
    turnover = price * qty
    exch = turnover * EXCHANGE_TXN_PCT / 100.0
    sebi = turnover * SEBI_PER_CRORE / 1e7
    stt = turnover * STT_SELL_PCT / 100.0 if side == "SELL" else 0.0
    stamp = turnover * STAMP_BUY_PCT / 100.0 if side == "BUY" else 0.0
    gst = (brokerage + exch + sebi) * GST_PCT / 100.0
    return brokerage + exch + sebi + stt + stamp + gst
