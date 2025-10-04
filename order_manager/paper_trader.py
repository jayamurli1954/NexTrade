"""
COMPLETE SCRIPT - paper_trader.py
Enhanced Paper Trading System with Excel Logging
Save this as: c:/Users/Dell/tradingbot_new/order_manager/paper_trader.py

NO PATCHING REQUIRED - Replace your existing paper_trader.py with this
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PaperTrader:
    """Enhanced paper trading system with trade logging support"""
    
    def __init__(self, initial_cash=100000, leverage=5.0, trade_logger=None):
        """
        Initialize paper trader
        
        Args:
            initial_cash: Starting cash amount
            leverage: Leverage ratio (default 5x)
            trade_logger: TradeLogger instance for Excel tracking
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.leverage = leverage
        self.positions = {}
        self.used_margin = 0
        self.margin_pct = 1 / leverage
        self.trade_logger = trade_logger  # Store trade logger
        self.trade_history = []
        
        logger.info(f"💰 PaperTrader started with cash ₹{initial_cash:,.2f} and leverage x{leverage}")
        logger.info(f"Intraday trading enabled: SHORT SELLING supported")
    
    def get_available_margin(self):
        """Calculate available margin for trading"""
        total_buying_power = self.cash * self.leverage
        available = total_buying_power - self.used_margin
        return max(0, available)
    
    def execute_order(self, symbol, action, quantity, price, stoploss=None, target=None):
        """
        Execute a paper trade
        
        Args:
            symbol: Stock symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Entry price
            stoploss: Stop loss price (optional)
            target: Target price (optional)
            
        Returns:
            order_id: Unique order identifier
        """
        # Generate unique order ID
        order_id = f"P{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        
        # Calculate order value and margin
        order_value = quantity * price
        margin_required = order_value * self.margin_pct
        
        # Check available margin
        available_margin = self.get_available_margin()
        
        logger.info(
            f"{action} attempt: {symbol} qty={quantity} @ ₹{price:.2f}, "
            f"Cost=₹{order_value:.2f}, Margin=₹{margin_required:.2f}"
        )
        logger.info(
            f"Cash: ₹{self.cash:,.2f}, Used margin: ₹{self.used_margin:.2f}, "
            f"Available: ₹{available_margin:,.2f}"
        )
        
        if margin_required > available_margin:
            logger.warning(
                f"❌ Insufficient margin for {action} {quantity} {symbol}. "
                f"Required: ₹{margin_required:.2f}, Available: ₹{available_margin:.2f}"
            )
            return None
        
        # Execute the order
        if action.upper() == "BUY":
            position = {
                'symbol': symbol,
                'action': 'LONG',
                'quantity': quantity,
                'entry_price': price,
                'current_price': price,
                'stoploss': stoploss if stoploss else 0,
                'target': target if target else 0,
                'order_id': order_id,
                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'pnl': 0,
                'pnl_percent': 0
            }
            
            self.positions[symbol] = position
            self.used_margin += margin_required
            
            logger.info(
                f"✓ BUY EXECUTED (LONG): {quantity} {symbol} @ ₹{price:.2f} "
                f"(SL: ₹{stoploss:.2f if stoploss else 0:.2f}, "
                f"Target: ₹{target:.2f if target else 0:.2f})"
            )
            
        elif action.upper() == "SELL":
            position = {
                'symbol': symbol,
                'action': 'SHORT',
                'quantity': quantity,
                'entry_price': price,
                'current_price': price,
                'stoploss': stoploss if stoploss else 0,
                'target': target if target else 0,
                'order_id': order_id,
                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'pnl': 0,
                'pnl_percent': 0
            }
            
            self.positions[symbol] = position
            self.used_margin += margin_required
            
            logger.info(
                f"✓ SELL EXECUTED (SHORT): {quantity} {symbol} @ ₹{price:.2f} "
                f"(SL: ₹{stoploss:.2f if stoploss else 0:.2f}, "
                f"Target: ₹{target:.2f if target else 0:.2f})"
            )
        
        # Log to Excel if trade_logger is available
        if self.trade_logger:
            try:
                self.trade_logger.log_entry(
                    order_id=order_id,
                    symbol=symbol,
                    action=action.upper(),
                    quantity=quantity,
                    price=price,
                    stoploss=stoploss,
                    target=target,
                    remarks=f"Paper {action.upper()} - {position['action']}"
                )
            except Exception as e:
                logger.error(f"Error logging trade to Excel: {e}")
        
        return order_id
    
    def update_position(self, symbol, current_price):
        """
        Update position with current market price and calculate P&L
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        position['current_price'] = current_price
        
        # Calculate P&L
        entry_value = position['entry_price'] * position['quantity']
        current_value = current_price * position['quantity']
        
        if position['action'] == 'LONG':
            position['pnl'] = current_value - entry_value
        else:  # SHORT
            position['pnl'] = entry_value - current_value
        
        position['pnl_percent'] = (position['pnl'] / entry_value) * 100
    
    def close_position(self, symbol, exit_price, reason='Manual'):
        """
        Close an open position
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            reason: Reason for closing (Manual, SL hit, Target hit, etc.)
            
        Returns:
            bool: True if closed successfully
        """
        if symbol not in self.positions:
            logger.warning(f"No open position found for {symbol}")
            return False
        
        position = self.positions[symbol]
        
        # Calculate final P&L
        entry_value = position['entry_price'] * position['quantity']
        exit_value = exit_price * position['quantity']
        
        if position['action'] == 'LONG':
            pnl = exit_value - entry_value
        else:  # SHORT
            pnl = entry_value - exit_value
        
        pnl_percent = (pnl / entry_value) * 100
        
        # Update cash
        self.cash += pnl
        
        # Free up margin
        margin_used = entry_value * self.margin_pct
        self.used_margin -= margin_used
        
        logger.info(
            f"✓ POSITION CLOSED: {symbol} @ ₹{exit_price:.2f} | "
            f"P&L: ₹{pnl:.2f} ({pnl_percent:+.2f}%) | "
            f"Reason: {reason}"
        )
        
        # Log exit to Excel
        if self.trade_logger and 'order_id' in position:
            try:
                self.trade_logger.log_exit(
                    order_id=position['order_id'],
                    exit_price=exit_price,
                    remarks=reason
                )
            except Exception as e:
                logger.error(f"Error logging exit to Excel: {e}")
        
        # Add to history
        self.trade_history.append({
            'symbol': symbol,
            'action': position['action'],
            'quantity': position['quantity'],
            'entry_price': position['entry_price'],
            'exit_price': exit_price,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'entry_time': position['entry_time'],
            'exit_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'reason': reason
        })
        
        # Remove position
        del self.positions[symbol]
        
        return True
    
    def check_stoploss_target(self, symbol, current_price):
        """
        Check if stop loss or target is hit
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            
        Returns:
            str: 'SL' if stop loss hit, 'TARGET' if target hit, None otherwise
        """
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        
        if position['action'] == 'LONG':
            # Check stop loss
            if position['stoploss'] > 0 and current_price <= position['stoploss']:
                self.close_position(symbol, current_price, 'Stop Loss Hit')
                return 'SL'
            
            # Check target
            if position['target'] > 0 and current_price >= position['target']:
                self.close_position(symbol, current_price, 'Target Hit')
                return 'TARGET'
        
        else:  # SHORT position
            # Check stop loss
            if position['stoploss'] > 0 and current_price >= position['stoploss']:
                self.close_position(symbol, current_price, 'Stop Loss Hit')
                return 'SL'
            
            # Check target
            if position['target'] > 0 and current_price <= position['target']:
                self.close_position(symbol, current_price, 'Target Hit')
                return 'TARGET'
        
        return None
    
    def get_portfolio_value(self):
        """Calculate total portfolio value"""
        cash_value = self.cash
        positions_value = sum(
            pos.get('pnl', 0) for pos in self.positions.values()
        )
        return cash_value + positions_value
    
    def get_positions(self):
        """Get all open positions"""
        return self.positions
    
    def get_position(self, symbol):
        """Get specific position"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol):
        """Check if position exists"""
        return symbol in self.positions
    
    def get_summary(self):
        """Get portfolio summary"""
        total_value = self.get_portfolio_value()
        total_pnl = total_value - self.initial_cash
        pnl_percent = (total_pnl / self.initial_cash) * 100
        
        return {
            'initial_cash': self.initial_cash,
            'current_cash': self.cash,
            'used_margin': self.used_margin,
            'available_margin': self.get_available_margin(),
            'total_value': total_value,
            'total_pnl': total_pnl,
            'pnl_percent': pnl_percent,
            'open_positions': len(self.positions),
            'total_trades': len(self.trade_history)
        }
    
    def holdings_snapshot(self):
        """Get holdings snapshot for UI compatibility"""
        return {
            'cash': self.cash,
            'used_margin': self.used_margin,
            'available_margin': self.get_available_margin(),
            'total_positions': len(self.positions),
            'positions': self.positions,
            'leverage': self.leverage
        }
    
    def square_off_all(self, provider):
        """Square off all positions using current market prices"""
        closed_count = 0
        for symbol in list(self.positions.keys()):
            try:
                current_price = provider.get_ltp(symbol, 'NSE')
                if current_price:
                    self.close_position(symbol, current_price, 'Square Off All')
                    closed_count += 1
            except Exception as e:
                logger.error(f"Error closing {symbol}: {e}")
        
        logger.info(f"Squared off {closed_count} positions")
        return closed_count