"""
Advanced Performance Analytics for Paper Trading

Provides comprehensive trading performance metrics beyond basic P&L.

Installation:
    pip install pandas numpy scipy

Usage:
    from enhancements.order_manager.performance_analyzer import PerformanceAnalyzer

    analyzer = PerformanceAnalyzer(paper_trader.closed_trades)
    report = analyzer.generate_report()
    print(report)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging

logger = logging.getLogger("PerformanceAnalyzer")


class PerformanceAnalyzer:
    """
    Advanced performance analytics for trading

    Metrics calculated:
    - Sharpe Ratio
    - Sortino Ratio
    - Maximum Drawdown
    - Calmar Ratio
    - Win Rate & Profit Factor
    - Average Win/Loss
    - Risk/Reward Ratio
    - Trade Duration Analysis
    - Best/Worst Trades
    - Consecutive Wins/Losses
    """

    def __init__(self, trades_history: List[Dict]):
        """
        Initialize with trade history

        Args:
            trades_history: List of closed trade dictionaries
        """
        if not trades_history:
            self.df = pd.DataFrame()
            logger.warning("No trades provided for analysis")
        else:
            self.df = pd.DataFrame(trades_history)
            self._prepare_data()

        self.risk_free_rate = 0.05  # 5% annual risk-free rate

    def _prepare_data(self):
        """Prepare data for analysis"""
        # Convert datetime strings to datetime objects
        if 'entry_time' in self.df.columns:
            self.df['entry_time'] = pd.to_datetime(self.df['entry_time'])

        if 'exit_time' in self.df.columns:
            self.df['exit_time'] = pd.to_datetime(self.df['exit_time'])

        # Calculate trade duration
        if 'entry_time' in self.df.columns and 'exit_time' in self.df.columns:
            self.df['duration'] = self.df['exit_time'] - self.df['entry_time']
            self.df['duration_hours'] = self.df['duration'].dt.total_seconds() / 3600

        # Add cumulative P&L
        if 'pnl' in self.df.columns:
            self.df['cumulative_pnl'] = self.df['pnl'].cumsum()

        # Calculate returns series
        if 'pnl' in self.df.columns and 'entry_price' in self.df.columns and 'quantity' in self.df.columns:
            self.df['capital_at_risk'] = self.df['entry_price'] * self.df['quantity']
            self.df['returns'] = self.df['pnl'] / self.df['capital_at_risk']

    def calculate_sharpe_ratio(self) -> float:
        """
        Calculate Sharpe Ratio (risk-adjusted return)

        Formula: (Mean Return - Risk Free Rate) / Std Dev of Returns

        Returns:
            float: Annualized Sharpe Ratio
        """
        if self.df.empty or 'returns' not in self.df.columns:
            return 0.0

        returns = self.df['returns']

        # Calculate excess returns
        daily_rf_rate = self.risk_free_rate / 252  # Assuming 252 trading days
        excess_returns = returns - daily_rf_rate

        # Calculate Sharpe ratio
        if excess_returns.std() == 0:
            return 0.0

        sharpe = excess_returns.mean() / excess_returns.std()

        # Annualize (assuming ~252 trading days)
        sharpe_annual = sharpe * np.sqrt(252)

        return round(sharpe_annual, 3)

    def calculate_sortino_ratio(self) -> float:
        """
        Calculate Sortino Ratio (downside risk-adjusted return)

        Only considers negative volatility

        Returns:
            float: Annualized Sortino Ratio
        """
        if self.df.empty or 'returns' not in self.df.columns:
            return 0.0

        returns = self.df['returns']
        daily_rf_rate = self.risk_free_rate / 252

        excess_returns = returns - daily_rf_rate

        # Calculate downside deviation (only negative returns)
        downside_returns = excess_returns[excess_returns < 0]

        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0

        sortino = excess_returns.mean() / downside_returns.std()
        sortino_annual = sortino * np.sqrt(252)

        return round(sortino_annual, 3)

    def calculate_max_drawdown(self) -> Dict[str, Any]:
        """
        Calculate Maximum Drawdown

        Returns:
            Dict containing max_dd_pct, max_dd_amount, peak, trough
        """
        if self.df.empty or 'cumulative_pnl' not in self.df.columns:
            return {
                'max_dd_pct': 0.0,
                'max_dd_amount': 0.0,
                'peak': 0.0,
                'trough': 0.0,
                'recovery_time': None
            }

        cumulative = self.df['cumulative_pnl'].values
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max

        max_dd_idx = np.argmin(drawdown)
        max_dd_amount = drawdown[max_dd_idx]

        # Find peak before max drawdown
        peak_idx = np.argmax(cumulative[:max_dd_idx+1]) if max_dd_idx > 0 else 0
        peak_value = cumulative[peak_idx]

        # Calculate percentage drawdown
        if peak_value > 0:
            max_dd_pct = (max_dd_amount / peak_value) * 100
        else:
            max_dd_pct = 0.0

        # Calculate recovery time
        recovery_idx = None
        if max_dd_idx < len(cumulative) - 1:
            recovery_indices = np.where(cumulative[max_dd_idx:] >= peak_value)[0]
            if len(recovery_indices) > 0:
                recovery_idx = max_dd_idx + recovery_indices[0]

        recovery_time = None
        if recovery_idx is not None and 'exit_time' in self.df.columns:
            recovery_time = (self.df['exit_time'].iloc[recovery_idx] -
                           self.df['exit_time'].iloc[max_dd_idx])

        return {
            'max_dd_pct': round(max_dd_pct, 2),
            'max_dd_amount': round(max_dd_amount, 2),
            'peak': round(peak_value, 2),
            'trough': round(cumulative[max_dd_idx], 2),
            'recovery_time': str(recovery_time) if recovery_time else "Not recovered"
        }

    def calculate_calmar_ratio(self) -> float:
        """
        Calculate Calmar Ratio (return / max drawdown)

        Returns:
            float: Calmar Ratio
        """
        if self.df.empty or 'pnl' not in self.df.columns:
            return 0.0

        total_return = self.df['pnl'].sum()
        max_dd = self.calculate_max_drawdown()['max_dd_amount']

        if max_dd == 0:
            return 0.0

        # Annualize return
        days_traded = (self.df['exit_time'].max() - self.df['entry_time'].min()).days
        if days_traded == 0:
            return 0.0

        annual_return = (total_return / days_traded) * 365

        calmar = annual_return / abs(max_dd)

        return round(calmar, 3)

    def calculate_win_rate(self) -> Dict[str, Any]:
        """
        Calculate win rate and related metrics

        Returns:
            Dict containing win_rate, profit_factor, avg_win, avg_loss
        """
        if self.df.empty or 'pnl' not in self.df.columns:
            return {
                'win_rate': 0.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0
            }

        total_trades = len(self.df)
        winning_trades = len(self.df[self.df['pnl'] > 0])
        losing_trades = len(self.df[self.df['pnl'] < 0])

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Calculate profit factor
        total_wins = self.df[self.df['pnl'] > 0]['pnl'].sum()
        total_losses = abs(self.df[self.df['pnl'] < 0]['pnl'].sum())

        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0.0

        # Calculate averages
        avg_win = self.df[self.df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0.0
        avg_loss = self.df[self.df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0.0

        # Largest win/loss
        largest_win = self.df['pnl'].max() if total_trades > 0 else 0.0
        largest_loss = self.df['pnl'].min() if total_trades > 0 else 0.0

        return {
            'win_rate': round(win_rate, 2),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'profit_factor': round(profit_factor, 3),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'largest_win': round(largest_win, 2),
            'largest_loss': round(largest_loss, 2)
        }

    def analyze_trade_duration(self) -> Dict[str, Any]:
        """
        Analyze trade holding periods

        Returns:
            Dict with duration statistics
        """
        if self.df.empty or 'duration_hours' not in self.df.columns:
            return {}

        return {
            'avg_duration_hours': round(self.df['duration_hours'].mean(), 2),
            'median_duration_hours': round(self.df['duration_hours'].median(), 2),
            'min_duration_hours': round(self.df['duration_hours'].min(), 2),
            'max_duration_hours': round(self.df['duration_hours'].max(), 2),
            'winning_avg_duration': round(
                self.df[self.df['pnl'] > 0]['duration_hours'].mean(), 2
            ) if len(self.df[self.df['pnl'] > 0]) > 0 else 0.0,
            'losing_avg_duration': round(
                self.df[self.df['pnl'] < 0]['duration_hours'].mean(), 2
            ) if len(self.df[self.df['pnl'] < 0]) > 0 else 0.0
        }

    def analyze_by_symbol(self) -> pd.DataFrame:
        """
        Analyze performance by symbol

        Returns:
            DataFrame with per-symbol statistics
        """
        if self.df.empty:
            return pd.DataFrame()

        symbol_stats = self.df.groupby('symbol').agg({
            'pnl': ['count', 'sum', 'mean', 'std'],
            'pnl_pct': ['mean', 'std']
        }).round(2)

        # Calculate win rate per symbol
        win_rates = self.df.groupby('symbol').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(2)

        symbol_stats['win_rate'] = win_rates

        return symbol_stats

    def analyze_by_action(self) -> Dict[str, Any]:
        """
        Compare BUY vs SELL performance

        Returns:
            Dict with action-based statistics
        """
        if self.df.empty or 'action' not in self.df.columns:
            return {}

        buy_trades = self.df[self.df['action'] == 'BUY']
        sell_trades = self.df[self.df['action'] == 'SELL']

        return {
            'buy': {
                'count': len(buy_trades),
                'win_rate': round((buy_trades['pnl'] > 0).sum() / len(buy_trades) * 100, 2) if len(buy_trades) > 0 else 0,
                'total_pnl': round(buy_trades['pnl'].sum(), 2) if len(buy_trades) > 0 else 0,
                'avg_pnl': round(buy_trades['pnl'].mean(), 2) if len(buy_trades) > 0 else 0
            },
            'sell': {
                'count': len(sell_trades),
                'win_rate': round((sell_trades['pnl'] > 0).sum() / len(sell_trades) * 100, 2) if len(sell_trades) > 0 else 0,
                'total_pnl': round(sell_trades['pnl'].sum(), 2) if len(sell_trades) > 0 else 0,
                'avg_pnl': round(sell_trades['pnl'].mean(), 2) if len(sell_trades) > 0 else 0
            }
        }

    def generate_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive performance report

        Returns:
            Dict containing all performance metrics
        """
        if self.df.empty:
            return {
                'status': 'NO_DATA',
                'message': 'No trades available for analysis'
            }

        report = {
            'summary': {
                'total_trades': len(self.df),
                'total_pnl': round(self.df['pnl'].sum(), 2),
                'total_pnl_pct': round(self.df['pnl_pct'].sum(), 2)
            },
            'risk_adjusted_returns': {
                'sharpe_ratio': self.calculate_sharpe_ratio(),
                'sortino_ratio': self.calculate_sortino_ratio(),
                'calmar_ratio': self.calculate_calmar_ratio()
            },
            'drawdown': self.calculate_max_drawdown(),
            'win_metrics': self.calculate_win_rate(),
            'duration_analysis': self.analyze_trade_duration(),
            'action_analysis': self.analyze_by_action(),
            'symbol_analysis': self.analyze_by_symbol().to_dict() if not self.analyze_by_symbol().empty else {}
        }

        return report

    def print_report(self):
        """Print formatted performance report"""
        report = self.generate_report()

        if report.get('status') == 'NO_DATA':
            print("⚠️  No trades available for analysis")
            return

        print("\n" + "="*80)
        print("PERFORMANCE ANALYSIS REPORT".center(80))
        print("="*80 + "\n")

        # Summary
        print("📊 SUMMARY")
        print("-" * 80)
        summary = report['summary']
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Total P&L: ₹{summary['total_pnl']:.2f}")
        print(f"Total P&L %: {summary['total_pnl_pct']:.2f}%\n")

        # Risk-Adjusted Returns
        print("📈 RISK-ADJUSTED RETURNS")
        print("-" * 80)
        risk_adj = report['risk_adjusted_returns']
        print(f"Sharpe Ratio: {risk_adj['sharpe_ratio']:.3f}")
        print(f"Sortino Ratio: {risk_adj['sortino_ratio']:.3f}")
        print(f"Calmar Ratio: {risk_adj['calmar_ratio']:.3f}\n")

        # Drawdown
        print("📉 DRAWDOWN ANALYSIS")
        print("-" * 80)
        dd = report['drawdown']
        print(f"Max Drawdown: {dd['max_dd_pct']:.2f}% (₹{dd['max_dd_amount']:.2f})")
        print(f"Peak: ₹{dd['peak']:.2f}")
        print(f"Trough: ₹{dd['trough']:.2f}")
        print(f"Recovery Time: {dd['recovery_time']}\n")

        # Win Metrics
        print("🎯 WIN/LOSS METRICS")
        print("-" * 80)
        win = report['win_metrics']
        print(f"Win Rate: {win['win_rate']:.2f}%")
        print(f"Winning Trades: {win['winning_trades']}")
        print(f"Losing Trades: {win['losing_trades']}")
        print(f"Profit Factor: {win['profit_factor']:.3f}")
        print(f"Avg Win: ₹{win['avg_win']:.2f}")
        print(f"Avg Loss: ₹{win['avg_loss']:.2f}")
        print(f"Largest Win: ₹{win['largest_win']:.2f}")
        print(f"Largest Loss: ₹{win['largest_loss']:.2f}\n")

        # Duration
        if report.get('duration_analysis'):
            print("⏱️  TRADE DURATION")
            print("-" * 80)
            dur = report['duration_analysis']
            print(f"Avg Duration: {dur.get('avg_duration_hours', 0):.2f} hours")
            print(f"Median Duration: {dur.get('median_duration_hours', 0):.2f} hours")
            print(f"Winning Trades Avg: {dur.get('winning_avg_duration', 0):.2f} hours")
            print(f"Losing Trades Avg: {dur.get('losing_avg_duration', 0):.2f} hours\n")

        # Action Analysis
        if report.get('action_analysis'):
            print("🔄 BUY vs SELL ANALYSIS")
            print("-" * 80)
            action = report['action_analysis']
            if 'buy' in action:
                buy = action['buy']
                print(f"BUY Trades: {buy['count']} | Win Rate: {buy['win_rate']:.2f}% | Total P&L: ₹{buy['total_pnl']:.2f}")
            if 'sell' in action:
                sell = action['sell']
                print(f"SELL Trades: {sell['count']} | Win Rate: {sell['win_rate']:.2f}% | Total P&L: ₹{sell['total_pnl']:.2f}\n")

        print("="*80 + "\n")


if __name__ == "__main__":
    # Example usage with sample data
    sample_trades = [
        {
            'symbol': 'RELIANCE',
            'action': 'BUY',
            'entry_price': 2500,
            'exit_price': 2550,
            'quantity': 10,
            'pnl': 500,
            'pnl_pct': 2.0,
            'entry_time': '2024-01-01 09:30:00',
            'exit_time': '2024-01-01 15:00:00'
        },
        {
            'symbol': 'TCS',
            'action': 'BUY',
            'entry_price': 3500,
            'exit_price': 3450,
            'quantity': 5,
            'pnl': -250,
            'pnl_pct': -1.43,
            'entry_time': '2024-01-02 10:00:00',
            'exit_time': '2024-01-02 14:30:00'
        },
        {
            'symbol': 'INFY',
            'action': 'SELL',
            'entry_price': 1500,
            'exit_price': 1480,
            'quantity': 20,
            'pnl': 400,
            'pnl_pct': 1.33,
            'entry_time': '2024-01-03 09:45:00',
            'exit_time': '2024-01-03 14:00:00'
        }
    ]

    analyzer = PerformanceAnalyzer(sample_trades)
    analyzer.print_report()
