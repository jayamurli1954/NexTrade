# order_manager/intraday_paper_trader.py
"""
================================================================================
                    INTRADAY-AWARE PAPER TRADER - FIXED VERSION
================================================================================
Angel One SmartAPI Compliant Paper Trading System
Fixed compatibility issues with main.py and UI threading

Version: 3.1.1
Date: 2025-09-25
================================================================================
"""

import json
import os
from datetime import datetime, time
from typing import Dict, Tuple, Optional, List
import logging
from dataclasses import dataclass, asdict
from enum import Enum

# Configure logging
logger = logging.getLogger("IntradayPaperTrader")

class ProductType(Enum):
    """Angel One Product Types"""
    MIS = "MIS"      # Margin Intraday Square-off
    CNC = "CNC"      # Cash and Carry (Delivery)
    NRML = "NRML"    # Normal (F&O, overnight positions)

class OrderSide(Enum):
    """Order sides"""
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    """Order status"""
    OPEN = "OPEN"
    EXECUTED = "EXECUTED"
    SQUARED_OFF = "SQUARED_OFF"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TARGET_HIT = "TARGET_HIT"
    AUTO_SQUARED = "AUTO_SQUARED"

@dataclass
class Position:
    """Trading position"""
    symbol: str
    quantity: int
    avg_price: float
    product_type: str
    side: str  # BUY or SELL for intraday positions
    entry_time: str
    current_price: float = 0.0
    pnl: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    def calculate_pnl(self, current_price: float) -> float:
        """Calculate P&L based on position side"""
        self.current_price = current_price
        
        if self.side == "BUY":
            # Long position: profit when price goes up
            self.pnl = (current_price - self.avg_price) * self.quantity
        else:  # SELL
            # Short position: profit when price goes down
            self.pnl = (self.avg_price - current_price) * self.quantity
            
        return self.pnl

@dataclass
class Order:
    """Trading order"""
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    product_type: str
    timestamp: str
    status: str = "EXECUTED"
    pnl: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class IntradayPaperTrader:
    """
    Angel One SmartAPI Compliant Paper Trader
    Supports proper intraday trading mechanics
    """
    
    def __init__(self, initial_balance: float = 100000.0):
        """Initialize with Angel One trading rules"""
        self.data_file = "data/intraday_paper_trading.json"
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Angel One Risk Management Settings
        self.default_stop_loss_pct = 2.0    # 2% stop loss
        self.default_take_profit_pct = 4.0  # 4% take profit
        self.auto_square_off_time = time(15, 25)  # 3:25 PM
        self.leverage_mis = 5.0  # 5x leverage for MIS orders
        
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        # Load existing data
        self.load_data()
        logger.info(f"Intraday paper trader initialized. Balance: Rs{self.balance:,.2f}")

    @property
    def current_balance(self):
        """Backward compatibility property for main.py"""
        return self.balance

    @property
    def portfolio_value(self):
        """Calculate total portfolio value including unrealized P&L"""
        total_pnl = 0
        for position in self.positions.values():
            # Mock current price (in real system, get from market data)
            mock_current_price = position.avg_price * 1.005
            total_pnl += position.calculate_pnl(mock_current_price)
        return self.balance + total_pnl

    def get_balance(self) -> float:
        """Get current balance - UI compatibility"""
        return self.balance

    def get_total_pnl(self) -> float:
        """Calculate total unrealized P&L"""
        total_pnl = 0
        for position in self.positions.values():
            # Mock current price (in real system, get from market data)
            mock_current_price = position.avg_price * 1.005
            total_pnl += position.calculate_pnl(mock_current_price)
        return total_pnl

    def load_data(self):
        """Load paper trading data from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    
                self.balance = data.get('balance', self.initial_balance)
                self.total_trades = data.get('total_trades', 0)
                self.winning_trades = data.get('winning_trades', 0)
                self.losing_trades = data.get('losing_trades', 0)
                
                # Load positions
                positions_data = data.get('positions', {})
                for symbol, pos_data in positions_data.items():
                    self.positions[symbol] = Position(**pos_data)
                
                # Load orders
                orders_data = data.get('orders', [])
                self.orders = [Order(**order_data) for order_data in orders_data]
                
                logger.info(f"Data loaded. Balance: Rs{self.balance:,.2f}, Positions: {len(self.positions)}")
                
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self.reset_data()

    def save_data(self):
        """Save paper trading data to file"""
        try:
            data = {
                'balance': self.balance,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'positions': {symbol: asdict(pos) for symbol, pos in self.positions.items()},
                'orders': [asdict(order) for order in self.orders],
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def place_order(self, symbol: str, side: str, quantity: int, price: float, 
                   product_type: str = "MIS") -> Tuple[bool, str]:
        """
        Place order with Angel One SmartAPI compliant logic
        
        Args:
            symbol: Stock symbol (e.g., "TCS", "RELIANCE")
            side: "BUY" or "SELL"
            quantity: Number of shares
            price: Order price
            product_type: "MIS" (intraday), "CNC" (delivery), "NRML" (normal)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Validate inputs
            if side not in ["BUY", "SELL"]:
                return False, "Invalid order side. Use 'BUY' or 'SELL'"
            
            if product_type not in ["MIS", "CNC", "NRML"]:
                return False, "Invalid product type. Use 'MIS', 'CNC', or 'NRML'"
            
            if quantity <= 0 or price <= 0:
                return False, "Quantity and price must be positive"

            # Check market hours for MIS orders
            if product_type == "MIS":
                current_time = datetime.now().time()
                if current_time >= self.auto_square_off_time:
                    return False, "MIS orders not allowed after 3:25 PM (auto square-off time)"

            # Calculate order value
            order_value = quantity * price
            
            # Apply leverage for MIS orders
            if product_type == "MIS":
                required_margin = order_value / self.leverage_mis
            else:
                required_margin = order_value

            # For CNC SELL orders, check if we have the position (delivery logic)
            if product_type == "CNC" and side == "SELL":
                position_key = f"{symbol}_{product_type}"
                if position_key not in self.positions:
                    return False, f"No {symbol} position found for delivery sale. Buy first for CNC orders."
                
                existing_pos = self.positions[position_key]
                if existing_pos.side != "BUY":
                    return False, f"Cannot sell {symbol} - no long position in delivery account"
                
                if existing_pos.quantity < quantity:
                    return False, f"Insufficient {symbol} quantity. Available: {existing_pos.quantity}, Requested: {quantity}"

            # For BUY orders, check balance
            if side == "BUY":
                if self.balance < required_margin:
                    return False, f"Insufficient balance. Required: Rs{required_margin:,.2f}, Available: Rs{self.balance:,.2f}"
            
            # For MIS SELL orders (short selling), check margin requirement
            elif product_type == "MIS" and side == "SELL":
                if self.balance < required_margin:
                    return False, f"Insufficient margin for short selling. Required: Rs{required_margin:,.2f}, Available: Rs{self.balance:,.2f}"

            # Execute the order
            order_id = f"ORD_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.orders)+1}"
            
            # Calculate stop loss and take profit
            if side == "BUY":
                stop_loss = price * (1 - self.default_stop_loss_pct / 100)
                take_profit = price * (1 + self.default_take_profit_pct / 100)
            else:  # SELL (short position)
                stop_loss = price * (1 + self.default_stop_loss_pct / 100)
                take_profit = price * (1 - self.default_take_profit_pct / 100)

            # Create order record
            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                product_type=product_type,
                timestamp=datetime.now().isoformat(),
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # Update positions
            position_key = f"{symbol}_{product_type}"
            
            if position_key in self.positions:
                # Update existing position
                existing_pos = self.positions[position_key]
                
                if product_type == "MIS":
                    # For intraday, handle both long and short positions
                    if existing_pos.side == side:
                        # Same side - add to position
                        total_value = (existing_pos.quantity * existing_pos.avg_price) + (quantity * price)
                        total_quantity = existing_pos.quantity + quantity
                        existing_pos.avg_price = total_value / total_quantity
                        existing_pos.quantity = total_quantity
                    else:
                        # Opposite side - square off or reverse
                        if existing_pos.quantity == quantity:
                            # Complete square off
                            pnl = existing_pos.calculate_pnl(price)
                            self.balance += pnl
                            self.update_trade_stats(pnl)
                            del self.positions[position_key]
                            order.pnl = pnl
                            order.status = "SQUARED_OFF"
                        elif existing_pos.quantity > quantity:
                            # Partial square off
                            pnl = (existing_pos.avg_price - price if existing_pos.side == "BUY" else price - existing_pos.avg_price) * quantity
                            self.balance += pnl
                            existing_pos.quantity -= quantity
                            order.pnl = pnl
                        else:
                            # Reverse position
                            pnl = existing_pos.calculate_pnl(price)
                            self.balance += pnl
                            remaining_qty = quantity - existing_pos.quantity
                            existing_pos.side = side
                            existing_pos.quantity = remaining_qty
                            existing_pos.avg_price = price
                            order.pnl = pnl
                
                elif product_type == "CNC":
                    # For delivery, simple add/subtract logic
                    if side == "BUY":
                        total_value = (existing_pos.quantity * existing_pos.avg_price) + (quantity * price)
                        existing_pos.quantity += quantity
                        existing_pos.avg_price = total_value / existing_pos.quantity
                    else:  # SELL
                        existing_pos.quantity -= quantity
                        if existing_pos.quantity == 0:
                            del self.positions[position_key]
                        
            else:
                # Create new position
                position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price,
                    product_type=product_type,
                    side=side,
                    entry_time=datetime.now().isoformat(),
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                self.positions[position_key] = position

            # Update balance based on order type
            if side == "BUY":
                self.balance -= required_margin
            # For MIS SELL (short), margin is blocked but no immediate cash flow
            # For CNC SELL, add the sale proceeds
            elif product_type == "CNC" and side == "SELL":
                self.balance += order_value

            # Add to orders list
            self.orders.append(order)
            self.total_trades += 1
            
            # Save data
            self.save_data()
            
            # Log the order
            logger.info(f"Order executed: {side} {quantity} {symbol} @ Rs{price:.2f} ({product_type})")
            
            return True, f"Order executed successfully: {side} {quantity} {symbol} @ Rs{price:.2f} ({product_type})"
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return False, f"Order failed: {str(e)}"

    def get_positions(self) -> Dict[str, Dict]:
        """Get current positions with P&L"""
        position_summary = {}
        
        for key, position in self.positions.items():
            # For demo, use a mock current price (in real system, get from market data)
            mock_current_price = position.avg_price * (1 + 0.005)  # Assume 0.5% movement
            pnl = position.calculate_pnl(mock_current_price)
            
            position_summary[key] = {
                'symbol': position.symbol,
                'quantity': position.quantity,
                'avg_price': position.avg_price,
                'current_price': mock_current_price,
                'side': position.side,
                'product_type': position.product_type,
                'pnl': pnl,
                'pnl_pct': (pnl / (position.quantity * position.avg_price)) * 100,
                'stop_loss': position.stop_loss,
                'take_profit': position.take_profit,
                'entry_time': position.entry_time
            }
            
        return position_summary

    def get_order_history(self) -> List[Dict]:
        """Get order history"""
        return [asdict(order) for order in self.orders[-10:]]  # Last 10 orders

    def get_position_summary(self) -> List[Dict]:
        """Get position summary for UI compatibility"""
        positions = []
        for key, position in self.positions.items():
            mock_current_price = position.avg_price * 1.005
            pnl = position.calculate_pnl(mock_current_price)
            
            positions.append({
                'symbol': position.symbol,
                'quantity': position.quantity,
                'avg_price': position.avg_price,
                'current_price': mock_current_price,
                'pnl': pnl,
                'side': position.side,
                'product_type': position.product_type
            })
        return positions

    def auto_square_off_check(self):
        """Check and auto square off MIS positions at 3:25 PM"""
        current_time = datetime.now().time()
        
        if current_time >= self.auto_square_off_time:
            mis_positions = {k: v for k, v in self.positions.items() if v.product_type == "MIS"}
            
            for key, position in mis_positions.items():
                # Auto square off at current market price
                current_price = position.avg_price * 1.001  # Mock price
                pnl = position.calculate_pnl(current_price)
                self.balance += pnl
                self.update_trade_stats(pnl)
                
                # Create auto square off order
                order = Order(
                    order_id=f"AUTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    symbol=position.symbol,
                    side="SELL" if position.side == "BUY" else "BUY",
                    quantity=position.quantity,
                    price=current_price,
                    product_type="MIS",
                    timestamp=datetime.now().isoformat(),
                    status="AUTO_SQUARED",
                    pnl=pnl
                )
                self.orders.append(order)
                
                logger.info(f"Auto squared off: {position.symbol} P&L: Rs{pnl:.2f}")
            
            # Remove all MIS positions
            self.positions = {k: v for k, v in self.positions.items() if v.product_type != "MIS"}
            self.save_data()

    def update_trade_stats(self, pnl: float):
        """Update trading statistics"""
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        total_pnl = sum(pos.calculate_pnl(pos.avg_price * 1.005) for pos in self.positions.values())
        
        return {
            'balance': self.balance,
            'initial_balance': self.initial_balance,
            'total_pnl': total_pnl,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': (self.winning_trades / max(self.total_trades, 1)) * 100,
            'active_positions': len(self.positions),
            'equity_value': self.balance + total_pnl
        }

    def reset_paper_trading(self):
        """Reset paper trading data"""
        self.balance = self.initial_balance
        self.positions.clear()
        self.orders.clear()
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Delete data file
        if os.path.exists(self.data_file):
            os.remove(self.data_file)
        
        self.save_data()
        logger.info("Paper trading data reset successfully")

# Create alias for backward compatibility
PaperTrader = IntradayPaperTrader

if __name__ == "__main__":
    # Test the intraday paper trader
    trader = IntradayPaperTrader()
    
    # Test intraday short selling
    print("Testing MIS short selling...")
    success, msg = trader.place_order("TCS", "SELL", 10, 3987.20, "MIS")
    print(f"Short sell result: {success} - {msg}")
    
    # Test current_balance property
    print(f"Current balance: Rs{trader.current_balance:,.2f}")
    
    # Test portfolio
    portfolio = trader.get_portfolio_summary()
    print(f"Portfolio: {portfolio}")
    
    # Test positions
    positions = trader.get_positions()
    print(f"Positions: {positions}")