#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE AS: ui_new/data_handler.py
# ==============================================================================
"""
Data Handler for Trading Bot UI
Reads trade data from Excel and provides cumulative statistics
"""

import pandas as pd
import os
from datetime import datetime

class TradeDataHandler:
    def __init__(self, excel_path="trades_log.xlsx"):
        self.excel_path = excel_path
        self.df = None
        self.load_data()
    
    def load_data(self):
        """Load trade data from Excel file"""
        try:
            if os.path.exists(self.excel_path):
                self.df = pd.read_excel(self.excel_path)
                print(f"✅ Loaded {len(self.df)} trades from {self.excel_path}")
            else:
                print(f"⚠️ Excel file not found: {self.excel_path}")
                self.df = pd.DataFrame()
        except Exception as e:
            print(f"❌ Error loading Excel: {e}")
            self.df = pd.DataFrame()
    
    def get_cumulative_stats(self):
        """Calculate cumulative statistics from all trades"""
        if self.df is None or self.df.empty:
            return {
                'capital': 100000.0,
                'total_trades': 0,
                'total_profit': 0.0,
                'win_rate': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0
            }
        
        # Calculate stats
        total_trades = len(self.df)
        
        # Assuming 'P&L' or 'Profit' column exists
        profit_col = None
        for col in ['P&L', 'Profit', 'PnL', 'profit', 'pnl']:
            if col in self.df.columns:
                profit_col = col
                break
        
        if profit_col:
            total_profit = self.df[profit_col].sum()
            winning_trades = len(self.df[self.df[profit_col] > 0])
            losing_trades = len(self.df[self.df[profit_col] < 0])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
            
            avg_profit = self.df[self.df[profit_col] > 0][profit_col].mean() if winning_trades > 0 else 0.0
            avg_loss = self.df[self.df[profit_col] < 0][profit_col].mean() if losing_trades > 0 else 0.0
            largest_win = self.df[profit_col].max() if not self.df[profit_col].empty else 0.0
            largest_loss = self.df[profit_col].min() if not self.df[profit_col].empty else 0.0
            
            # Calculate current capital (starting capital + total profit)
            starting_capital = 100000.0  # Default
            current_capital = starting_capital + total_profit
        else:
            total_profit = 0.0
            winning_trades = 0
            losing_trades = 0
            win_rate = 0.0
            avg_profit = 0.0
            avg_loss = 0.0
            largest_win = 0.0
            largest_loss = 0.0
            current_capital = 100000.0
        
        return {
            'capital': current_capital,
            'total_trades': total_trades,
            'total_profit': total_profit,
            'win_rate': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss
        }
    
    def get_recent_trades(self, n=10):
        """Get most recent n trades"""
        if self.df is None or self.df.empty:
            return []
        
        # Sort by date if date column exists
        date_col = None
        for col in ['Date', 'Timestamp', 'Time', 'date', 'timestamp']:
            if col in self.df.columns:
                date_col = col
                break
        
        if date_col:
            df_sorted = self.df.sort_values(by=date_col, ascending=False)
        else:
            df_sorted = self.df
        
        return df_sorted.head(n).to_dict('records')
    
    def get_active_positions(self):
        """Get currently active/open positions"""
        if self.df is None or self.df.empty:
            return []
        
        # Check for Status column
        status_col = None
        for col in ['Status', 'status', 'Position', 'position']:
            if col in self.df.columns:
                status_col = col
                break
        
        if status_col:
            active = self.df[self.df[status_col].str.upper().isin(['OPEN', 'ACTIVE'])]
            return active.to_dict('records')
        
        return []
    
    def get_daily_pnl(self):
        """Calculate daily P&L breakdown"""
        if self.df is None or self.df.empty:
            return {}
        
        # Find date and profit columns
        date_col = None
        for col in ['Date', 'Timestamp', 'Time', 'date', 'timestamp']:
            if col in self.df.columns:
                date_col = col
                break
        
        profit_col = None
        for col in ['P&L', 'Profit', 'PnL', 'profit', 'pnl']:
            if col in self.df.columns:
                profit_col = col
                break
        
        if date_col and profit_col:
            self.df[date_col] = pd.to_datetime(self.df[date_col])
            daily_pnl = self.df.groupby(self.df[date_col].dt.date)[profit_col].sum()
            return daily_pnl.to_dict()
        
        return {}
    
    def refresh(self):
        """Reload data from Excel"""
        self.load_data()
        return self.get_cumulative_stats()


if __name__ == "__main__":
    # Test the data handler
    handler = TradeDataHandler()
    stats = handler.get_cumulative_stats()
    
    print("\n📊 Cumulative Statistics:")
    print(f"💰 Current Capital: ₹{stats['capital']:,.2f}")
    print(f"🔄 Total Trades: {stats['total_trades']}")
    print(f"📈 Total Profit: ₹{stats['total_profit']:,.2f}")
    print(f"🎯 Win Rate: {stats['win_rate']:.1f}%")
    print(f"✅ Winning Trades: {stats['winning_trades']}")
    print(f"❌ Losing Trades: {stats['losing_trades']}")
    print(f"📊 Avg Profit: ₹{stats['avg_profit']:.2f}")
    print(f"📉 Avg Loss: ₹{stats['avg_loss']:.2f}")
    print(f"🏆 Largest Win: ₹{stats['largest_win']:.2f}")
    print(f"💔 Largest Loss: ₹{stats['largest_loss']:.2f}")
    
    print("\n📋 Recent Trades:")
    recent = handler.get_recent_trades(5)
    for i, trade in enumerate(recent, 1):
        print(f"{i}. {trade}")