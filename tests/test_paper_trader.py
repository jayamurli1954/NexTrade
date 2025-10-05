"""
Standalone test script for PaperTrader.
Run: python test_paper_trader.py

- Buys/Sells some stocks
- Attempts invalid trades
- Shows trade history
- Simulates auto square-off at 3:15 PM
- Resets portfolio
"""

from order_manager.paper_trader import PaperTrader
from datetime import datetime

def auto_square_off(trader: PaperTrader, price_map: dict):
    """
    Close all open positions at provided prices (simulate 3:15 PM auto square-off).
    """
    print("\n=== Auto Square-off (simulating 3:15 PM) ===")
    closed = []
    for symbol, pos in list(trader.positions.items()):
        qty = pos["qty"]
        if qty > 0:
            price = price_map.get(symbol, pos["avg_price"])
            ok, msg = trader.place_order(symbol, "SELL", qty, price)
            closed.append((symbol, qty, price, ok, msg))
        elif qty < 0:  # short positions (if supported later)
            price = price_map.get(symbol, pos["avg_price"])
            ok, msg = trader.place_order(symbol, "BUY", abs(qty), price)
            closed.append((symbol, qty, price, ok, msg))

    for sym, qty, price, ok, msg in closed:
        print(f"Square-off {sym} x{qty} @ {price} => {msg}")

    print("Final portfolio after square-off:", trader.get_portfolio_summary())


def run_tests():
    trader = PaperTrader(initial_balance=100000)

    print("=== Initial State ===")
    print(trader.get_portfolio_summary())

    # Test Buy
    print("\n=== Buy 50 RELIANCE @ 2500 ===")
    ok, msg = trader.place_order("RELIANCE", "BUY", 50, 2500)
    print("Result:", ok, msg)

    # Test Sell
    print("\n=== Sell 20 RELIANCE @ 2520 ===")
    ok, msg = trader.place_order("RELIANCE", "SELL", 20, 2520)
    print("Result:", ok, msg)

    # Invalid Sell (too many)
    print("\n=== Sell 100 RELIANCE (should fail) ===")
    ok, msg = trader.place_order("RELIANCE", "SELL", 100, 2510)
    print("Result:", ok, msg)

    # Test Buy INFY
    print("\n=== Buy 30 INFY @ 1600 ===")
    ok, msg = trader.place_order("INFY", "BUY", 30, 1600)
    print("Result:", ok, msg)

    # Trade history
    print("\n=== Trade History ===")
    for trade in trader.get_trade_history():
        print(trade)

    # Auto square-off simulation
    fake_prices = {"RELIANCE": 2515, "INFY": 1610}  # assume these prices at 3:15 PM
    auto_square_off(trader, fake_prices)

    # Reset
    print("\n=== Reset Portfolio ===")
    ok, msg = trader.reset_portfolio()
    print("Reset:", ok, msg)
    print(trader.get_portfolio_summary())


if __name__ == "__main__":
    run_tests()
