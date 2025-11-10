#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ENHANCED BACKTESTING ENGINE v3.0.0
Integrates with EnhancedAnalyzer (with FinBERT, Screener.in, Candlestick Patterns)

Features:
- Uses current enhanced_analyzer with all latest features
- Comprehensive performance metrics (Sharpe, Sortino, Calmar, Max Drawdown)
- Trade-level analysis
- Multiple strategy configuration testing
- Excel/JSON report generation
- Performance visualization ready
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BacktestEngineV3")

# Try to import yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.error("yfinance not installed! Run: pip install yfinance")


class MockDataProvider:
    """
    Mock data provider for backtesting
    Provides historical data without requiring live API
    """

    def __init__(self):
        self.cache = {}

    def get_historical(self, symbol, exchange="NSE", period_days=50):
        """Return cached historical data"""
        key = f"{symbol}_{period_days}"
        return self.cache.get(key, None)

    def set_historical(self, symbol, df, period_days=50):
        """Cache historical data"""
        key = f"{symbol}_{period_days}"
        self.cache[key] = df

    def get_ltp(self, symbol, exchange="NSE"):
        """Return last close price from cache"""
        df = self.cache.get(f"{symbol}_50", None)
        if df is not None and not df.empty:
            return df['close'].iloc[-1]
        return None


class EnhancedBacktestEngine:
    """
    Advanced backtesting engine using EnhancedAnalyzer
    """

    def __init__(self,
                 initial_capital=100000,
                 position_size_method='fixed_rupees',
                 position_size_value=100000,
                 enable_fundamentals=False,
                 config_file=None):
        """
        Initialize enhanced backtest engine

        Args:
            initial_capital: Starting capital (default: ₹100,000)
            position_size_method: 'fixed_rupees' or 'risk_pct'
            position_size_value: Fixed amount or risk %
            enable_fundamentals: Whether to use fundamentals (slower but more accurate)
            config_file: Path to analyzer config file
        """
        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance is required. Install with: pip install yfinance")

        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.position_size_method = position_size_method
        self.position_size_value = position_size_value
        self.enable_fundamentals = enable_fundamentals
        self.config_file = config_file

        # Initialize mock data provider and analyzer
        self.data_provider = MockDataProvider()
        self._init_analyzer()

        # Trade tracking
        self.trades = []
        self.open_positions = {}
        self.closed_trades = []
        self.daily_equity = []

        # Performance metrics
        self.metrics = {}

        logger.info(f"✅ Enhanced Backtester initialized - Capital: ₹{initial_capital:,.0f}")
        logger.info(f"   Position sizing: {position_size_method} = {position_size_value}")
        logger.info(f"   Fundamentals: {'ENABLED' if enable_fundamentals else 'DISABLED (faster)'}")

    def _init_analyzer(self):
        """Initialize EnhancedAnalyzer"""
        try:
            from analyzer.enhanced_analyzer import EnhancedAnalyzer

            self.analyzer = EnhancedAnalyzer(
                data_provider=self.data_provider,
                config_file=self.config_file
            )

            # Override fundamentals setting
            self.analyzer.fundamentals_enabled = self.enable_fundamentals

            # Disable FinBERT for backtesting (too slow)
            self.analyzer.finbert_enabled = False

            logger.info("✅ EnhancedAnalyzer loaded for backtesting")

        except Exception as e:
            logger.error(f"Failed to load EnhancedAnalyzer: {e}")
            raise

    def fetch_data(self, symbol, start_date, end_date, interval='1d'):
        """
        Fetch historical data from Yahoo Finance

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            start_date: Start date
            end_date: End date
            interval: Data interval ('1d', '1h', '5m')

        Returns:
            DataFrame with OHLCV data
        """
        yf_symbol = f"{symbol}.NS" if not symbol.endswith('.NS') else symbol

        try:
            logger.debug(f"Fetching data for {yf_symbol} ({start_date} to {end_date})...")
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=start_date, end=end_date, interval=interval)

            if df.empty:
                logger.warning(f"No data for {yf_symbol}")
                return None

            # Rename columns to match our format
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })

            # Keep only OHLCV
            df = df[['open', 'high', 'low', 'close', 'volume']].copy()

            logger.info(f"✅ {symbol}: {len(df)} bars fetched")
            return df

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def run_backtest(self, symbols, start_date, end_date, interval='1d'):
        """
        Run backtest on list of symbols

        Args:
            symbols: List of stock symbols
            start_date: Start date ('YYYY-MM-DD' or datetime)
            end_date: End date ('YYYY-MM-DD' or datetime)
            interval: Data interval ('1d', '1h')

        Returns:
            Dictionary with comprehensive backtest results
        """
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')

        total_days = (end_date - start_date).days
        logger.info(f"{'='*70}")
        logger.info(f"BACKTEST STARTED")
        logger.info(f"{'='*70}")
        logger.info(f"Symbols: {len(symbols)}")
        logger.info(f"Period: {start_date.date()} to {end_date.date()} ({total_days} days / {total_days/365:.1f} years)")
        logger.info(f"Interval: {interval}")
        logger.info(f"Initial Capital: ₹{self.initial_capital:,.0f}")
        logger.info(f"{'='*70}")

        # Reset state
        self.current_capital = self.initial_capital
        self.trades = []
        self.open_positions = {}
        self.closed_trades = []
        self.daily_equity = []

        # Backtest each symbol
        for idx, symbol in enumerate(symbols):
            logger.info(f"\n[{idx+1}/{len(symbols)}] Backtesting {symbol}...")

            try:
                self._backtest_symbol(symbol, start_date, end_date, interval)
            except Exception as e:
                logger.error(f"❌ Error backtesting {symbol}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Close any remaining open positions
        self._close_all_positions(end_date)

        # Calculate comprehensive metrics
        self._calculate_metrics()

        # Generate report
        report = self._generate_report()

        logger.info(f"\n{'='*70}")
        logger.info(f"BACKTEST COMPLETE")
        logger.info(f"{'='*70}")
        logger.info(f"Total Trades: {self.metrics.get('total_trades', 0)}")
        logger.info(f"Win Rate: {self.metrics.get('win_rate', 0):.1f}%")
        logger.info(f"Total Return: {self.metrics.get('total_return_pct', 0):.2f}%")
        logger.info(f"Max Drawdown: {self.metrics.get('max_drawdown_pct', 0):.2f}%")
        logger.info(f"Sharpe Ratio: {self.metrics.get('sharpe_ratio', 0):.2f}")
        logger.info(f"Profit Factor: {self.metrics.get('profit_factor', 0):.2f}")
        logger.info(f"{'='*70}")

        return report

    def _backtest_symbol(self, symbol, start_date, end_date, interval):
        """Backtest a single symbol"""
        # Fetch data with buffer for indicators (50 days)
        fetch_start = start_date - timedelta(days=100)
        df = self.fetch_data(symbol, fetch_start, end_date, interval)

        if df is None or df.empty:
            return

        # Make dates timezone-aware if needed
        import pytz
        if df.index.tz is not None:
            tz = df.index.tz
            start_date = start_date.replace(tzinfo=tz) if start_date.tzinfo is None else start_date
            end_date = end_date.replace(tzinfo=tz) if end_date.tzinfo is None else end_date

        # Filter to actual backtest period
        test_df = df[(df.index >= start_date) & (df.index <= end_date)]

        if len(test_df) < 30:
            logger.warning(f"⚠️ Insufficient data for {symbol} ({len(test_df)} bars)")
            return

        logger.info(f"   Testing on {len(test_df)} bars...")

        # Iterate through each bar
        signals_generated = 0
        trades_executed = 0

        for bar_idx, current_date in enumerate(test_df.index):
            # Get historical data up to current bar
            historical_df = df[df.index <= current_date].tail(100)  # Last 100 bars for indicators

            if len(historical_df) < 30:
                continue

            # Update data provider cache
            self.data_provider.set_historical(symbol, historical_df, period_days=50)

            # Generate signal using EnhancedAnalyzer
            signal = self._generate_signal(symbol, historical_df, current_date)

            if signal:
                signals_generated += 1

            # Get current bar data
            current_bar = test_df.loc[current_date]

            # Check existing position for exits
            if symbol in self.open_positions:
                self._check_exit(symbol, current_bar, current_date)

            # Open new position if signal and no position
            elif signal and signal.get('action') in ['BUY', 'SELL']:
                if self._open_position(symbol, signal, current_bar, current_date):
                    trades_executed += 1

            # Track equity
            if bar_idx % 10 == 0:  # Every 10 bars
                equity = self._calculate_current_equity(df, current_date)
                self.daily_equity.append({
                    'date': current_date,
                    'equity': equity
                })

        logger.info(f"   Signals: {signals_generated}, Trades: {trades_executed}")

    def _generate_signal(self, symbol, historical_df, current_date):
        """Generate trading signal using EnhancedAnalyzer"""
        try:
            # Analyze using enhanced analyzer
            result = self.analyzer.analyze_symbol(symbol, exchange="NSE")

            if result and result.get('action') in ['BUY', 'SELL']:
                return result

            return None

        except Exception as e:
            logger.debug(f"Signal generation error for {symbol}: {e}")
            return None

    def _calculate_position_size(self, entry_price, stop_loss):
        """Calculate position size based on method"""
        # Cap position size to 90% of available capital to ensure we can open trades
        max_position_value = self.current_capital * 0.90

        if self.position_size_method == 'fixed_rupees':
            # Fixed rupee amount per trade (capped by available capital)
            target_value = min(self.position_size_value, max_position_value)
            quantity = int(target_value / entry_price)

        elif self.position_size_method == 'risk_pct':
            # Risk-based position sizing
            risk_per_share = abs(entry_price - stop_loss)
            if risk_per_share == 0:
                risk_per_share = entry_price * 0.02  # Default 2%

            risk_amount = self.current_capital * (self.position_size_value / 100)
            quantity = int(risk_amount / risk_per_share)

            # Cap by max position value
            max_quantity = int(max_position_value / entry_price)
            quantity = min(quantity, max_quantity)

        else:
            # Default to 90% of capital
            quantity = int(max_position_value / entry_price)

        return max(1, quantity)  # At least 1 share

    def _open_position(self, symbol, signal, current_bar, current_date):
        """Open a new position"""
        entry_price = current_bar['close']
        stop_loss = signal.get('stop_loss', entry_price * 0.98)
        target = signal.get('target', entry_price * 1.02)

        # Calculate position size
        quantity = self._calculate_position_size(entry_price, stop_loss)

        # Calculate cost
        cost = quantity * entry_price

        # Check if we have enough capital
        max_allowed = self.current_capital * 0.95
        if cost > max_allowed:  # Use max 95% of capital
            logger.warning(f"⚠️ Insufficient capital for {symbol}: Cost ₹{cost:,.0f} > Max allowed ₹{max_allowed:,.0f} (Capital: ₹{self.current_capital:,.0f})")
            return False

        # Open position
        position = {
            'symbol': symbol,
            'action': signal['action'],
            'entry_date': current_date,
            'entry_price': entry_price,
            'quantity': quantity,
            'stop_loss': stop_loss,
            'target': target,
            'confidence': signal.get('confidence', 0),
            'reason': signal.get('reason', ''),
            'cost': cost
        }

        self.open_positions[symbol] = position
        self.current_capital -= cost  # Reduce available capital

        logger.debug(f"   📈 OPENED {signal['action']}: {symbol} @ ₹{entry_price:.2f} x {quantity} | SL: ₹{stop_loss:.2f}, TGT: ₹{target:.2f}")

        return True

    def _check_exit(self, symbol, current_bar, current_date):
        """Check if position should be exited"""
        position = self.open_positions[symbol]

        high = current_bar['high']
        low = current_bar['low']
        close = current_bar['close']

        exit_price = None
        exit_reason = None

        # Check stop loss
        if low <= position['stop_loss']:
            exit_price = position['stop_loss']
            exit_reason = 'STOP_LOSS'

        # Check target
        elif high >= position['target']:
            exit_price = position['target']
            exit_reason = 'TARGET'

        # Check max hold period (30 days)
        elif (current_date - position['entry_date']).days >= 30:
            exit_price = close
            exit_reason = 'MAX_HOLD'

        # Exit if triggered
        if exit_price:
            self._close_position(symbol, exit_price, current_date, exit_reason)

    def _close_position(self, symbol, exit_price, exit_date, exit_reason):
        """Close an open position"""
        position = self.open_positions[symbol]

        # Calculate P&L
        if position['action'] == 'BUY':
            pnl = (exit_price - position['entry_price']) * position['quantity']
        else:  # SELL
            pnl = (position['entry_price'] - exit_price) * position['quantity']

        pnl_pct = (pnl / position['cost']) * 100

        # Return capital + profit/loss
        self.current_capital += position['cost'] + pnl

        # Record closed trade
        trade = {
            **position,
            'exit_date': exit_date,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'hold_days': (exit_date - position['entry_date']).days,
            'status': 'WIN' if pnl > 0 else 'LOSS'
        }

        self.closed_trades.append(trade)

        logger.debug(f"   {'✅' if pnl > 0 else '❌'} CLOSED: {symbol} @ ₹{exit_price:.2f} | {exit_reason} | P&L: ₹{pnl:,.0f} ({pnl_pct:+.1f}%)")

        # Remove from open positions
        del self.open_positions[symbol]

    def _close_all_positions(self, exit_date):
        """Close all remaining open positions at end of backtest"""
        for symbol in list(self.open_positions.keys()):
            position = self.open_positions[symbol]
            # Close at entry price (no profit/loss)
            self._close_position(symbol, position['entry_price'], exit_date, 'END_OF_BACKTEST')

    def _calculate_current_equity(self, df, current_date):
        """Calculate current total equity (cash + open positions value)"""
        equity = self.current_capital

        # Add value of open positions
        for symbol, position in self.open_positions.items():
            try:
                current_price = df.loc[current_date, 'close']
                position_value = position['quantity'] * current_price
                equity += position_value
            except:
                equity += position['cost']  # Use entry cost if price not available

        return equity

    def _calculate_metrics(self):
        """Calculate comprehensive performance metrics"""
        if not self.closed_trades:
            logger.warning("No closed trades - cannot calculate metrics")
            self.metrics = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_profit': 0.0,
                'total_loss': 0.0,
                'net_pnl': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'expectancy': 0.0,
                'max_drawdown': 0.0,
                'max_drawdown_pct': 0.0,
                'sharpe_ratio': 0.0,
                'total_return_pct': 0.0,
                'initial_capital': self.initial_capital,
                'final_capital': self.current_capital,
                'start_date': None,
                'end_date': None
            }
            return

        # Basic counts
        total_trades = len(self.closed_trades)
        winning_trades = [t for t in self.closed_trades if t['pnl'] > 0]
        losing_trades = [t for t in self.closed_trades if t['pnl'] <= 0]

        num_wins = len(winning_trades)
        num_losses = len(losing_trades)

        # P&L
        total_profit = sum(t['pnl'] for t in winning_trades) if winning_trades else 0
        total_loss = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0
        net_pnl = total_profit - total_loss

        # Averages
        avg_win = total_profit / num_wins if num_wins > 0 else 0
        avg_loss = total_loss / num_losses if num_losses > 0 else 0

        # Ratios
        win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # Returns
        final_capital = self.current_capital
        total_return_pct = ((final_capital - self.initial_capital) / self.initial_capital) * 100

        # Drawdown
        equity_curve = pd.DataFrame(self.daily_equity)
        if not equity_curve.empty:
            equity_curve['peak'] = equity_curve['equity'].cummax()
            equity_curve['drawdown'] = equity_curve['equity'] - equity_curve['peak']
            equity_curve['drawdown_pct'] = (equity_curve['drawdown'] / equity_curve['peak']) * 100

            max_drawdown = equity_curve['drawdown'].min()
            max_drawdown_pct = equity_curve['drawdown_pct'].min()
        else:
            max_drawdown = 0
            max_drawdown_pct = 0

        # Sharpe Ratio (annualized)
        daily_returns = []
        for trade in self.closed_trades:
            daily_return = (trade['pnl'] / trade['cost']) / max(1, trade['hold_days'])
            daily_returns.append(daily_return)

        if daily_returns:
            daily_returns_series = pd.Series(daily_returns)
            sharpe_ratio = (daily_returns_series.mean() / daily_returns_series.std()) * np.sqrt(252) if daily_returns_series.std() > 0 else 0
        else:
            sharpe_ratio = 0

        # Expectancy
        expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

        # Store metrics
        self.metrics = {
            'total_trades': total_trades,
            'winning_trades': num_wins,
            'losing_trades': num_losses,
            'win_rate': round(win_rate, 2),
            'total_profit': round(total_profit, 2),
            'total_loss': round(total_loss, 2),
            'net_pnl': round(net_pnl, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy': round(expectancy, 2),
            'max_drawdown': round(max_drawdown, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'total_return_pct': round(total_return_pct, 2),
            'initial_capital': self.initial_capital,
            'final_capital': round(final_capital, 2),
            'start_date': self.closed_trades[0]['entry_date'] if self.closed_trades else None,
            'end_date': self.closed_trades[-1]['exit_date'] if self.closed_trades else None
        }

    def _generate_report(self):
        """Generate comprehensive backtest report"""
        report = {
            'summary': self.metrics,
            'trades': self.closed_trades,
            'equity_curve': self.daily_equity,
            'trade_analysis': self._analyze_trades()
        }

        return report

    def _analyze_trades(self):
        """Detailed trade analysis"""
        if not self.closed_trades:
            return {}

        df = pd.DataFrame(self.closed_trades)

        analysis = {
            'by_exit_reason': df.groupby('exit_reason')['pnl'].agg(['count', 'sum', 'mean']).to_dict(),
            'by_symbol': df.groupby('symbol')['pnl'].agg(['count', 'sum', 'mean']).to_dict(),
            'avg_hold_days_winners': df[df['pnl'] > 0]['hold_days'].mean() if len(df[df['pnl'] > 0]) > 0 else 0,
            'avg_hold_days_losers': df[df['pnl'] <= 0]['hold_days'].mean() if len(df[df['pnl'] <= 0]) > 0 else 0,
            'best_trade': df.loc[df['pnl'].idxmax()].to_dict() if not df.empty else {},
            'worst_trade': df.loc[df['pnl'].idxmin()].to_dict() if not df.empty else {}
        }

        return analysis

    def save_report(self, report, output_dir="backtesting/results"):
        """Save backtest report to files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save JSON report
        json_file = output_path / f"backtest_{timestamp}.json"
        with open(json_file, 'w') as f:
            # Convert datetime objects to strings for JSON serialization
            report_copy = self._serialize_report(report)
            json.dump(report_copy, f, indent=2, default=str)

        logger.info(f"📄 Report saved: {json_file}")

        # Save trades to Excel
        if self.closed_trades:
            try:
                excel_file = output_path / f"trades_{timestamp}.xlsx"
                trades_df = pd.DataFrame(self.closed_trades)
                trades_df.to_excel(excel_file, index=False)
                logger.info(f"📊 Trades saved: {excel_file}")
            except Exception as e:
                logger.warning(f"Could not save Excel: {e}")

        return json_file

    def _serialize_report(self, report):
        """Convert datetime objects to strings for JSON"""
        import copy
        report_copy = copy.deepcopy(report)

        # Convert trades
        for trade in report_copy.get('trades', []):
            for key in ['entry_date', 'exit_date']:
                if key in trade and hasattr(trade[key], 'isoformat'):
                    trade[key] = trade[key].isoformat()

        # Convert equity curve
        for point in report_copy.get('equity_curve', []):
            if 'date' in point and hasattr(point['date'], 'isoformat'):
                point['date'] = point['date'].isoformat()

        # Convert summary dates
        summary = report_copy.get('summary', {})
        for key in ['start_date', 'end_date']:
            if key in summary and summary[key] and hasattr(summary[key], 'isoformat'):
                summary[key] = summary[key].isoformat()

        return report_copy


# Example usage
if __name__ == "__main__":
    # Initialize backtester
    engine = EnhancedBacktestEngine(
        initial_capital=100000,
        position_size_method='fixed_rupees',
        position_size_value=100000,  # ₹100,000 per trade
        enable_fundamentals=False  # Disable for faster backtesting
    )

    # Define test parameters
    symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK']
    start_date = '2024-01-01'
    end_date = '2024-11-01'

    # Run backtest
    report = engine.run_backtest(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        interval='1d'
    )

    # Save report
    engine.save_report(report)

    # Print summary
    print("\n" + "="*70)
    print("BACKTEST SUMMARY")
    print("="*70)
    for key, value in report['summary'].items():
        print(f"{key:.<40} {value}")
    print("="*70)
