#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Indentation Error
File: fix_indent_error.py
"""

import os
import shutil
from datetime import datetime


def main():
    print("="*70)
    print("FIXING INDENTATION ERROR")
    print("="*70)
    print()
    
    ui_file = r"ui\professional_trading_ui.py"
    
    # Find the most recent backup
    backups = [f for f in os.listdir('ui') if f.startswith('professional_trading_ui.py.backup_')]
    if not backups:
        print("❌ No backups found!")
        print()
        print("Please restore manually or share the error section")
        input("Press ENTER to exit...")
        return 1
    
    # Sort by timestamp (filename)
    backups.sort(reverse=True)
    
    # Find the backup from BEFORE watchlist fix
    backup_to_use = None
    for backup in backups:
        if 'watchlist' not in backup.lower():
            # This is from before the problematic watchlist patch
            backup_to_use = backup
            break
    
    if not backup_to_use:
        # Use the second most recent (the one before the last patch)
        if len(backups) >= 2:
            backup_to_use = backups[1]
        else:
            backup_to_use = backups[0]
    
    backup_path = os.path.join('ui', backup_to_use)
    
    print(f"📄 Restoring from: {backup_to_use}")
    print()
    print("This will restore to the state BEFORE the watchlist fix")
    print()
    choice = input("Continue? (yes/no): ").lower()
    
    if choice != 'yes':
        print("Cancelled")
        return 1
    
    # Restore the backup
    shutil.copy2(backup_path, ui_file)
    print()
    print("✅ File restored!")
    print()
    print("="*70)
    print("NEXT STEPS")
    print("="*70)
    print()
    print("Option 1: Try a simpler fix")
    print("  • I'll create a minimal patch that just comments out")
    print("    the blocking code instead of removing it")
    print()
    print("Option 2: Manual fix")
    print("  • Open ui\\professional_trading_ui.py")
    print("  • Find line 410-412")
    print("  • Fix the indentation manually")
    print()
    print("Which option? (1/2): ", end='')
    
    option = input().strip()
    
    if option == '1':
        return apply_simple_fix()
    else:
        print()
        print("Manual fix instructions:")
        print("  1. Open: ui\\professional_trading_ui.py")
        print("  2. Go to line 410")
        print("  3. Look for the 'for' loop")
        print("  4. Ensure the next line is indented properly")
        print()
        input("Press ENTER to exit...")
        return 0


def apply_simple_fix():
    """Apply a simpler, safer fix"""
    
    print()
    print("="*70)
    print("APPLYING SIMPLE FIX")
    print("="*70)
    print()
    
    ui_file = r"ui\professional_trading_ui.py"
    
    with open(ui_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{ui_file}.backup_simple_{timestamp}"
    shutil.copy2(ui_file, backup_path)
    print(f"✅ Backup: {backup_path}")
    print()
    
    # Find __init__ method
    init_line = None
    for i, line in enumerate(lines):
        if 'def __init__(self' in line:
            init_line = i
            break
    
    if init_line is None:
        print("❌ Could not find __init__")
        return 1
    
    # Look for the watchlist loading line
    watchlist_load_line = None
    for i in range(init_line, min(init_line + 100, len(lines))):
        if 'self.watchlist = self._load_watchlist()' in lines[i]:
            watchlist_load_line = i
            print(f"🔍 Found watchlist loading at line {i + 1}")
            break
    
    if watchlist_load_line:
        # Comment out this line and add a note
        indent = len(lines[watchlist_load_line]) - len(lines[watchlist_load_line].lstrip())
        indent_str = ' ' * indent
        
        # Replace with deferred version
        lines[watchlist_load_line] = (
            f"{indent_str}# Load symbols only (no prices - deferred to avoid startup delay)\n"
            f"{indent_str}self.watchlist = self._load_watchlist_symbols_only()\n"
        )
        
        print("✅ Modified watchlist loading")
        
        # Now add the _load_watchlist_symbols_only method
        # Find _load_watchlist method
        load_method_line = None
        for i, line in enumerate(lines):
            if 'def _load_watchlist(self' in line:
                load_method_line = i
                break
        
        if load_method_line:
            # Add new method after _load_watchlist
            # Find end of _load_watchlist
            end_line = load_method_line + 1
            method_indent = len(lines[load_method_line]) - len(lines[load_method_line].lstrip())
            
            while end_line < len(lines):
                curr_line = lines[end_line]
                if curr_line.strip() and curr_line.strip().startswith('def '):
                    curr_indent = len(curr_line) - len(curr_line.lstrip())
                    if curr_indent == method_indent:
                        break
                end_line += 1
            
            # Insert new method
            new_method = [
                "\n",
                f"{' ' * method_indent}def _load_watchlist_symbols_only(self):\n",
                f"{' ' * (method_indent + 4)}\"\"\"Load watchlist symbols without fetching prices\"\"\"\n",
                f"{' ' * (method_indent + 4)}try:\n",
                f"{' ' * (method_indent + 8)}if os.path.exists(self.watchlist_file):\n",
                f"{' ' * (method_indent + 12)}with open(self.watchlist_file, 'r') as f:\n",
                f"{' ' * (method_indent + 16)}import json\n",
                f"{' ' * (method_indent + 16)}data = json.load(f)\n",
                f"{' ' * (method_indent + 16)}return data.get('symbols', [])\n",
                f"{' ' * (method_indent + 4)}except Exception as e:\n",
                f"{' ' * (method_indent + 8)}logger.error(f'Error loading watchlist: {{e}}')\n",
                f"{' ' * (method_indent + 4)}return []\n",
                "\n",
            ]
            
            for line in reversed(new_method):
                lines.insert(end_line, line)
            
            print("✅ Added symbols-only loading method")
    
    # Write fixed file
    with open(ui_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print()
    print("✅ Simple fix applied!")
    print()
    print("="*70)
    print("TEST NOW")
    print("="*70)
    print()
    print("Run: python main.py")
    print()
    print("GUI should open in 2-3 seconds (no price fetching on startup)")
    print()
    input("Press ENTER to exit...")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())