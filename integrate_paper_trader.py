#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE AS: integrate_paper_trader.py
# RUN: python integrate_paper_trader.py
# ==============================================================================
"""
Integrate Paper Trader with Cumulative Systems

Patches paper_trader.py to use:
- Capital Tracker (persistent balance)
- Cumulative Logger (one Excel file forever)
"""

import os
import shutil
from datetime import datetime


def create_backup(filepath):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_cumulative_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"Backup: {backup_path}")
    return backup_path


def patch_paper_trader():
    """Patch paper_trader.py for cumulative tracking"""
    
    trader_file = "order_manager/paper_trader.py"
    
    if not os.path.exists(trader_file):
        print(f"ERROR: {trader_file} not found")
        return False
    
    print(f"\nPatching: {trader_file}")
    
    with open(trader_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Create backup
    backup = create_backup(trader_file)
    
    lines = content.split('\n')
    
    # 1. Add imports at top
    import_idx = None
    for i, line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            import_idx = i + 1
    
    if import_idx and 'capital_tracker' not in content:
        new_imports = [
            'from core.capital_tracker import get_capital_tracker',
            'from core.cumulative_trade_logger import get_cumulative_logger',
        ]
        for imp in reversed(new_imports):
            lines.insert(import_idx, imp)
        print("  Added cumulative system imports")
    
    # 2. Initialize in __init__
    for i, line in enumerate(lines):
        if 'def __init__(self' in line and 'PaperTrader' in ''.join(lines[max(0,i-10):i]):
            # Find end of __init__
            indent = len(line) - len(line.lstrip())
            body_indent = ' ' * (indent + 4)
            
            for j in range(i + 1, len(lines)):
                curr_line = lines[j]
                if curr_line.strip() and curr_line.strip().startswith('def '):
                    curr_indent = len(curr_line) - len(curr_line.lstrip())
                    if curr_indent == indent:
                        # Add initialization before next method
                        init_code = [
                            "",
                            f"{body_indent}# Cumulative tracking systems",
                            f"{body_indent}self.capital_tracker = get_capital_tracker(",
                            f"{body_indent}    initial_capital=starting_cash",
                            f"{body_indent})",
                            f"{body_indent}self.cumulative_logger = get_cumulative_logger()",
                            f"{body_indent}",
                            f"{body_indent}# Use cumulative balance instead of local cash",
                            f"{body_indent}self.cash = self.capital_tracker.get_current_balance()",
                        ]
                        
                        for code_line in reversed(init_code):
                            lines.insert(j, code_line)
                        
                        print("  Added cumulative system initialization")
                        break
            break
    
    # 3. Patch place_order to use cumulative logger
    for i, line in enumerate(lines):
        if 'def place_order(self' in line:
            print("  Found place_order method")
            # We'll patch the trade logging part later in a more targeted way
            break
    
    # 4. Patch exit_position to record in cumulative systems
    for i, line in enumerate(lines):
        if 'def exit_position(self' in line or 'def _exit_position(self' in line:
            # Find where P&L is calculated
            for j in range(i, min(i + 100, len(lines))):
                if 'pnl' in lines[j].lower() and '=' in lines[j]:
                    # Found P&L calculation
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    indent_str = ' ' * indent
                    
                    # Add cumulative tracking after P&L calculation
                    tracking_code = [
                        "",
                        f"{indent_str}# Record in cumulative systems",
                        f"{indent_str}try:",
                        f"{indent_str}    # Update capital tracker",
                        f"{indent_str}    self.capital_tracker.record_trade(pnl, symbol)",
                        f"{indent_str}    ",
                        f"{indent_str}    # Log in cumulative Excel",
                        f"{indent_str}    trade_data = {{",
                        f"{indent_str}        'symbol': symbol,",
                        f"{indent_str}        'action': position.get('action', ''),",
                        f"{indent_str}        'quantity': position.get('quantity', 0),",
                        f"{indent_str}        'entry_price': position.get('avg_price', 0),",
                        f"{indent_str}        'exit_price': exit_price,",
                        f"{indent_str}        'pnl': pnl,",
                        f"{indent_str}        'pnl_pct': (pnl / (position.get('avg_price', 1) * position.get('quantity', 1))) * 100,",
                        f"{indent_str}        'balance_after': self.capital_tracker.get_current_balance(),",
                        f"{indent_str}        'exit_reason': reason",
                        f"{indent_str}    }}",
                        f"{indent_str}    self.cumulative_logger.log_trade(trade_data)",
                        f"{indent_str}except Exception as e:",
                        f"{indent_str}    logger.error(f'Error recording cumulative trade: {{e}}')",
                    ]
                    
                    # Insert after P&L calculation
                    for code_line in reversed(tracking_code):
                        lines.insert(j + 1, code_line)
                    
                    print("  Added cumulative tracking in exit_position")
                    break
            break
    
    # Write patched file
    with open(trader_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"\nSuccess! {trader_file} patched")
    return True


def main():
    print("="*70)
    print("PAPER TRADER CUMULATIVE INTEGRATION")
    print("="*70)
    print()
    print("This will patch paper_trader.py to use:")
    print("  1. Capital Tracker - Persistent balance")
    print("  2. Cumulative Logger - All trades in one Excel file")
    print()
    print("Benefits:")
    print("  - Balance persists across bot restarts")
    print("  - All trades logged in logs/cumulative/all_trades.xlsx")
    print("  - Track strategy performance over time")
    print("  - See if you're making money!")
    print()
    
    # Check if cumulative systems exist
    if not os.path.exists("core/capital_tracker.py"):
        print("ERROR: core/capital_tracker.py not found!")
        print("Please create it first.")
        return
    
    if not os.path.exists("core/cumulative_trade_logger.py"):
        print("ERROR: core/cumulative_trade_logger.py not found!")
        print("Please create it first.")
        return
    
    print("Found cumulative systems")
    print()
    
    choice = input("Continue? (yes/no): ").lower().strip()
    if choice != 'yes':
        print("Cancelled")
        return
    
    print()
    
    if patch_paper_trader():
        print()
        print("="*70)
        print("INTEGRATION COMPLETE!")
        print("="*70)
        print()
        print("What was done:")
        print("  1. Added cumulative system imports")
        print("  2. Initialize capital tracker and logger")
        print("  3. Paper trader now uses persistent balance")
        print("  4. All trades logged to cumulative Excel")
        print()
        print("Next time you trade:")
        print("  - Balance will start from where you left off")
        print("  - Trades will be in logs/cumulative/all_trades.xlsx")
        print("  - You can track cumulative P&L over days/weeks/months")
        print()
        print("Example:")
        print("  Day 1: Start Rs.100,000 -> End Rs.100,500")
        print("  Day 2: Start Rs.100,500 -> End Rs.101,200")
        print("  Day 3: Start Rs.101,200 -> End Rs.100,800")
        print("  ...and so on!")
        print()
        print("To test: Restart bot and make a paper trade")
        print()


if __name__ == "__main__":
    main()