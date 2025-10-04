# order_manager/paper_trader_hotfix.py
"""
Quick hotfix for paper trading issues
Simple, reliable implementation for immediate use
"""
import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger("PaperTraderHotfix")


class SimplePaperTrader:
    """Simple, reliable paper trader for immediate use"""
    
    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        
        # Simple data structures
        self.positions = {}  # {symbol: {'side': 'BUY', 'qty': 10, 'avg_price': 100, 'invested': 1000}}
        self.trades = []     # List of all trades
        
        # Data file
        self.data_file = "data/simple_paper_trading.json"
        
        # Load existing data
        self.load_data()
        
        logger.info(f"Simple paper trader initialized. Balance: Rs{self.current_balance:,.2f}")

    def place_order(self, symbol: str, side: str, quantity: int, price: float) -> Tuple[bool, str]:
        """Place a simple order"""
        try:
            # Validate basic inputs
            if not all([symbol, side, quantity, price]):
                return False, "Invalid order parameters"
            
            if side not in ["BUY", "SELL"]:
                return False, "Side must be BUY or SELL"
            
            if quantity <= 0 or price <= 0:
                return False, "Quantity and price must be positive"
            
            # Check for SELL without position
            if side == "SELL":
                if symbol not in self.positions:
                    return False, f"Cannot sell {symbol} - No position found. Place BUY order first."
                
                current_pos = self.positions[symbol]
                if current_pos['side'] != 'BUY':
                    return False, f"Cannot sell {symbol} - Current position is {current_pos['side']}"
                
                if quantity > current_pos['qty']:
                    return False, f"Cannot sell {quantity} shares - Only {current_pos['qty']} available"
            
            # Calculate order value
            order_value = price * quantity
            
            # Check balance for BUY orders
            if side == "BUY" and symbol not in self.positions:
                if order_value > self.current_balance:
                    return False, f"Insufficient balance. Required: Rs{order_value:,.2f}, Available: Rs{self.current_balance:,.2f}"
            
            # Generate order ID
            order_id = str(uuid.uuid4())[:8].upper()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Execute order
            if side == "BUY":
                self._execute_buy(symbol, quantity, price, order_id, timestamp)
            else:  # SELL
                self._execute_sell(symbol, quantity, price, order_id, timestamp)
            
            # Record trade
            trade = {
                'order_id': order_id,
                'timestamp': timestamp,
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'order_value': order_value,
                'status': 'EXECUTED'
            }
            self.trades.append(trade)
            
            # Save data
            self.save_data()
            
            message = (f"Order executed successfully!\n"
                      f"Order ID: {order_id}\n"
                      f"Symbol: {symbol}\n"
                      f"Side: {side}\n"
                      f"Quantity: {quantity}\n"
                      f"Price: Rs{price:.2f}\n"
                      f"Total Value: Rs{order_value:,.2f}")
            
            logger.info(f"Order executed: {side} {quantity} {symbol} @ Rs{price:.2f}")
            return True, message
            
        except Exception as e:
            logger.exception(f"Order execution error: {e}")
            return False, f"Order failed: {str(e)}"
    
    def _execute_buy(self, symbol: str, quantity: int, price: float, order_id: str, timestamp: str):
        """Execute BUY order"""
        order_value = price * quantity
        
        if symbol in self.positions:
            # Add to existing position (averaging)
            current_pos = self.positions[symbol]
            if current_pos['side'] == 'BUY':
                # Average the position
                total_qty = current_pos['qty'] + quantity
                total_invested = current_pos['invested'] + order_value
                avg_price = total_invested / total_qty
                
                self.positions[symbol] = {
                    'side': 'BUY',
                    'qty': total_qty,
                    'avg_price': avg_price,
                    'invested': total_invested
                }
            else:
                # Close SELL position and create new BUY
                if quantity >= current_pos['qty']:
                    # Close SELL, create BUY
                    remaining_qty = quantity - current_pos['qty']
                    if remaining_qty > 0:
                        self.positions[symbol] = {
                            'side': 'BUY',
                            'qty': remaining_qty,
                            'avg_price': price,
                            'invested': remaining_qty * price
                        }
                    else:
                        # Exact close
                        del self.positions[symbol]
                else:
                    # Reduce SELL position
                    self.positions[symbol]['qty'] -= quantity
                    self.positions[symbol]['invested'] -= quantity * self.positions[symbol]['avg_price']
        else:
            # Create new BUY position
            self.positions[symbol] = {
                'side': 'BUY',
                'qty': quantity,
                'avg_price': price,
                'invested': order_value
            }
        
        # Deduct from balance
        self.current_balance -= order_value
    
    def _execute_sell(self, symbol: str, quantity: int, price: float, order_id: str, timestamp: str):
        """Execute SELL order"""
        if symbol not in self.positions:
            return  # Should not reach here due to validation
        
        current_pos = self.positions[symbol]
        order_value = price * quantity
        
        if quantity == current_pos['qty']:
            # Close entire position
            invested_portion = current_pos['invested']
            pnl = order_value - invested_portion
            self.current_balance += order_value
            del self.positions[symbol]
            logger.info(f"Position closed: {symbol}, P&L: Rs{pnl:.2f}")
        else:
            # Partial sell
            sell_ratio = quantity / current_pos['qty']
            invested_portion = current_pos['invested'] * sell_ratio
            pnl = order_value - invested_portion
            
            # Update position
            self.positions[symbol]['qty'] -= quantity
            self.positions[symbol]['invested'] -= invested_portion
            
            self.current_balance += order_value
            logger.info(f"Partial sell: {symbol}, P&L: Rs{pnl:.2f}")
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        total_invested = sum(pos['invested'] for pos in self.positions.values())
        
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
            
            logger.info("Portfolio reset successfully")
            return True, "Portfolio reset successfully"
        except Exception as e:
            logger.exception(f"Reset error: {e}")
            return False, f"Reset failed: {str(e)}"
    
    def save_data(self):
        """Save data to file"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            data = {
                'current_balance': self.current_balance,
                'initial_balance': self.initial_balance,
                'positions': self.positions,
                'trades': self.trades[-100:]  # Keep last 100 trades
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.exception(f"Save error: {e}")
    
    def load_data(self):
        """Load data from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                
                self.current_balance = data.get('current_balance', self.initial_balance)
                self.initial_balance = data.get('initial_balance', self.initial_balance)
                self.positions = data.get('positions', {})
                self.trades = data.get('trades', [])
                
                logger.info(f"Data loaded. Balance: Rs{self.current_balance:,.2f}, Positions: {len(self.positions)}")
        except Exception as e:
            logger.exception(f"Load error: {e}")


# For compatibility with existing code
class PaperTrader(SimplePaperTrader):
    """Alias for compatibility"""
    pass