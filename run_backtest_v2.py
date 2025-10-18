#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BACKTEST LAUNCHER V2.0.0 - Using Yahoo Finance
Much more reliable than Angel One API

Usage:
    python run_backtest_v2.py
"""

import sys
import os
from datetime import datetime, timedelta
import json
import pandas as pd

print("=" * 70)
print("🔬 TRADING BOT - BACKTESTING ENGINE v2.0.0")
print("=" * 70)
print()
print("Using Yahoo Finance for better historical data access!")
print()

# Check if yfinance is installed
try:
    import yfinance as yf
    print("✅ yfinance is installed")
except ImportError:
    print("❌ yfinance not installed!")
    print()
    print("Installing yfinance...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    print("✅ yfinance installed successfully!")
    print()
    import yfinance as yf

from backtesting.backtest_engine_v2 import BacktestEngineV2


def load_watchlist():
    """Load watchlist"""
    with open('watchlist.json', 'r') as f:
        data = json.load(f)
        if isinstance(data, list):
            return data
        else:
            return data.get('symbols', [])


def select_test_period():
    """Let user select period"""
    print("📅 SELECT BACKTEST PERIOD:")
    print()
    print("  1. Last 6 months  (Quick test)")
    print("  2. Last 1 year    (Recommended)")
    print("  3. Last 2 years   (Good validation)")
    print("  4. Last 5 years   (Comprehensive)")
    print("  5. Custom period")
    print()
    
    choice = input("Enter your choice (1-5): ").strip()
    
    end_date = datetime.now()
    
    if choice == '1':
        start_date = end_date - timedelta(days=180)
        period_name = "6 Months"
    elif choice == '2':
        start_date = end_date - timedelta(days=365)
        period_name = "1 Year"
    elif choice == '3':
        start_date = end_date - timedelta(days=730)
        period_name = "2 Years"
    elif choice == '4':
        start_date = end_date - timedelta(days=1825)
        period_name = "5 Years"
    elif choice == '5':
        start_str = input("Enter start date (YYYY-MM-DD): ").strip()
        end_str = input("Enter end date (YYYY-MM-DD): ").strip()
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d')
        period_name = "Custom"
    else:
        print("Invalid choice, using 1 year")
        start_date = end_date - timedelta(days=365)
        period_name = "1 Year"
    
    return start_date, end_date, period_name


def select_symbols(watchlist):
    """Let user select symbols"""
    print()
    print("📊 SELECT SYMBOLS TO TEST:")
    print()
    print(f"  1. Top 5 stocks  (fastest)")
    print(f"  2. Top 10 stocks (recommended)")
    print(f"  3. Top 20 stocks")
    print(f"  4. All watchlist stocks ({len(watchlist)} symbols)")
    print(f"  5. Custom selection")
    print()
    
    choice = input("Enter your choice (1-5): ").strip()
    
    if choice == '1':
        selected = watchlist[:5]
        selection_name = "Top 5 stocks"
    elif choice == '2':
        selected = watchlist[:10]
        selection_name = "Top 10 stocks"
    elif choice == '3':
        selected = watchlist[:20]
        selection_name = "Top 20 stocks"
    elif choice == '4':
        selected = watchlist
        selection_name = f"All {len(watchlist)} stocks"
    elif choice == '5':
        print(f"\nAvailable stocks: {', '.join(watchlist[:20])}...")
        symbols_str = input("Enter symbols separated by commas: ").strip()
        selected = [s.strip().upper() for s in symbols_str.split(',')]
        selection_name = f"{len(selected)} custom stocks"
    else:
        print("Invalid choice, using top 10")
        selected = watchlist[:10]
        selection_name = "Top 10 stocks"
    
    return selected, selection_name


def print_summary(report, period_name, selection_name, duration):
    """Print results summary"""
    summary = report['summary']
    
    print()
    print("=" * 70)
    print("📊 BACKTEST RESULTS SUMMARY")
    print("=" * 70)
    print()
    
    print(f"⏱️  Duration: {duration:.1f} seconds")
    print(f"📅 Period: {period_name}")
    print(f"📊 Symbols: {selection_name}")
    print()
    
    print("💰 CAPITAL & RETURNS:")
    print(f"   Initial Capital:     ₹{summary['initial_capital']:>12,.0f}")
    print(f"   Final Capital:       ₹{summary['final_capital']:>12,.0f}")
    print(f"   Total Return:        ₹{summary['total_return']:>12,.0f}")
    print(f"   Return %:            {summary['total_return_pct']:>12.2f}%")
    print()
    
    print("📈 TRADE STATISTICS:")
    print(f"   Total Trades:        {summary['total_trades']:>12}")
    print(f"   Win Rate:            {summary['win_rate']:>12.1f}%")
    print(f"   Profit Factor:       {summary['profit_factor']:>12.2f}")
    print(f"   Sharpe Ratio:        {summary['sharpe_ratio']:>12.2f}")
    print()
    
    print("⚠️  RISK METRICS:")
    print(f"   Max Drawdown:        ₹{summary['max_drawdown']:>12,.0f}")
    print(f"   Max Drawdown %:      {summary['max_drawdown_pct']:>12.2f}%")
    print()
    
    # Verdict
    print("=" * 70)
    print("🎯 VERDICT:")
    print("=" * 70)
    
    if summary['win_rate'] >= 60 and summary['profit_factor'] >= 1.5 and summary['total_return_pct'] > 0:
        print("✅ EXCELLENT! Strategy shows strong potential!")
        print("   → Proceed to paper trading with confidence")
    elif summary['win_rate'] >= 55 and summary['profit_factor'] >= 1.2 and summary['total_return_pct'] > 0:
        print("✅ GOOD! Strategy is viable with acceptable risk")
        print("   → Proceed to paper trading cautiously")
    elif summary['win_rate'] >= 50 and summary['total_return_pct'] > 0:
        print("⚠️  MARGINAL! Strategy barely profitable")
        print("   → Consider tuning parameters before paper trading")
    else:
        print("❌ POOR! Strategy needs significant improvement")
        print("   → DO NOT proceed to paper trading")
        print("   → Revise strategy or adjust thresholds")
    
    print("=" * 70)
    print()


def show_best_trades(report, n=5):
    """Show best and worst trades"""
    trades = pd.DataFrame(report['trades'])
    
    if len(trades) == 0:
        print("⚠️  No trades executed")
        return
    
    print("🏆 BEST TRADES:")
    print("-" * 70)
    best = trades.nlargest(min(n, len(trades)), 'pnl')
    for idx, trade in best.iterrows():
        print(f"   {trade['symbol']:>10} | {trade['action']:<4} | "
              f"₹{trade['pnl']:>8,.0f} ({trade['pnl_pct']:>6.2f}%) | "
              f"{trade['exit_reason']:<10} | {trade['days_held']:>2} days")
    print()
    
    print("📉 WORST TRADES:")
    print("-" * 70)
    worst = trades.nsmallest(min(n, len(trades)), 'pnl')
    for idx, trade in worst.iterrows():
        print(f"   {trade['symbol']:>10} | {trade['action']:<4} | "
              f"₹{trade['pnl']:>8,.0f} ({trade['pnl_pct']:>6.2f}%) | "
              f"{trade['exit_reason']:<10} | {trade['days_held']:>2} days")
    print()


def save_excel_report(report, filename):
    """Save Excel report"""
    try:
        trades_df = pd.DataFrame(report['trades'])
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Summary
            summary_df = pd.DataFrame([report['summary']])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Trades
            if len(trades_df) > 0:
                trades_df.to_excel(writer, sheet_name='Trades', index=False)
            
            # Metrics
            metrics_df = pd.DataFrame([report['metrics']])
            metrics_df.to_excel(writer, sheet_name='Metrics', index=False)
        
        print(f"✅ Excel report saved: {filename}")
        
    except Exception as e:
        print(f"⚠️  Could not save Excel: {e}")


def main():
    """Main function"""
    print("📂 Loading configuration...")
    watchlist = load_watchlist()
    print(f"✅ Loaded {len(watchlist)} stocks")
    print()
    
    # Select period
    start_date, end_date, period_name = select_test_period()
    
    # Select symbols
    selected_symbols, selection_name = select_symbols(watchlist)
    
    # Confirm
    print()
    print("=" * 70)
    print("📋 BACKTEST CONFIGURATION:")
    print("=" * 70)
    print(f"   Period:       {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({period_name})")
    print(f"   Symbols:      {selection_name}")
    print(f"   Initial Cap:  ₹100,000")
    print(f"   Risk/Trade:   2%")
    print("=" * 70)
    print()
    
    confirm = input("Proceed with backtest? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("❌ Backtest cancelled")
        return
    
    print()
    print("🔬 Starting backtest... Fetching data from Yahoo Finance...")
    print()
    
    # Initialize engine
    engine = BacktestEngineV2(
        initial_capital=100000,
        position_size_pct=0.02
    )
    
    # Run backtest
    start_time = datetime.now()
    
    try:
        report = engine.run_backtest(
            symbols=selected_symbols,
            start_date=start_date,
            end_date=end_date
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Print results
        print_summary(report, period_name, selection_name, duration)
        
        # Show trades
        if len(report['trades']) > 0:
            show_best_trades(report)
        
        # Save reports
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        os.makedirs('backtesting/results', exist_ok=True)
        
        json_file = f'backtesting/results/backtest_v2_{timestamp}.json'
        engine.save_report(report, json_file)
        
        excel_file = f'backtesting/results/backtest_v2_{timestamp}.xlsx'
        save_excel_report(report, excel_file)
        
        print()
        print("=" * 70)
        print("✅ BACKTEST COMPLETE!")
        print("=" * 70)
        print()
        print(f"📁 Reports saved to:")
        print(f"   • {json_file}")
        print(f"   • {excel_file}")
        print()
        
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ ERROR DURING BACKTEST")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Backtest cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
