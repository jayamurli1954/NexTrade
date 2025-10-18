#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE THIS FILE AS: core/capital_tracker.py
# TEST: python core/capital_tracker.py
# ==============================================================================
"""
Capital Tracker - Persistent Balance Management

Tracks capital across sessions:
- Remembers yesterday's ending balance
- Today starts with yesterday's ending
- Cumulative P&L tracking
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from logzero import logger


class CapitalTracker:
    """
    Manages persistent capital state across trading sessions
    
    Features:
    - Persistent balance (survives bot restarts)
    - Daily P&L calculation
    - All-time P&L tracking
    - Win/loss statistics
    """
    
    def __init__(self, state_file: str = "logs/cumulative/capital_state.json", 
                 initial_capital: float = 100000.0):
        """
        Initialize capital tracker
        
        Args:
            state_file: Path to persistent state file
            initial_capital: Starting capital (only used on first run)
        """
        self.state_file = state_file
        self.initial_capital = initial_capital
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        
        # Load or initialize state
        self.state = self._load_state()
        
        logger.info(f"Capital Tracker initialized")
        logger.info(f"   Starting Capital: Rs.{self.initial_capital:,.2f}")
        logger.info(f"   Current Balance: Rs.{self.get_current_balance():,.2f}")
        logger.info(f"   All-Time P&L: Rs.{self.get_all_time_pnl():,.2f}")
    
    def _load_state(self) -> Dict:
        """Load capital state from file"""
        
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                logger.info(f"Loaded capital state from {self.state_file}")
                return state
                
            except Exception as e:
                logger.error(f"Error loading state: {e}")
                logger.info("Creating new state")
        
        # Create new state
        return self._create_initial_state()
    
    def _create_initial_state(self) -> Dict:
        """Create initial capital state"""
        
        state = {
            'initial_capital': self.initial_capital,
            'current_balance': self.initial_capital,
            'last_updated': datetime.now().isoformat(),
            'start_date': datetime.now().date().isoformat(),
            
            # Statistics
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0.0,
            'total_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            
            # Daily tracking
            'daily_sessions': {},
            
            # Version
            'version': '1.0'
        }
        
        self._save_state(state)
        logger.info("Created new capital state")
        
        return state
    
    def _save_state(self, state: Optional[Dict] = None):
        """Save capital state to file"""
        
        if state is None:
            state = self.state
        
        state['last_updated'] = datetime.now().isoformat()
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.debug("Capital state saved")
            
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def get_current_balance(self) -> float:
        """Get current available balance"""
        return self.state['current_balance']
    
    def get_initial_capital(self) -> float:
        """Get initial capital (starting amount)"""
        return self.state['initial_capital']
    
    def get_all_time_pnl(self) -> float:
        """Get all-time profit/loss"""
        return self.state['current_balance'] - self.state['initial_capital']
    
    def get_all_time_pnl_pct(self) -> float:
        """Get all-time P&L percentage"""
        pnl = self.get_all_time_pnl()
        return (pnl / self.state['initial_capital']) * 100
    
    def record_trade(self, pnl: float, symbol: str = ""):
        """
        Record a trade and update capital
        
        Args:
            pnl: Profit/loss from the trade
            symbol: Stock symbol (optional, for logging)
        """
        
        # Update balance
        self.state['current_balance'] += pnl
        self.state['total_trades'] += 1
        
        # Update statistics
        if pnl > 0:
            self.state['winning_trades'] += 1
            self.state['total_profit'] += pnl
            if pnl > self.state['largest_win']:
                self.state['largest_win'] = pnl
            
            logger.info(f"WIN: {symbol} +Rs.{pnl:,.2f} | Balance: Rs.{self.state['current_balance']:,.2f}")
        
        elif pnl < 0:
            self.state['losing_trades'] += 1
            self.state['total_loss'] += abs(pnl)
            if abs(pnl) > abs(self.state['largest_loss']):
                self.state['largest_loss'] = pnl
            
            logger.info(f"LOSS: {symbol} Rs.{pnl:,.2f} | Balance: Rs.{self.state['current_balance']:,.2f}")
        
        else:
            logger.info(f"BREAKEVEN: {symbol} | Balance: Rs.{self.state['current_balance']:,.2f}")
        
        # Update daily session
        today = datetime.now().date().isoformat()
        if today not in self.state['daily_sessions']:
            self.state['daily_sessions'][today] = {
                'starting_balance': self.state['current_balance'] - pnl,
                'ending_balance': self.state['current_balance'],
                'trades': 1,
                'pnl': pnl
            }
        else:
            session = self.state['daily_sessions'][today]
            session['ending_balance'] = self.state['current_balance']
            session['trades'] += 1
            session['pnl'] += pnl
        
        # Save state
        self._save_state()
    
    def get_today_pnl(self) -> float:
        """Get today's P&L"""
        today = datetime.now().date().isoformat()
        if today in self.state['daily_sessions']:
            return self.state['daily_sessions'][today]['pnl']
        return 0.0
    
    def get_today_starting_balance(self) -> float:
        """Get today's starting balance"""
        today = datetime.now().date().isoformat()
        if today in self.state['daily_sessions']:
            return self.state['daily_sessions'][today]['starting_balance']
        return self.state['current_balance']
    
    def get_win_rate(self) -> float:
        """Get win rate percentage"""
        if self.state['total_trades'] == 0:
            return 0.0
        return (self.state['winning_trades'] / self.state['total_trades']) * 100
    
    def get_profit_factor(self) -> float:
        """Get profit factor (total profit / total loss)"""
        if self.state['total_loss'] == 0:
            return float('inf') if self.state['total_profit'] > 0 else 0.0
        return self.state['total_profit'] / self.state['total_loss']
    
    def get_average_win(self) -> float:
        """Get average winning trade"""
        if self.state['winning_trades'] == 0:
            return 0.0
        return self.state['total_profit'] / self.state['winning_trades']
    
    def get_average_loss(self) -> float:
        """Get average losing trade"""
        if self.state['losing_trades'] == 0:
            return 0.0
        return self.state['total_loss'] / self.state['losing_trades']
    
    def get_statistics(self) -> Dict:
        """Get comprehensive statistics"""
        
        return {
            'initial_capital': self.state['initial_capital'],
            'current_balance': self.state['current_balance'],
            'all_time_pnl': self.get_all_time_pnl(),
            'all_time_pnl_pct': self.get_all_time_pnl_pct(),
            
            'today_pnl': self.get_today_pnl(),
            'today_starting': self.get_today_starting_balance(),
            
            'total_trades': self.state['total_trades'],
            'winning_trades': self.state['winning_trades'],
            'losing_trades': self.state['losing_trades'],
            'win_rate': self.get_win_rate(),
            
            'total_profit': self.state['total_profit'],
            'total_loss': self.state['total_loss'],
            'profit_factor': self.get_profit_factor(),
            
            'average_win': self.get_average_win(),
            'average_loss': self.get_average_loss(),
            
            'largest_win': self.state['largest_win'],
            'largest_loss': self.state['largest_loss'],
            
            'days_trading': len(self.state['daily_sessions']),
            'start_date': self.state['start_date'],
        }
    
    def print_statistics(self):
        """Print formatted statistics"""
        
        stats = self.get_statistics()
        
        print()
        print("="*70)
        print("TRADING PERFORMANCE - ALL TIME")
        print("="*70)
        print()
        print(f"  Starting Capital:        Rs.{stats['initial_capital']:>12,.2f}")
        print(f"  Current Balance:         Rs.{stats['current_balance']:>12,.2f}")
        print(f"  Total P&L:               Rs.{stats['all_time_pnl']:>12,.2f} ({stats['all_time_pnl_pct']:>6.2f}%)")
        print()
        print(f"  Today's P&L:             Rs.{stats['today_pnl']:>12,.2f}")
        print()
        print(f"  Total Trades:            {stats['total_trades']:>15,}")
        print(f"  Winning Trades:          {stats['winning_trades']:>15,} ({stats['win_rate']:>5.1f}%)")
        print(f"  Losing Trades:           {stats['losing_trades']:>15,}")
        print()
        print(f"  Best Trade:              Rs.{stats['largest_win']:>12,.2f}")
        print(f"  Worst Trade:             Rs.{stats['largest_loss']:>12,.2f}")
        print(f"  Average Win:             Rs.{stats['average_win']:>12,.2f}")
        print(f"  Average Loss:            Rs.{stats['average_loss']:>12,.2f}")
        print()
        print(f"  Profit Factor:           {stats['profit_factor']:>16.2f}")
        print(f"  Days Trading:            {stats['days_trading']:>15,}")
        print()
        print("="*70)
        print()
    
    def reset(self, new_initial_capital: Optional[float] = None):
        """
        Reset capital tracker to initial state
        
        Args:
            new_initial_capital: New initial capital (optional)
        """
        
        if new_initial_capital:
            self.initial_capital = new_initial_capital
        
        self.state = self._create_initial_state()
        logger.warning("Capital tracker has been RESET!")


# Singleton instance
_capital_tracker_instance = None


def get_capital_tracker(state_file: str = "logs/cumulative/capital_state.json",
                       initial_capital: float = 100000.0) -> CapitalTracker:
    """Get or create the capital tracker singleton"""
    
    global _capital_tracker_instance
    
    if _capital_tracker_instance is None:
        _capital_tracker_instance = CapitalTracker(state_file, initial_capital)
    
    return _capital_tracker_instance


if __name__ == "__main__":
    # Demo usage
    print("Capital Tracker Demo")
    print()
    
    tracker = get_capital_tracker()
    
    # Show initial stats
    tracker.print_statistics()
    
    # Simulate some trades
    print("Simulating trades...")
    print()
    
    tracker.record_trade(500, "INFY")
    tracker.record_trade(-300, "TCS")
    tracker.record_trade(750, "WIPRO")
    tracker.record_trade(-200, "TATASTEEL")
    
    # Show updated stats
    tracker.print_statistics()