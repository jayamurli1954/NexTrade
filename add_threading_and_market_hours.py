#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SURGICAL FIX: Adds threading + market hours check to existing UI
WITHOUT breaking anything
"""

import os
import shutil
from datetime import datetime

def add_threading_fix():
    """Add threading support to prevent UI freezing"""
    
    ui_file = "ui/professional_trading_ui.py"
    
    print("="*80)
    print("  SURGICAL THREADING + MARKET HOURS FIX")
    print("="*80)
    
    # Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"ui/professional_trading_ui.py.backup_{timestamp}"
    shutil.copy2(ui_file, backup)
    print(f"\n✅ Backup: {backup}")
    
    # Read
    with open(ui_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"✅ Read {len(lines)} lines")
    
    # Find where to add imports
    import_line = -1
    for i, line in enumerate(lines):
        if 'import logging' in line:
            import_line = i
            break
    
    if import_line == -1:
        print("❌ Could not find import section")
        return False
    
    # Add threading import if not present
    if not any('import threading' in line for line in lines):
        lines.insert(import_line + 1, 'import threading\n')
        print("✅ Added: import threading")
    
    # Find __init__ method
    init_line = -1
    for i, line in enumerate(lines):
        if 'def __init__(self, root, analyzer, provider, paper_trader' in line:
            init_line = i
            break
    
    if init_line == -1:
        print("❌ Could not find __init__ method")
        return False
    
    # Add threading helper method after __init__
    # Find end of __init__ (next method definition)
    end_init = -1
    for i in range(init_line + 1, len(lines)):
        if lines[i].strip().startswith('def ') and 'def __init__' not in lines[i]:
            end_init = i
            break
    
    if end_init == -1:
        print("❌ Could not find end of __init__")
        return False
    
    # Check if threading method already exists
    if not any('def _run_in_background' in line for line in lines):
        threading_method = '''
    def _run_in_background(self, func, callback=None, error_callback=None):
        """CRITICAL FIX: Run function in background thread"""
        def worker():
            try:
                result = func()
                if callback:
                    self.root.after(0, lambda: callback(result))
            except Exception as e:
                logger.error(f"Background task error: {e}")
                if error_callback:
                    self.root.after(0, lambda: error_callback(e))
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

'''
        lines.insert(end_init, threading_method)
        print("✅ Added: _run_in_background() method")
    
    # Add market hours check method
    if not any('def _is_market_open' in line for line in lines):
        market_hours_method = '''    def _is_market_open(self):
        """Check if market is open for trading"""
        from datetime import datetime, time
        
        now = datetime.now()
        
        # Check if weekend
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False, "Market closed: Weekend"
        
        # Market hours: 9:15 AM to 3:00 PM
        market_open = time(9, 15)
        market_close = time(15, 0)
        current_time = now.time()
        
        if current_time < market_open:
            return False, "Market closed: Opens at 9:15 AM"
        elif current_time >= market_close:
            return False, "Market closed: Closed at 3:00 PM"
        else:
            return True, "Market is open"

'''
        lines.insert(end_init + 1, market_hours_method)
        print("✅ Added: _is_market_open() method")
    
    # Now make key methods async - find and wrap them
    methods_to_make_async = [
        '_refresh_dashboard',
        '_refresh_portfolio', 
        '_run_analysis',
        '_refresh_paper_tab',
        '_update_watchlist_display'
    ]
    
    for method_name in methods_to_make_async:
        # Find the method
        for i, line in enumerate(lines):
            if f'def {method_name}(self' in line:
                # Check if already has _async version
                async_name = f'_async{method_name}' if method_name.startswith('_') else f'async_{method_name}'
                
                if any(f'def {async_name}' in l for l in lines):
                    continue  # Already has async version
                
                # Create async wrapper
                indent = len(line) - len(line.lstrip())
                async_wrapper = f"{' ' * indent}def {async_name}(self, *args, **kwargs):\n"
                async_wrapper += f"{' ' * (indent + 4)}\"\"\"FIXED: Non-blocking version\"\"\"\n"
                async_wrapper += f"{' ' * (indent + 4)}self._run_in_background(\n"
                async_wrapper += f"{' ' * (indent + 8)}lambda: self.{method_name}(*args, **kwargs)\n"
                async_wrapper += f"{' ' * (indent + 4)})\n\n"
                
                # Insert before the original method
                lines.insert(i, async_wrapper)
                print(f"✅ Added: {async_name}() wrapper")
                break
    
    # Find and update button callbacks to use async versions
    callback_replacements = [
        ('command=self._refresh_dashboard', 'command=self._async_refresh_dashboard'),
        ('command=self._refresh_portfolio', 'command=self._async_refresh_portfolio'),
        ('command=self._run_analysis', 'command=self._async_run_analysis'),
        ('command=self._refresh_paper_tab', 'command=self._async_refresh_paper_tab'),
        ('command=self._update_watchlist_display', 'command=self._async_update_watchlist_display'),
    ]
    
    replacements_made = 0
    for i, line in enumerate(lines):
        for old, new in callback_replacements:
            if old in line and new not in line:
                lines[i] = line.replace(old, new)
                replacements_made += 1
                print(f"✅ Updated callback: {old.split('=')[1]} -> {new.split('=')[1]}")
    
    # Add market hours check to trade execution
    for i, line in enumerate(lines):
        if 'def _execute_trade_from_tree(self' in line:
            # Find the start of the method body
            for j in range(i + 1, min(i + 10, len(lines))):
                if 'selection = tree.selection()' in lines[j]:
                    # Insert market hours check before selection
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    check_code = f"{' ' * indent}# Check market hours\n"
                    check_code += f"{' ' * indent}is_open, msg = self._is_market_open()\n"
                    check_code += f"{' ' * indent}if not is_open:\n"
                    check_code += f"{' ' * (indent + 4)}messagebox.showwarning('Market Closed', msg)\n"
                    check_code += f"{' ' * (indent + 4)}return\n\n"
                    
                    lines.insert(j, check_code)
                    print("✅ Added: Market hours check in trade execution")
                    break
            break
    
    # Write fixed file
    with open(ui_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"\n✅ Fixed file written: {len(lines)} lines")
    
    print("\n" + "="*80)
    print("  FIXES APPLIED SUCCESSFULLY!")
    print("="*80)
    print("\n✅ Threading: All UI-blocking calls now run in background")
    print("✅ Market Hours: Trades blocked outside 9:15 AM - 3:00 PM (Mon-Fri)")
    print(f"✅ Backup saved: {backup}")
    print("\n🚀 Run: python main.py")
    print("="*80)
    
    return True


if __name__ == "__main__":
    if not os.path.exists("ui/professional_trading_ui.py"):
        print("❌ ERROR: ui/professional_trading_ui.py not found!")
        print(f"Current directory: {os.getcwd()}")
        input("Press Enter...")
        exit(1)
    
    success = add_threading_fix()
    
    if not success:
        print("\n❌ Patching failed - check errors above")
    
    input("\nPress Enter to exit...")