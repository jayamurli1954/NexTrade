"""
Standalone test script for PaperTrader.
Run: python -m tests.test_paper_trader
"""

from order_manager.paper_trader import PaperTrader


def run_tests():
    trader = PaperTrader(initial_cash=100000)

    print("=== Initial State ===")
    print(trader.get_summary())

    # Test Buy
    print("\n=== Buy 50 RELIANCE @ 2500 ===")
    res = trader.execute_order("RELIANCE", "BUY", 50, 2500)
    print("Result:", res)

    # Test Sell
    print("\n=== Sell 20 RELIANCE @ 2520 ===")
    res = trader.execute_order("RELIANCE", "SELL", 20, 2520)
    print("Result:", res)

    # Invalid Sell (too many)
    print("\n=== Sell 100 RELIANCE (should fail/warn) ===")
    res = trader.execute_order("RELIANCE", "SELL", 100, 2510)
    print("Result:", res)

    # Test Buy INFY
    print("\n=== Buy 30 INFY @ 1600 ===")
    res = trader.execute_order("INFY", "BUY", 30, 1600)
    print("Result:", res)

    # Positions summary
    print("\n=== Positions ===")
    print(trader.get_positions())

    print("\n=== Portfolio Value ===")
    print(trader.get_portfolio_value())

    print("\n=== Summary ===")
    print(trader.get_summary())


if __name__ == "__main__":
    run_tests()
