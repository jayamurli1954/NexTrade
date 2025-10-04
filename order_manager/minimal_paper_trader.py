# order_manager/minimal_paper_trader.py
"""
Minimal Paper Trader - Focus on core functionality
"""
import json
import os
from datetime import datetime
from typing import Dict, Tuple
import logging

logger = logging.getLogger("MinimalPaperTrader")


class PaperTrader:
    """Minimal paper trader focused on working correctly"""
    
    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.positions = {}  # {symbol: {'qty': 10, 'avg_price': 100.0, 'side': 'BUY'}}
        self.trades = []
        
        # Simple data file
        self.data_file = "data/minimal_paper_data.json"
        self.load_data()
        
        logger.info(f"Minimal paper trader started. Balance: Rs{self.current_balance:,.2f}")

    def place_order(self, symbol: str, side: str, quantity: int, price: float) -> Tuple[bool, str]:
        """Place order with simple logic"""
        try:
            # Basic validation
            if side not in ["BUY", "SELL"]:
                return False, "Side must be BUY or SELL"
            
            # For SELL orders, check if position exists
            if side == "SELL":
                if symbol not in self.positions:
                    return False, f"Cannot sell {symbol} - No position found. Place BUY order first."
                
                pos = self.positions[symbol]
                if pos['side'] != 'BUY':
                    return False, f"Cannot sell {symbol} - No BUY position exists"
                
                if quantity > pos['qty']:
                    return False, f"Cannot sell {quantity} shares - Only {pos['qty']} available"
            
            # Execute the order
            order_value = price * quantity
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if side == "BUY":
                # Check balance
                if order_value > self.current_balance:
                    return False, f"Insufficient balance. Required: Rs{order_value:,.2f}"
                
                # Add to position
                if symbol in self.positions and self.positions[symbol]['side'] == 'BUY':
                    # Average existing position
                    old_pos = self.positions[symbol]
                    total_qty = old_pos['qty'] + quantity
                    total_value = (old_pos['qty'] * old_pos['avg_price']) + order_value
                    new_avg = total_value / total_qty
                    
                    self.positions[symbol] = {
                        'qty': total_qty,
                        'avg_price': new_avg,
                        'side': 'BUY'
                    }
                else:
                    # New position
                    self.positions[symbol] = {
                        'qty': quantity,
                        'avg_price': price,
                        'side': 'BUY'
                    }
                
                self.current_balance -= order_value
                
            else:  # SELL
                pos = self.positions[symbol]
                
                if quantity == pos['qty']:
                    # Close entire position
                    proceeds = order_value
                    cost = pos['qty'] * pos['avg_price']
                    pnl = proceeds - cost
                    
                    self.current_balance += proceeds
                    del self.positions[symbol]
                    
                    logger.info(f"Position closed: {symbol}, P&L: Rs{pnl:.2f}")
                else:
                    # Partial sell
                    proceeds = order_value
                    cost_per_share = pos['avg_price']
                    pnl = (price - cost_per_share) * quantity
                    
                    self.current_balance += proceeds
                    self.positions[symbol]['qty'] -= quantity
                    
                    logger.info(f"Partial sell: {symbol}, P&L: Rs{pnl:.2f}")
            
            # Record trade
            trade = {
                'timestamp': timestamp,
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'value': order_value
            }
            self.trades.append(trade)
            
            # Save data
            self.save_data()
            
            message = (f"Order executed successfully!\n"
                      f"Symbol: {symbol}\n"
                      f"Side: {side}\n"
                      f"Quantity: {quantity}\n"
                      f"Price: Rs{price:.2f}")
            
            return True, message
            
        except Exception as e:
            logger.exception(f"Order error: {e}")
            return False, f"Order failed: {str(e)}"

    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        total_invested = 0
        for pos in self.positions.values():
            if pos['side'] == 'BUY':
                total_invested += pos['qty'] * pos['avg_price']
        
        return {
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'total_invested': total_invested,
            'positions_count': len(self.positions),
            'total_trades': len(self.trades),
            'positions': self.positions.copy()
        }

    def reset_portfolio(self) -> Tuple[bool, str]:
        """Reset portfolio"""
        try:
            self.current_balance = self.initial_balance
            self.positions.clear()
            self.trades.clear()
            self.save_data()
            return True, "Portfolio reset successfully"
        except Exception as e:
            return False, f"Reset failed: {str(e)}"

    def save_data(self):
        """Save data"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            data = {
                'current_balance': self.current_balance,
                'initial_balance': self.initial_balance,
                'positions': self.positions,
                'trades': self.trades[-50:]  # Keep last 50 trades
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.exception(f"Save error: {e}")

    def load_data(self):
        """Load data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                
                self.current_balance = data.get('current_balance', self.initial_balance)
                self.initial_balance = data.get('initial_balance', self.initial_balance) 
                self.positions = data.get('positions', {})
                self.trades = data.get('trades', [])
                
                logger.info(f"Data loaded: Balance Rs{self.current_balance:,.2f}, {len(self.positions)} positions")
        except Exception as e:
            logger.exception(f"Load error: {e}")