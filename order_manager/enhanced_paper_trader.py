# order_manager/enhanced_paper_trader.py
"""
Enhanced Paper Trading Module
Handles intraday positions, detailed order tracking, and risk management
"""
import json
import os
import uuid
from datetime import datetime, time
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger("PaperTrader")


class Position:
    """Represents a trading position"""
    def __init__(self, symbol: str, side: str, quantity: int, entry_price: float, 
                 timestamp: str, order_id: str):
        self.symbol = symbol
        self.side = side  # 'BUY' or 'SELL'
        self.quantity = quantity
        self.entry_price = entry_price
        self.timestamp = timestamp
        self.order_id = order_id
        self.current_ltp = entry_price
        self.exit_price = None
        self.exit_time = None
        self.status = "OPEN"
        
    def update_ltp(self, ltp: float):
        """Update last traded price"""
        self.current_ltp = ltp
        
    def get_pnl(self) -> float:
        """Calculate current P&L"""
        if self.side == 'BUY':
            return (self.current_ltp - self.entry_price) * self.quantity
        else:  # SELL
            return (self.entry_price - self.current_ltp) * self.quantity
            
    def get_pnl_percentage(self) -> float:
        """Calculate P&L percentage"""
        investment = self.entry_price * self.quantity
        if investment == 0:
            return 0
        return (self.get_pnl() / investment) * 100
        
    def close_position(self, exit_price: float):
        """Close the position"""
        self.exit_price = exit_price
        self.exit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.status = "CLOSED"
        self.current_ltp = exit_price


class Order:
    """Represents an order"""
    def __init__(self, symbol: str, side: str, quantity: int, price: float, 
                 order_type: str = "MARKET"):
        self.order_id = str(uuid.uuid4())[:8].upper()
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.order_type = order_type
        self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.status = "PENDING"
        self.executed_price = None
        self.executed_time = None
        
    def execute(self, execution_price: float):
        """Mark order as executed"""
        self.status = "EXECUTED"
        self.executed_price = execution_price
        self.executed_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class EnhancedPaperTrader:
    """Enhanced paper trading system with comprehensive tracking"""
    
    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.positions: Dict[str, Position] = {}  # Active positions
        self.order_history: List[Order] = []
        self.closed_positions: List[Position] = []
        
        # Trading parameters
        self.margin_multiplier = 5.0  # 5x leverage for intraday
        self.brokerage = 0.03  # 0.03% brokerage
        self.square_off_time = time(15, 20)  # Auto square-off at 3:20 PM
        
        # Risk management
        self.max_loss_per_trade = 2.0  # 2% max loss per trade
        self.max_profit_per_trade = 4.0  # 4% max profit per trade (1:2 R:R)
        
        # Load existing data
        self.data_file = "data/paper_trading_data.json"
        self.load_data()
        
        logger.info(f"Enhanced paper trader initialized with balance: Rs{self.current_balance:,.2f}")

    def place_order(self, symbol: str, side: str, quantity: int, 
                   price: float, order_type: str = "INTRADAY") -> Tuple[bool, str]:
        """Place an intraday order"""
        try:
            # Check if trying to sell without position
            if side == "SELL" and symbol not in self.positions:
                return False, f"Cannot sell {symbol} - No position found. Place BUY order first."
            
            # Check if trying to sell more than available quantity
            if side == "SELL" and symbol in self.positions:
                current_position = self.positions[symbol]
                if current_position.side != "BUY":
                    return False, f"Cannot sell {symbol} - Current position is SELL"
                if quantity > current_position.quantity:
                    return False, f"Cannot sell {quantity} shares - Only {current_position.quantity} available"
            
            # Calculate order value
            order_value = price * quantity
            required_margin = order_value / self.margin_multiplier if order_type == "INTRADAY" else order_value
            brokerage_cost = order_value * (self.brokerage / 100)
            total_required = required_margin + brokerage_cost
            
            # Check balance for new BUY positions
            if side == "BUY" and symbol not in self.positions:
                if total_required > self.current_balance:
                    return False, f"Insufficient balance. Required: Rs{total_required:,.2f}, Available: Rs{self.current_balance:,.2f}"
            
            # Create and execute order
            order = Order(symbol, side, quantity, price, order_type)
            execution_price = self._get_execution_price(price, side)
            order.execute(execution_price)
            self.order_history.append(order)
            
            # Handle position logic
            if side == "BUY":
                self._handle_buy_order(order, execution_price)
            else:  # SELL
                self._handle_sell_order(order, execution_price)
            
            self.save_data()
            
            message = (f"Order executed successfully!\n"
                      f"Order ID: {order.order_id}\n"
                      f"Symbol: {symbol}\n"
                      f"Side: {side}\n"
                      f"Quantity: {quantity}\n"
                      f"Price: Rs{execution_price:.2f}")
            
            logger.info(f"Order placed: {side} {quantity} {symbol} @ Rs{execution_price:.2f}")
            return True, message
            
        except Exception as e:
            logger.exception(f"Order placement error: {e}")
            return False, f"Order failed: {str(e)}"
    
    def _handle_buy_order(self, order: Order, execution_price: float):
        """Handle BUY order execution"""
        symbol = order.symbol
        quantity = order.quantity
        
        if symbol in self.positions:
            # Add to existing position (averaging)
            existing_pos = self.positions[symbol]
            if existing_pos.side == "BUY":
                total_qty = existing_pos.quantity + quantity
                total_value = (existing_pos.entry_price * existing_pos.quantity) + (execution_price * quantity)
                avg_price = total_value / total_qty
                
                existing_pos.quantity = total_qty
                existing_pos.entry_price = avg_price
            else:
                # Close existing SELL position
                self._close_position(symbol, execution_price)
                
                # Create new BUY position if quantity is more
                if quantity > existing_pos.quantity:
                    remaining_qty = quantity - existing_pos.quantity
                    new_position = Position(symbol, "BUY", remaining_qty, execution_price,
                                          order.executed_time, order.order_id)
                    self.positions[symbol] = new_position
                elif quantity < existing_pos.quantity:
                    # Reduce existing SELL position
                    existing_pos.quantity -= quantity
                else:
                    # Exact match - position closed
                    pass
        else:
            # Create new BUY position
            new_position = Position(symbol, "BUY", quantity, execution_price,
                                  order.executed_time, order.order_id)
            self.positions[symbol] = new_position
        
        # Deduct cost from balance
        order_value = execution_price * quantity
        required_margin = order_value / self.margin_multiplier
        brokerage_cost = order_value * (self.brokerage / 100)
        self.current_balance -= (required_margin + brokerage_cost)
    
    def _handle_sell_order(self, order: Order, execution_price: float):
        """Handle SELL order execution"""
        symbol = order.symbol
        quantity = order.quantity
        
        if symbol in self.positions:
            existing_pos = self.positions[symbol]
            
            if existing_pos.side == "BUY":
                if quantity == existing_pos.quantity:
                    # Close entire position
                    self._close_position(symbol, execution_price)
                elif quantity < existing_pos.quantity:
                    # Partial sell
                    pnl = (execution_price - existing_pos.entry_price) * quantity
                    self.current_balance += (execution_price * quantity) + pnl
                    existing_pos.quantity -= quantity
                else:
                    # Selling more than held - this should be caught earlier
                    logger.warning(f"Attempting to sell more than held for {symbol}")
            else:
                # Add to existing SELL position
                total_qty = existing_pos.quantity + quantity
                total_value = (existing_pos.entry_price * existing_pos.quantity) + (execution_price * quantity)
                avg_price = total_value / total_qty
                
                existing_pos.quantity = total_qty
                existing_pos.entry_price = avg_price
        
        # Add proceeds to balance (for new SELL positions this handles the margin)
        order_value = execution_price * quantity
        brokerage_cost = order_value * (self.brokerage / 100)
        if symbol not in self.positions or self.positions[symbol].side != "SELL":
            self.current_balance += order_value - brokerage_cost
    
    def _close_position(self, symbol: str, exit_price: float):
        """Close a position and calculate P&L"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        position.close_position(exit_price)
        
        # Calculate P&L
        pnl = position.get_pnl()
        order_value = exit_price * position.quantity
        brokerage_cost = order_value * (self.brokerage / 100)
        
        # Update balance
        if position.side == "BUY":
            # Return margin + P&L
            margin_returned = (position.entry_price * position.quantity) / self.margin_multiplier
            self.current_balance += margin_returned + pnl - brokerage_cost
        else:  # SELL position
            margin_returned = (position.entry_price * position.quantity) / self.margin_multiplier
            self.current_balance += margin_returned - pnl - brokerage_cost
        
        # Move to closed positions
        self.closed_positions.append(position)
        del self.positions[symbol]
        
        logger.info(f"Position closed: {symbol} P&L: Rs{pnl:.2f}")
    
    def _get_execution_price(self, price: float, side: str) -> float:
        """Simulate realistic execution price with slippage"""
        import random
        slippage_percent = random.uniform(0.01, 0.05)  # 0.01% to 0.05% slippage
        
        if side == "BUY":
            return price * (1 + slippage_percent / 100)
        else:
            return price * (1 - slippage_percent / 100)
    
    def update_ltp(self, symbol: str, ltp: float):
        """Update last traded price for a symbol"""
        if symbol in self.positions:
            self.positions[symbol].update_ltp(ltp)
            self._check_risk_management(symbol)
    
    def _check_risk_management(self, symbol: str):
        """Check if position needs to be closed due to risk management rules"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        pnl_percent = position.get_pnl_percentage()
        
        # Auto close on stop loss
        if pnl_percent <= -self.max_loss_per_trade:
            logger.info(f"Stop loss triggered for {symbol} at {pnl_percent:.2f}%")
            self._close_position(symbol, position.current_ltp)
        
        # Auto close on target profit
        elif pnl_percent >= self.max_profit_per_trade:
            logger.info(f"Target profit reached for {symbol} at {pnl_percent:.2f}%")
            self._close_position(symbol, position.current_ltp)
    
    def square_off_all_positions(self) -> List[str]:
        """Square off all open positions (end of day)"""
        closed_symbols = []
        
        for symbol in list(self.positions.keys()):
            position = self.positions[symbol]
            # Use current LTP or entry price as square-off price
            square_off_price = position.current_ltp
            self._close_position(symbol, square_off_price)
            closed_symbols.append(symbol)
        
        self.save_data()
        logger.info(f"All positions squared off: {closed_symbols}")
        return closed_symbols
    
    def get_portfolio_summary(self) -> Dict:
        """Get comprehensive portfolio summary"""
        total_invested = sum(pos.entry_price * pos.quantity / self.margin_multiplier 
                           for pos in self.positions.values())
        
        unrealized_pnl = sum(pos.get_pnl() for pos in self.positions.values())
        realized_pnl = sum(pos.get_pnl() for pos in self.closed_positions)
        
        return {
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'total_invested': total_invested,
            'positions_count': len(self.positions),
            'total_trades': len(self.order_history),
            'unrealized_pnl': unrealized_pnl,
            'realized_pnl': realized_pnl,
            'total_pnl': unrealized_pnl + realized_pnl,
            'positions': {symbol: {
                'side': pos.side,
                'qty': pos.quantity,
                'entry_price': pos.entry_price,
                'current_ltp': pos.current_ltp,
                'pnl': pos.get_pnl(),
                'pnl_percent': pos.get_pnl_percentage(),
                'entry_time': pos.timestamp
            } for symbol, pos in self.positions.items()}
        }
    
    def get_order_book(self) -> List[Dict]:
        """Get detailed order book"""
        orders = []
        
        for order in self.order_history[-20:]:  # Last 20 orders
            orders.append({
                'order_id': order.order_id,
                'symbol': order.symbol,
                'side': order.side,
                'quantity': order.quantity,
                'order_price': order.price,
                'executed_price': order.executed_price,
                'status': order.status,
                'timestamp': order.timestamp,
                'executed_time': order.executed_time
            })
        
        return orders
    
    def get_closed_trades(self) -> List[Dict]:
        """Get closed trades with P&L"""
        trades = []
        
        for pos in self.closed_positions[-10:]:  # Last 10 closed trades
            trades.append({
                'symbol': pos.symbol,
                'side': pos.side,
                'quantity': pos.quantity,
                'entry_price': pos.entry_price,
                'exit_price': pos.exit_price,
                'entry_time': pos.timestamp,
                'exit_time': pos.exit_time,
                'pnl': pos.get_pnl(),
                'pnl_percent': pos.get_pnl_percentage()
            })
        
        return trades
    
    def reset_portfolio(self) -> Tuple[bool, str]:
        """Reset paper trading portfolio"""
        try:
            self.current_balance = self.initial_balance
            self.positions.clear()
            self.order_history.clear()
            self.closed_positions.clear()
            
            self.save_data()
            logger.info("Paper trading portfolio reset")
            return True, "Portfolio reset successfully"
            
        except Exception as e:
            logger.exception(f"Portfolio reset error: {e}")
            return False, f"Reset failed: {str(e)}"
    
    def save_data(self):
        """Save trading data to file"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            data = {
                'current_balance': self.current_balance,
                'positions': {symbol: {
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'timestamp': pos.timestamp,
                    'order_id': pos.order_id,
                    'current_ltp': pos.current_ltp
                } for symbol, pos in self.positions.items()},
                'order_history': [{
                    'order_id': order.order_id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'order_type': order.order_type,
                    'timestamp': order.timestamp,
                    'status': order.status,
                    'executed_price': order.executed_price,
                    'executed_time': order.executed_time
                } for order in self.order_history],
                'closed_positions': [{
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'timestamp': pos.timestamp,
                    'order_id': pos.order_id,
                    'current_ltp': pos.current_ltp,
                    'exit_price': pos.exit_price,
                    'exit_time': pos.exit_time,
                    'status': pos.status
                } for pos in self.closed_positions]
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.exception(f"Data save error: {e}")
    
    def load_data(self):
        """Load trading data from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                
                self.current_balance = data.get('current_balance', self.initial_balance)
                
                # Load positions
                for symbol, pos_data in data.get('positions', {}).items():
                    pos = Position(
                        pos_data['symbol'], pos_data['side'], pos_data['quantity'],
                        pos_data['entry_price'], pos_data['timestamp'], pos_data['order_id']
                    )
                    pos.current_ltp = pos_data.get('current_ltp', pos_data['entry_price'])
                    self.positions[symbol] = pos
                
                # Load order history
                for order_data in data.get('order_history', []):
                    order = Order(
                        order_data['symbol'], order_data['side'], order_data['quantity'],
                        order_data['price'], order_data.get('order_type', 'MARKET')
                    )
                    order.order_id = order_data['order_id']
                    order.timestamp = order_data['timestamp']
                    order.status = order_data['status']
                    order.executed_price = order_data.get('executed_price')
                    order.executed_time = order_data.get('executed_time')
                    self.order_history.append(order)
                
                # Load closed positions
                for pos_data in data.get('closed_positions', []):
                    pos = Position(
                        pos_data['symbol'], pos_data['side'], pos_data['quantity'],
                        pos_data['entry_price'], pos_data['timestamp'], pos_data['order_id']
                    )
                    pos.current_ltp = pos_data.get('current_ltp', pos_data['entry_price'])
                    pos.exit_price = pos_data.get('exit_price')
                    pos.exit_time = pos_data.get('exit_time')
                    pos.status = pos_data.get('status', 'CLOSED')
                    self.closed_positions.append(pos)
                
                logger.info(f"Paper trading data loaded. Balance: Rs{self.current_balance:,.2f}")
                
        except Exception as e:
            logger.exception(f"Data load error: {e}")
    
    def is_market_open(self) -> bool:
        """Check if market is open for trading"""
        now = datetime.now().time()
        market_start = time(9, 15)
        market_end = time(15, 30)
        
        return market_start <= now <= market_end