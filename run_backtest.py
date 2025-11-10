#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Backtest Runner
Easy-to-use script for running backtests with your enhanced analyzer

Usage:
    python run_backtest.py

Customize:
    Edit the BACKTEST_CONFIG section below to change parameters
"""

import sys
from datetime import datetime, timedelta
from backtesting.enhanced_backtest_engine import EnhancedBacktestEngine

# ============================================================================
# BACKTEST CONFIGURATION - CUSTOMIZE THIS
# ============================================================================

BACKTEST_CONFIG = {
    # Capital settings
    'initial_capital': 100000,  # Starting capital in ₹

    # Position sizing
    'position_size_method': 'fixed_rupees',  # 'fixed_rupees' or 'risk_pct'
    'position_size_value': 100000,  # ₹100,000 per trade (or 2% if using risk_pct)

    # Features
    'enable_fundamentals': False,  # Set True for Screener.in (slower but more accurate)

    # Test period
    'start_date': '2024-01-01',  # YYYY-MM-DD
    'end_date': '2024-11-01',    # YYYY-MM-DD
    'interval': '1d',             # '1d' for daily, '1h' for hourly

    # Symbols to test
    'symbols': [
        # Large Cap
        'RELIANCE',
        'TCS',
        'INFY',
        'HDFCBANK',
        'ICICIBANK',
        'HINDUNILVR',
        'ITC',
        'SBIN',
        'BHARTIARTL',
        'KOTAKBANK',

        # Mid Cap
        'TATAPOWER',
        'ADANIPORTS',
        'TATAMOTORS',
        'SUNPHARMA',
        'LT',
    ]
}

# ============================================================================
# QUICK PRESETS - Uncomment to use
# ============================================================================

# # Conservative (Lower risk, slower)
# BACKTEST_CONFIG.update({
#     'position_size_method': 'risk_pct',
#     'position_size_value': 1.0,  # Risk 1% per trade
#     'enable_fundamentals': True,
# })

# # Aggressive (Higher risk, faster)
# BACKTEST_CONFIG.update({
#     'position_size_method': 'fixed_rupees',
#     'position_size_value': 200000,  # ₹200,000 per trade
#     'enable_fundamentals': False,
# })

# # Last 6 months only
# BACKTEST_CONFIG.update({
#     'start_date': (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d'),
#     'end_date': datetime.now().strftime('%Y-%m-%d'),
# })

# # Last 1 year
# BACKTEST_CONFIG.update({
#     'start_date': (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),
#     'end_date': datetime.now().strftime('%Y-%m-%d'),
# })

# ============================================================================
# RUN BACKTEST
# ============================================================================

def main():
    print("\n" + "="*80)
    print("ENHANCED BACKTESTING SYSTEM")
    print("="*80)
    print("\nConfiguration:")
    print(f"  Initial Capital: ₹{BACKTEST_CONFIG['initial_capital']:,}")
    print(f"  Position Sizing: {BACKTEST_CONFIG['position_size_method']} = {BACKTEST_CONFIG['position_size_value']}")
    print(f"  Fundamentals: {'ENABLED (Screener.in)' if BACKTEST_CONFIG['enable_fundamentals'] else 'DISABLED (faster)'}")
    print(f"  Period: {BACKTEST_CONFIG['start_date']} to {BACKTEST_CONFIG['end_date']}")
    print(f"  Symbols: {len(BACKTEST_CONFIG['symbols'])} stocks")
    print(f"  Interval: {BACKTEST_CONFIG['interval']}")
    print("="*80)

    # Confirm
    response = input("\nProceed with backtest? (y/n): ")
    if response.lower() != 'y':
        print("Backtest cancelled.")
        return

    try:
        # Initialize engine
        engine = EnhancedBacktestEngine(
            initial_capital=BACKTEST_CONFIG['initial_capital'],
            position_size_method=BACKTEST_CONFIG['position_size_method'],
            position_size_value=BACKTEST_CONFIG['position_size_value'],
            enable_fundamentals=BACKTEST_CONFIG['enable_fundamentals']
        )

        # Run backtest
        print("\nStarting backtest...")
        report = engine.run_backtest(
            symbols=BACKTEST_CONFIG['symbols'],
            start_date=BACKTEST_CONFIG['start_date'],
            end_date=BACKTEST_CONFIG['end_date'],
            interval=BACKTEST_CONFIG['interval']
        )

        # Save report
        report_file = engine.save_report(report)

        # Print detailed summary
        print_detailed_summary(report)

        print(f"\n✅ Backtest complete! Report saved to: {report_file}")
        print(f"   Trades file: backtesting/results/trades_*.xlsx")

    except Exception as e:
        print(f"\n❌ Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


def print_detailed_summary(report):
    """Print comprehensive backtest results"""
    summary = report['summary']

    print("\n" + "="*80)
    print("BACKTEST RESULTS")
    print("="*80)

    # Performance Overview
    print("\n📊 PERFORMANCE OVERVIEW")
    print("-" * 80)
    print(f"  Initial Capital       : ₹{summary['initial_capital']:,.0f}")
    print(f"  Final Capital         : ₹{summary['final_capital']:,.0f}")
    print(f"  Net P&L               : ₹{summary['net_pnl']:,.0f}")
    print(f"  Total Return          : {summary['total_return_pct']:+.2f}%")
    print(f"  Max Drawdown          : {summary['max_drawdown_pct']:.2f}%")

    # Trade Statistics
    print("\n📈 TRADE STATISTICS")
    print("-" * 80)
    print(f"  Total Trades          : {summary['total_trades']}")
    print(f"  Winning Trades        : {summary['winning_trades']} ({summary['win_rate']:.1f}%)")
    print(f"  Losing Trades         : {summary['losing_trades']} ({100-summary['win_rate']:.1f}%)")
    print(f"  Win Rate              : {summary['win_rate']:.1f}%")

    # P&L Analysis
    print("\n💰 PROFIT & LOSS")
    print("-" * 80)
    print(f"  Total Profit          : ₹{summary['total_profit']:,.0f}")
    print(f"  Total Loss            : ₹{summary['total_loss']:,.0f}")
    print(f"  Average Win           : ₹{summary['avg_win']:,.0f}")
    print(f"  Average Loss          : ₹{summary['avg_loss']:,.0f}")
    print(f"  Profit Factor         : {summary['profit_factor']:.2f}")
    print(f"  Expectancy            : ₹{summary['expectancy']:,.0f} per trade")

    # Risk Metrics
    print("\n⚠️  RISK METRICS")
    print("-" * 80)
    print(f"  Sharpe Ratio          : {summary['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown          : ₹{summary['max_drawdown']:,.0f} ({summary['max_drawdown_pct']:.2f}%)")

    # Trade Analysis
    if 'trade_analysis' in report:
        analysis = report['trade_analysis']

        print("\n🔍 TRADE ANALYSIS")
        print("-" * 80)

        if 'avg_hold_days_winners' in analysis:
            print(f"  Avg Hold (Winners)    : {analysis['avg_hold_days_winners']:.1f} days")
        if 'avg_hold_days_losers' in analysis:
            print(f"  Avg Hold (Losers)     : {analysis['avg_hold_days_losers']:.1f} days")

        # Best/Worst trades
        if 'best_trade' in analysis and analysis['best_trade']:
            best = analysis['best_trade']
            print(f"\n  🏆 Best Trade:")
            print(f"     {best.get('symbol', 'N/A')} | P&L: ₹{best.get('pnl', 0):,.0f} ({best.get('pnl_pct', 0):+.1f}%)")

        if 'worst_trade' in analysis and analysis['worst_trade']:
            worst = analysis['worst_trade']
            print(f"\n  ⚠️  Worst Trade:")
            print(f"     {worst.get('symbol', 'N/A')} | P&L: ₹{worst.get('pnl', 0):,.0f} ({worst.get('pnl_pct', 0):+.1f}%)")

    # Rating
    print("\n" + "="*80)
    print("STRATEGY RATING")
    print("="*80)
    rating = rate_strategy(summary)
    print(f"  {rating['emoji']} {rating['grade']}: {rating['description']}")
    print(f"  {rating['recommendation']}")
    print("="*80)


def rate_strategy(summary):
    """Rate the strategy based on metrics"""
    score = 0

    # Win rate (max 25 points)
    if summary['win_rate'] >= 60:
        score += 25
    elif summary['win_rate'] >= 50:
        score += 20
    elif summary['win_rate'] >= 45:
        score += 15
    elif summary['win_rate'] >= 40:
        score += 10

    # Profit factor (max 25 points)
    pf = summary['profit_factor']
    if pf >= 2.0:
        score += 25
    elif pf >= 1.5:
        score += 20
    elif pf >= 1.2:
        score += 15
    elif pf >= 1.0:
        score += 10

    # Sharpe ratio (max 25 points)
    sharpe = summary['sharpe_ratio']
    if sharpe >= 2.0:
        score += 25
    elif sharpe >= 1.5:
        score += 20
    elif sharpe >= 1.0:
        score += 15
    elif sharpe >= 0.5:
        score += 10

    # Total return (max 25 points)
    ret = summary['total_return_pct']
    if ret >= 30:
        score += 25
    elif ret >= 20:
        score += 20
    elif ret >= 10:
        score += 15
    elif ret >= 5:
        score += 10
    elif ret >= 0:
        score += 5

    # Grade
    if score >= 85:
        return {
            'grade': 'EXCELLENT',
            'emoji': '🌟',
            'description': 'Outstanding performance! This strategy is highly profitable.',
            'recommendation': '✅ RECOMMENDED for live trading with proper risk management.'
        }
    elif score >= 70:
        return {
            'grade': 'GOOD',
            'emoji': '✅',
            'description': 'Solid performance with good risk-adjusted returns.',
            'recommendation': '⚠️  Consider live trading with conservative position sizing.'
        }
    elif score >= 50:
        return {
            'grade': 'FAIR',
            'emoji': '⚠️',
            'description': 'Moderate performance. Strategy needs optimization.',
            'recommendation': '🔧 Optimize parameters before live trading.'
        }
    elif score >= 30:
        return {
            'grade': 'WEAK',
            'emoji': '❌',
            'description': 'Below-average performance with questionable profitability.',
            'recommendation': '🛑 NOT recommended for live trading. Needs major improvements.'
        }
    else:
        return {
            'grade': 'POOR',
            'emoji': '🚫',
            'description': 'Poor performance. Strategy is not profitable.',
            'recommendation': '🚫 DO NOT use for live trading. Complete strategy overhaul needed.'
        }


if __name__ == "__main__":
    sys.exit(main())
