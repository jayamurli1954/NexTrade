#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE THIS FILE AS: core/cumulative_trade_logger.py
# TEST: python core/cumulative_trade_logger.py
# ==============================================================================
"""
Cumulative Trade Logger

ONE Excel file for ALL trades (never resets)
- All trades since day 1
- Summary sheet with daily stats
- Position sheet with open positions
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from logzero import logger


class CumulativeTradeLogger:
    """
    Logs all trades to a single cumulative Excel file
    
    Features:
    - One file for all time
    - Three sheets: Trades, Daily Summary, Open Positions
    - Never resets
    - Grows forever
    """
    
    def __init__(self, excel_file: str = "logs/cumulative/all_trades.xlsx"):
        """
        Initialize cumulative trade logger
        
        Args:
            excel_file: Path to cumulative Excel file
        """
        self.excel_file = excel_file
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(excel_file), exist_ok=True)
        
        # Initialize or load existing file
        self._initialize_file()
        
        logger.info(f"Cumulative Trade Logger initialized: {excel_file}")
    
    def _initialize_file(self):
        """Initialize Excel file with sheets if it doesn't exist"""
        
        if os.path.exists(self.excel_file):
            logger.info(f"Using existing cumulative file: {self.excel_file}")
            return
        
        # Create new file with empty sheets
        with pd.ExcelWriter(self.excel_file, engine='openpyxl') as writer:
            # Trades sheet
            trades_df = pd.DataFrame(columns=[
                'Date', 'Time', 'Symbol', 'Action', 'Quantity', 
                'Entry Price', 'Exit Price', 'P&L', 'P&L %',
                'Balance After', 'Strategy', 'Exit Reason'
            ])
            trades_df.to_excel(writer, sheet_name='All Trades', index=False)
            
            # Daily summary sheet
            summary_df = pd.DataFrame(columns=[
                'Date', 'Starting Balance', 'Ending Balance', 
                'Trades', 'Winners', 'Losers', 'Daily P&L', 'Daily Return %'
            ])
            summary_df.to_excel(writer, sheet_name='Daily Summary', index=False)
            
            # Open positions sheet
            positions_df = pd.DataFrame(columns=[
                'Symbol', 'Action', 'Quantity', 'Entry Price', 'Entry Time',
                'Current Price', 'Unrealized P&L', 'P&L %', 'Target', 'Stop Loss'
            ])
            positions_df.to_excel(writer, sheet_name='Open Positions', index=False)
        
        logger.info(f"Created new cumulative file: {self.excel_file}")
    
    def log_trade(self, trade: Dict):
        """
        Log a completed trade
        
        Args:
            trade: Dictionary with trade details
        """
        
        try:
            # Read existing trades
            df = pd.read_excel(self.excel_file, sheet_name='All Trades')
            
            # Create new row
            new_row = {
                'Date': trade.get('date', datetime.now().strftime('%Y-%m-%d')),
                'Time': trade.get('time', datetime.now().strftime('%H:%M:%S')),
                'Symbol': trade.get('symbol', ''),
                'Action': trade.get('action', ''),  # BUY/SELL
                'Quantity': trade.get('quantity', 0),
                'Entry Price': trade.get('entry_price', 0),
                'Exit Price': trade.get('exit_price', 0),
                'P&L': trade.get('pnl', 0),
                'P&L %': trade.get('pnl_pct', 0),
                'Balance After': trade.get('balance_after', 0),
                'Strategy': trade.get('strategy', 'Golden Ratio'),
                'Exit Reason': trade.get('exit_reason', '')
            }
            
            # Append new row
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            # Write back to Excel
            with pd.ExcelWriter(self.excel_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                df.to_excel(writer, sheet_name='All Trades', index=False)
            
            logger.info(f"Logged trade: {trade.get('symbol')} P&L: Rs.{trade.get('pnl', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
    
    def update_daily_summary(self, date: str, starting_balance: float, 
                            ending_balance: float, trades: int, 
                            winners: int, losers: int):
        """
        Update daily summary sheet
        
        Args:
            date: Trading date
            starting_balance: Balance at start of day
            ending_balance: Balance at end of day
            trades: Number of trades
            winners: Number of winning trades
            losers: Number of losing trades
        """
        
        try:
            # Read existing summary
            try:
                df = pd.read_excel(self.excel_file, sheet_name='Daily Summary')
            except:
                df = pd.DataFrame(columns=[
                    'Date', 'Starting Balance', 'Ending Balance', 
                    'Trades', 'Winners', 'Losers', 'Daily P&L', 'Daily Return %'
                ])
            
            # Calculate P&L
            daily_pnl = ending_balance - starting_balance
            daily_return = (daily_pnl / starting_balance * 100) if starting_balance > 0 else 0
            
            # Check if date already exists
            if date in df['Date'].values:
                # Update existing row
                idx = df[df['Date'] == date].index[0]
                df.at[idx, 'Ending Balance'] = ending_balance
                df.at[idx, 'Trades'] = trades
                df.at[idx, 'Winners'] = winners
                df.at[idx, 'Losers'] = losers
                df.at[idx, 'Daily P&L'] = daily_pnl
                df.at[idx, 'Daily Return %'] = daily_return
            else:
                # Add new row
                new_row = {
                    'Date': date,
                    'Starting Balance': starting_balance,
                    'Ending Balance': ending_balance,
                    'Trades': trades,
                    'Winners': winners,
                    'Losers': losers,
                    'Daily P&L': daily_pnl,
                    'Daily Return %': daily_return
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            # Write back
            with pd.ExcelWriter(self.excel_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                df.to_excel(writer, sheet_name='Daily Summary', index=False)
            
            logger.info(f"Updated daily summary for {date}: P&L Rs.{daily_pnl:.2f}")
            
        except Exception as e:
            logger.error(f"Error updating daily summary: {e}")
    
    def update_open_positions(self, positions: List[Dict]):
        """
        Update open positions sheet
        
        Args:
            positions: List of open position dictionaries
        """
        
        try:
            # Create DataFrame from positions
            if not positions:
                df = pd.DataFrame(columns=[
                    'Symbol', 'Action', 'Quantity', 'Entry Price', 'Entry Time',
                    'Current Price', 'Unrealized P&L', 'P&L %', 'Target', 'Stop Loss'
                ])
            else:
                df = pd.DataFrame(positions)
            
            # Write to Excel
            with pd.ExcelWriter(self.excel_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                df.to_excel(writer, sheet_name='Open Positions', index=False)
            
            logger.debug(f"Updated open positions: {len(positions)} positions")
            
        except Exception as e:
            logger.error(f"Error updating positions: {e}")
    
    def get_total_trades(self) -> int:
        """Get total number of trades logged"""
        try:
            df = pd.read_excel(self.excel_file, sheet_name='All Trades')
            return len(df)
        except:
            return 0
    
    def get_last_trade(self) -> Optional[Dict]:
        """Get the last logged trade"""
        try:
            df = pd.read_excel(self.excel_file, sheet_name='All Trades')
            if len(df) > 0:
                return df.iloc[-1].to_dict()
            return None
        except:
            return None


# Singleton instance
_cumulative_logger_instance = None


def get_cumulative_logger(excel_file: str = "logs/cumulative/all_trades.xlsx") -> CumulativeTradeLogger:
    """Get or create the cumulative logger singleton"""
    
    global _cumulative_logger_instance
    
    if _cumulative_logger_instance is None:
        _cumulative_logger_instance = CumulativeTradeLogger(excel_file)
    
    return _cumulative_logger_instance


if __name__ == "__main__":
    # Demo usage
    print("Cumulative Trade Logger Demo")
    print()
    
    trade_logger = get_cumulative_logger()
    
    print(f"Total trades logged: {trade_logger.get_total_trades()}")
    print()
    
    # Simulate some trades
    print("Logging sample trades...")
    
    trades = [
        {
            'symbol': 'INFY',
            'action': 'BUY',
            'quantity': 10,
            'entry_price': 1500,
            'exit_price': 1550,
            'pnl': 500,
            'pnl_pct': 3.33,
            'balance_after': 100500,
            'exit_reason': 'Target Hit'
        },
        {
            'symbol': 'TCS',
            'action': 'SELL',
            'quantity': 5,
            'entry_price': 3100,
            'exit_price': 3040,
            'pnl': -300,
            'pnl_pct': -1.94,
            'balance_after': 100200,
            'exit_reason': 'Stop Loss'
        },
        {
            'symbol': 'WIPRO',
            'action': 'BUY',
            'quantity': 30,
            'entry_price': 250,
            'exit_price': 275,
            'pnl': 750,
            'pnl_pct': 10.0,
            'balance_after': 100950,
            'exit_reason': 'Target Hit'
        }
    ]
    
    for trade in trades:
        trade_logger.log_trade(trade)
    
    print()
    print(f"Total trades now: {trade_logger.get_total_trades()}")
    
    # Update daily summary
    today = datetime.now().strftime('%Y-%m-%d')
    trade_logger.update_daily_summary(
        date=today,
        starting_balance=100000,
        ending_balance=100950,
        trades=3,
        winners=2,
        losers=1
    )
    
    # Update open positions (empty for demo)
    trade_logger.update_open_positions([])
    
    print()
    print(f"Excel file created: {trade_logger.excel_file}")
    print("Open it to see all trades, daily summary, and positions!")
    print()