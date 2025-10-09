import os
import re

def patch_paper_trader(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Patch for execute_order in sell: Fix KeyError by checking if 'quantity' exists
    execute_pattern = r'def execute_order\(self, symbol, action, quantity, price, stoploss=None, target=None\):.*?return order_id'
    new_execute = r'''def execute_order(self, symbol, action, quantity, price, stoploss=None, target=None):
        order_id = f"P{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        
        order_value = quantity * price
        margin_required = order_value * self.margin_pct
        
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

        if action.upper() == 'BUY':
            self.positions[symbol] = {
                'action': 'LONG',
                'quantity': quantity,
                'entry_price': price,
                'current_price': price,
                'pnl': 0,
                'pnl_percent': 0,
                'stoploss': stoploss or 0,
                'target': target or 0,
                'entry_time': datetime.now().isoformat()
            }
            self.used_margin += margin_required
            self.cash -= order_value  # Deduct full value for buy
            logger.info(f"✅ BUY executed: {quantity} x {symbol} @ ₹{price:.2f}")
            
        elif action.upper() == 'SELL':
            if symbol in self.positions and 'quantity' in self.positions[symbol]:
                existing_qty = self.positions[symbol]['quantity']
                if existing_qty > 0:  # Closing long
                    close_qty = min(quantity, existing_qty)
                    pnl = (price - self.positions[symbol]['entry_price']) * close_qty
                    self.positions[symbol]['quantity'] -= close_qty
                    self.used_margin -= (close_qty * self.positions[symbol]['entry_price'] * self.margin_pct)
                    self.cash += (close_qty * price)  # Add sale proceeds
                    if self.positions[symbol]['quantity'] <= 0:
                        del self.positions[symbol]
                    logger.info(f"✅ SELL (close long): {close_qty} x {symbol} @ ₹{price:.2f}, P&L: ₹{pnl:.2f}")
                elif existing_qty < 0:  # Closing short
                    close_qty = min(quantity, -existing_qty)
                    pnl = (self.positions[symbol]['entry_price'] - price) * close_qty
                    self.positions[symbol]['quantity'] += close_qty
                    self.used_margin -= (close_qty * price * self.margin_pct)
                    self.cash += (close_qty * (self.positions[symbol]['entry_price'] - price + price))  # Adjust for short close
                    if self.positions[symbol]['quantity'] >= 0:
                        del self.positions[symbol]
                    logger.info(f"✅ BUY (close short): {close_qty} x {symbol} @ ₹{price:.2f}, P&L: ₹{pnl:.2f}")
            else:  # Opening short
                self.positions[symbol] = {
                    'action': 'SHORT',
                    'quantity': -quantity,
                    'entry_price': price,
                    'current_price': price,
                    'pnl': 0,
                    'pnl_percent': 0,
                    'stoploss': stoploss or 0,
                    'target': target or 0,
                    'entry_time': datetime.now().isoformat()
                }
                self.used_margin += margin_required
                self.cash += order_value  # Add proceeds from short sell
                logger.info(f"✅ SELL (open short): {quantity} x {symbol} @ ₹{price:.2f}")

        # Log trade if logger available
        if self.trade_logger:
            self.trade_logger.log_trade(
                timestamp=datetime.now().isoformat(),
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                order_value=order_value,
                pnl=self.positions.get(symbol, {}).get('pnl', 0) if symbol in self.positions else 0
            )

        self.trade_history.append({
            'order_id': order_id,
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'price': price,
            'stoploss': stoploss,
            'target': target
        })

        return order_id'''

    content = re.sub(execute_pattern, new_execute, content, flags=re.DOTALL | re.MULTILINE)

    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"KeyError fix patch applied to {file_path}. Backup created.")

# Create backup
paper_file = r'c:\Users\Dell\tradingbot_new\order_manager\paper_trader.py'
if os.path.exists(paper_file):
    backup_file = r'c:\Users\Dell\tradingbot_new\order_manager\paper_trader.py.backup_keyerror'
    with open(paper_file, 'rb') as src, open(backup_file, 'wb') as dst:
        dst.write(src.read())

# Apply patch
patch_paper_trader(paper_file)