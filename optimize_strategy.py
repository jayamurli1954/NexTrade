#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STRATEGY OPTIMIZER - Test Multiple Confidence Thresholds
Finds the optimal threshold for best win rate and profit
"""

import sys
import os
from datetime import datetime, timedelta
import json
import pandas as pd

print("=" * 70)
print("🎯 STRATEGY OPTIMIZER - Confidence Threshold Tuning")
print("=" * 70)
print()

from backtesting.backtest_engine_v2 import BacktestEngineV2


def load_watchlist():
    """Load watchlist"""
    with open('watchlist.json', 'r') as f:
        data = json.load(f)
        if isinstance(data, list):
            return data
        else:
            return data.get('symbols', [])


def test_threshold(threshold, symbols, start_date, end_date):
    """Test a specific confidence threshold"""
    # Modify the BacktestEngineV2 to use this threshold
    # For now, we'll test with the default 50 (from _generate_signal)
    
    engine = BacktestEngineV2(initial_capital=100000, position_size_pct=0.02)
    
    # Override the signal generation threshold
    original_generate = engine._generate_signal
    
    def generate_with_threshold(symbol, price, rsi, ema_short, ema_long, 
                                fib_levels, volume_ratio, bb_upper, bb_lower, atr):
        signal = original_generate(symbol, price, rsi, ema_short, ema_long,
                                   fib_levels, volume_ratio, bb_upper, bb_lower, atr)
        
        # Apply threshold filter
        if signal and signal['confidence'] < threshold:
            return None
        
        return signal
    
    engine._generate_signal = generate_with_threshold
    
    report = engine.run_backtest(symbols, start_date, end_date)
    
    return report


def main():
    """Main optimization function"""
    print("This will test multiple confidence thresholds to find the best one")
    print()
    
    # Load data
    watchlist = load_watchlist()
    symbols = watchlist[:10]  # Top 10 stocks
    
    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 1 year
    
    print(f"📊 Testing on: {len(symbols)} stocks")
    print(f"📅 Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print()
    
    # Test different thresholds
    thresholds_to_test = [0.50, 0.55, 0.60, 0.65, 0.70]
    
    print("🔬 Testing confidence thresholds...")
    print()
    print("=" * 90)
    print(f"{'Threshold':<12} {'Trades':<8} {'Win Rate':<10} {'Profit':<12} {'Drawdown':<12} {'Verdict':<20}")
    print("=" * 90)
    
    results = []
    
    for threshold in thresholds_to_test:
        print(f"\nTesting {threshold*100:.0f}% confidence...", end=" ")
        
        try:
            report = test_threshold(threshold, symbols, start_date, end_date)
            
            summary = report['summary']
            
            # Store results
            result = {
                'threshold': threshold,
                'trades': summary['total_trades'],
                'win_rate': summary['win_rate'],
                'return_pct': summary['total_return_pct'],
                'profit_factor': summary['profit_factor'],
                'max_drawdown_pct': summary['max_drawdown_pct'],
                'sharpe': summary['sharpe_ratio']
            }
            results.append(result)
            
            # Verdict
            if summary['win_rate'] >= 55 and summary['profit_factor'] >= 1.2:
                verdict = "✅ GOOD"
            elif summary['win_rate'] >= 50 and summary['profit_factor'] >= 1.0:
                verdict = "⚠️  MARGINAL"
            else:
                verdict = "❌ POOR"
            
            print(f"{threshold*100:>6.0f}%     {summary['total_trades']:>6}   {summary['win_rate']:>6.1f}%    {summary['total_return_pct']:>6.1f}%     {summary['max_drawdown_pct']:>6.1f}%      {verdict}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            continue
    
    print("=" * 90)
    print()
    
    if not results:
        print("❌ No results obtained")
        return
    
    # Find best threshold
    df_results = pd.DataFrame(results)
    
    # Sort by win rate and profit factor
    df_results['score'] = (df_results['win_rate'] * 0.4) + (df_results['return_pct'] * 0.3) + (df_results['profit_factor'] * 10)
    df_results = df_results.sort_values('score', ascending=False)
    
    print()
    print("=" * 70)
    print("🏆 BEST THRESHOLD:")
    print("=" * 70)
    
    best = df_results.iloc[0]
    
    print()
    print(f"   Confidence:      {best['threshold']*100:.0f}%")
    print(f"   Total Trades:    {best['trades']:.0f}")
    print(f"   Win Rate:        {best['win_rate']:.1f}%")
    print(f"   Return:          {best['return_pct']:.1f}%")
    print(f"   Profit Factor:   {best['profit_factor']:.2f}")
    print(f"   Max Drawdown:    {best['max_drawdown_pct']:.1f}%")
    print(f"   Sharpe Ratio:    {best['sharpe']:.2f}")
    print()
    
    if best['win_rate'] >= 50 and best['profit_factor'] >= 1.0:
        print("✅ This threshold shows promise!")
        print(f"   → Update your analyzer to use {best['threshold']*100:.0f}% confidence")
        print()
        print("To apply this threshold:")
        print(f"   1. Open: analyzer/enhanced_analyzer.py")
        print(f"   2. Find: self.confidence_threshold = 0.65")
        print(f"   3. Change to: self.confidence_threshold = {best['threshold']:.2f}")
        print(f"   4. Save and restart your bot")
    else:
        print("⚠️  Even the best threshold has low performance")
        print("   → Strategy may need fundamental changes")
        print("   → Consider paper trading to validate in real-time")
    
    print()
    print("=" * 70)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f'backtesting/results/optimization_{timestamp}.xlsx'
    
    df_results.to_excel(results_file, index=False)
    print(f"📁 Results saved to: {results_file}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Optimization cancelled")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
