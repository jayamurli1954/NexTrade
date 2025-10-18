"""
COMPLETE SCRIPT - trade_logger.py
Enhanced Trade Logger with Excel Support
Save this as: c:/Users/Dell/tradingbot_new/trade_logger.py

NO PATCHING REQUIRED - This is the complete file
"""

import os
import json
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TradeLogger:
    """Comprehensive trade logging system with Excel export"""
    
    def __init__(self, log_dir='logs/trades'):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Get today's date for filename
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.excel_file = os.path.join(log_dir, f'trades_{self.today}.xlsx')
        self.json_file = os.path.join(log_dir, f'trades_{self.today}.json')
        
        # Load existing trades if any
        self.trades = self._load_trades()
        logger.info(f"TradeLogger initialized. File: {self.excel_file}")
        
    def _load_trades(self):
        """Load existing trades from JSON file"""
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, 'r') as f:
                    trades = json.load(f)
                logger.info(f"Loaded {len(trades)} existing trades from {self.json_file}")
                return trades
            except Exception as e:
                logger.error(f"Error loading trades: {e}")
                return []
        return []
    
    def _save_trades(self):
        """Save trades to both JSON and Excel"""
        try:
            # Save to JSON (for quick loading)
            with open(self.json_file, 'w') as f:
                json.dump(self.trades, f, indent=2)
            
            # Save to Excel (for user analysis)
            if self.trades:
                df = pd.DataFrame(self.trades)
                
                # Reorder columns for better readability
                column_order = [
                    'order_id', 'symbol', 'action', 'quantity',
                    'entry_price', 'exit_price', 'entry_time', 'exit_time',
                    'stoploss', 'target', 'pnl', 'pnl_percent',
                    'status', 'remarks'
                ]
                
                # Only include columns that exist
                existing_cols = [col for col in column_order if col in df.columns]
                df = df[existing_cols]
                
                # Format numeric columns
                numeric_cols = ['entry_price', 'exit_price', 'stoploss', 'target', 'pnl']
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
                
                if 'pnl_percent' in df.columns:
                    df['pnl_percent'] = df['pnl_percent'].apply(
                        lambda x: f"{x:.2f}%" if pd.notna(x) else ""
                    )
                
                # Write to Excel with formatting
                with pd.ExcelWriter(self.excel_file, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Trades', index=False)
                    
                    # Get workbook and worksheet
                    workbook = writer.book
                    worksheet = writer.sheets['Trades']
                    
                    # Auto-adjust column widths
                    for idx, col in enumerate(df.columns, 1):
                        max_length = max(
                            df[col].astype(str).apply(len).max(),
                            len(col)
                        )
                        column_letter = chr(64 + idx)
                        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
                    
                    # Add summary at the bottom
                    summary_row = len(df) + 3
                    worksheet[f'A{summary_row}'] = 'SUMMARY'
                    worksheet[f'A{summary_row}'].font = workbook.create_font(bold=True)
                    
                    total_trades = len(df)
                    completed_trades = len(df[df['status'] == 'CLOSED'])
                    open_trades = len(df[df['status'] == 'OPEN'])
                    total_pnl = df['pnl'].sum() if 'pnl' in df.columns else 0
                    
                    worksheet[f'A{summary_row + 1}'] = 'Total Trades:'
                    worksheet[f'B{summary_row + 1}'] = total_trades
                    worksheet[f'A{summary_row + 2}'] = 'Completed Trades:'
                    worksheet[f'B{summary_row + 2}'] = completed_trades
                    worksheet[f'A{summary_row + 3}'] = 'Open Trades:'
                    worksheet[f'B{summary_row + 3}'] = open_trades
                    worksheet[f'A{summary_row + 4}'] = 'Total P&L:'
                    worksheet[f'B{summary_row + 4}'] = f"₹{total_pnl:.2f}"
                    
                    # Color code P&L
                    if total_pnl >= 0:
                        worksheet[f'B{summary_row + 4}'].font = workbook.create_font(bold=True, color='00FF00')
                    else:
                        worksheet[f'B{summary_row + 4}'].font = workbook.create_font(bold=True, color='FF0000')
                
                logger.info(f"Saved {len(self.trades)} trades to Excel: {self.excel_file}")
            
        except Exception as e:
            logger.error(f"Error saving trades: {e}")
    
    def log_entry(self, order_id, symbol, action, quantity, price, 
                   stoploss=None, target=None, remarks=''):
        """Log trade entry"""
        trade = {
            'order_id': order_id,
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'entry_price': price,
            'exit_price': None,
            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'exit_time': None,
            'stoploss': stoploss,
            'target': target,
            'pnl': None,
            'pnl_percent': None,
            'status': 'OPEN',
            'remarks': remarks
        }
        
        self.trades.append(trade)
        self._save_trades()
        
        logger.info(f"✓ Trade Entry Logged: {action} {quantity} {symbol} @ ₹{price:.2f}")
        return order_id
    
    def log_exit(self, order_id, exit_price, remarks=''):
        """Log trade exit and calculate P&L"""
        for trade in self.trades:
            if trade['order_id'] == order_id and trade['status'] == 'OPEN':
                trade['exit_price'] = exit_price
                trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                trade['status'] = 'CLOSED'
                trade['remarks'] = f"{trade['remarks']} | {remarks}".strip(' |')
                
                # Calculate P&L
                entry_value = trade['entry_price'] * trade['quantity']
                exit_value = exit_price * trade['quantity']
                
                if trade['action'] == 'BUY':
                    trade['pnl'] = exit_value - entry_value
                else:  # SHORT
                    trade['pnl'] = entry_value - exit_value
                
                trade['pnl_percent'] = (trade['pnl'] / entry_value) * 100
                
                self._save_trades()
                
                logger.info(
                    f"✓ Trade Exit Logged: {trade['symbol']} @ ₹{exit_price:.2f} | "
                    f"P&L: ₹{trade['pnl']:.2f} ({trade['pnl_percent']:.2f}%)"
                )
                return True
        
        logger.warning(f"Trade {order_id} not found or already closed")
        return False
    
    def get_open_trades(self):
        """Get all open trades"""
        return [t for t in self.trades if t['status'] == 'OPEN']
    
    def get_closed_trades(self):
        """Get all closed trades"""
        return [t for t in self.trades if t['status'] == 'CLOSED']
    
    def get_trade_summary(self):
        """Get summary statistics"""
        total_trades = len(self.trades)
        open_trades = len(self.get_open_trades())
        closed_trades = len(self.get_closed_trades())
        
        total_pnl = sum(t.get('pnl', 0) for t in self.trades if t.get('pnl'))
        winning_trades = len([t for t in self.trades if t.get('pnl', 0) > 0])
        losing_trades = len([t for t in self.trades if t.get('pnl', 0) < 0])
        
        win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0
        
        return {
            'total_trades': total_trades,
            'open_trades': open_trades,
            'closed_trades': closed_trades,
            'total_pnl': total_pnl,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate
        }