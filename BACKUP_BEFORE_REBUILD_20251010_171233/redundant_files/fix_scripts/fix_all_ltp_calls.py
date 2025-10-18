#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix ALL LTP Request Paths - Complete Rate Limiting
File: fix_all_ltp_calls.py

Patches ALL three unpatched code paths:
1. Watchlist refresh (line 385)
2. Position monitoring (line 627)  
3. Paper trader orders (line 422)
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup of file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_allltp_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup: {backup_path}")
    return backup_path

def patch_watchlist_refresh(content):
    """Patch the watchlist refresh loop (line ~385)"""
    lines = content.split('\n')
    
    # Find the watchlist refresh loop
    for i, line in enumerate(lines):
        if 'for idx, sym in enumerate(self.watchlist):' in line:
            print(f"🔍 Found watchlist loop at line {i + 1}")
            
            # Get indentation
            indent = len(line) - len(line.lstrip())
            loop_body_indent = ' ' * (indent + 4)
            
            # Find the ltp = self.provider.get_ltp line
            for j in range(i, min(i + 10, len(lines))):
                if 'ltp = self.provider.get_ltp' in lines[j]:
                    print(f"   Found get_ltp call at line {j + 1}")
                    
                    # Find end of this iteration to add sleep
                    # Look for the next line with same or less indentation
                    insert_idx = j + 1
                    while insert_idx < len(lines):
                        l = lines[insert_idx]
                        if l.strip():
                            curr_indent = len(l) - len(l.lstrip())
                            if curr_indent <= indent:
                                break
                        insert_idx += 1
                    
                    # Insert rate limiting before the end
                    rate_limit_code = [
                        "",
                        f"{loop_body_indent}# ✅ Rate limiting for watchlist",
                        f"{loop_body_indent}if idx < len(self.watchlist) - 1:",
                        f"{loop_body_indent}    time.sleep(0.5)  # 500ms delay",
                    ]
                    
                    for line_to_insert in reversed(rate_limit_code):
                        lines.insert(insert_idx - 1, line_to_insert)
                    
                    print(f"   ✅ Added rate limiting after line {j + 1}")
                    break
            break
    
    return '\n'.join(lines)

def patch_position_monitoring(content):
    """Patch the position monitoring loop (line ~627)"""
    lines = content.split('\n')
    
    # Find position monitoring loop
    for i, line in enumerate(lines):
        if 'for pos in positions:' in line or 'for position in positions:' in line:
            # Check if this is the monitoring loop (has get_ltp call nearby)
            has_ltp_call = False
            for j in range(i, min(i + 15, len(lines))):
                if 'current_price = self.provider.get_ltp' in lines[j]:
                    has_ltp_call = True
                    print(f"🔍 Found position monitoring loop at line {i + 1}")
                    print(f"   with get_ltp at line {j + 1}")
                    break
            
            if has_ltp_call:
                # Change to enumerate if not already
                indent = len(line) - len(line.lstrip())
                loop_body_indent = ' ' * (indent + 4)
                
                if 'enumerate' not in line:
                    if 'for pos in positions:' in line:
                        lines[i] = ' ' * indent + 'for idx, pos in enumerate(positions):'
                        print(f"   ✅ Changed to enumerate at line {i + 1}")
                    elif 'for position in positions:' in line:
                        lines[i] = ' ' * indent + 'for idx, position in enumerate(positions):'
                        print(f"   ✅ Changed to enumerate at line {i + 1}")
                
                # Find end of loop to add sleep
                insert_idx = i + 1
                brace_level = 0
                for k in range(i + 1, len(lines)):
                    l = lines[k]
                    if l.strip():
                        curr_indent = len(l) - len(l.lstrip())
                        if curr_indent <= indent:
                            insert_idx = k
                            break
                
                # Add rate limiting
                rate_limit_code = [
                    "",
                    f"{loop_body_indent}# ✅ Rate limiting for position monitoring",
                    f"{loop_body_indent}if idx < len(positions) - 1:",
                    f"{loop_body_indent}    time.sleep(0.3)  # 300ms delay",
                ]
                
                for line_to_insert in reversed(rate_limit_code):
                    lines.insert(insert_idx - 1, line_to_insert)
                
                print(f"   ✅ Added rate limiting")
                break
    
    return '\n'.join(lines)

def patch_paper_trader(content):
    """Add rate limiting to paper trader get_ltp calls"""
    lines = content.split('\n')
    
    # The paper trader typically calls get_ltp individually, not in a loop
    # We need to add a simple time-based throttle at the get_ltp call itself
    
    for i, line in enumerate(lines):
        if 'price = self.data_provider.get_ltp(symbol' in line:
            print(f"🔍 Found paper trader get_ltp at line {i + 1}")
            
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent
            
            # Add throttle before the call
            throttle_code = [
                f"{indent_str}# ✅ Rate limiting throttle",
                f"{indent_str}time.sleep(0.1)  # Small delay for paper trading",
            ]
            
            for line_to_insert in reversed(throttle_code):
                lines.insert(i, line_to_insert)
            
            print(f"   ✅ Added throttle before get_ltp")
            break
    
    return '\n'.join(lines)

def ensure_time_import(content, filepath):
    """Make sure 'import time' exists"""
    if 'import time' in content:
        print(f"✅ '{os.path.basename(filepath)}' already has 'import time'")
        return content
    
    lines = content.split('\n')
    
    # Find where to insert
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i + 1
    
    lines.insert(insert_idx, 'import time')
    print(f"✅ Added 'import time' to '{os.path.basename(filepath)}'")
    
    return '\n'.join(lines)

def main():
    print("="*70)
    print("COMPREHENSIVE LTP RATE LIMITING FIX")
    print("="*70)
    print("\nThis will patch ALL three unpatched code paths:")
    print("  1. Watchlist refresh (ui/professional_trading_ui.py:385)")
    print("  2. Position monitoring (ui/professional_trading_ui.py:627)")
    print("  3. Paper trader orders (order_manager/paper_trader.py:422)")
    print()
    input("Press ENTER to continue...")
    print()
    
    # Patch UI file
    ui_file = r"ui\professional_trading_ui.py"
    print("="*70)
    print(f"PATCHING: {ui_file}")
    print("="*70)
    
    if not os.path.exists(ui_file):
        print(f"❌ File not found!")
        input("Press ENTER to exit...")
        return 1
    
    try:
        with open(ui_file, 'r', encoding='utf-8') as f:
            ui_content = f.read()
    except Exception as e:
        print(f"❌ Error reading: {e}")
        input("Press ENTER to exit...")
        return 1
    
    ui_backup = create_backup(ui_file)
    print()
    
    # Ensure import time
    ui_content = ensure_time_import(ui_content, ui_file)
    
    # Patch watchlist
    print("\n📝 Patching watchlist refresh...")
    ui_content = patch_watchlist_refresh(ui_content)
    
    # Patch position monitoring
    print("\n📝 Patching position monitoring...")
    ui_content = patch_position_monitoring(ui_content)
    
    # Write UI file
    try:
        with open(ui_file, 'w', encoding='utf-8') as f:
            f.write(ui_content)
        print(f"\n✅ {ui_file} patched successfully!")
    except Exception as e:
        print(f"\n❌ Error writing: {e}")
        shutil.copy2(ui_backup, ui_file)
        print("Backup restored")
        input("Press ENTER to exit...")
        return 1
    
    # Patch Paper Trader
    print("\n" + "="*70)
    paper_file = r"order_manager\paper_trader.py"
    print(f"PATCHING: {paper_file}")
    print("="*70)
    
    if not os.path.exists(paper_file):
        print(f"⚠️  File not found - skipping")
    else:
        try:
            with open(paper_file, 'r', encoding='utf-8') as f:
                paper_content = f.read()
        except Exception as e:
            print(f"❌ Error reading: {e}")
            input("Press ENTER to exit...")
            return 1
        
        paper_backup = create_backup(paper_file)
        print()
        
        # Ensure import time
        paper_content = ensure_time_import(paper_content, paper_file)
        
        # Patch paper trader
        print("\n📝 Patching paper trader get_ltp...")
        paper_content = patch_paper_trader(paper_content)
        
        # Write paper trader file
        try:
            with open(paper_file, 'w', encoding='utf-8') as f:
                f.write(paper_content)
            print(f"\n✅ {paper_file} patched successfully!")
        except Exception as e:
            print(f"\n❌ Error writing: {e}")
            shutil.copy2(paper_backup, paper_file)
            print("Backup restored")
            input("Press ENTER to exit...")
            return 1
    
    print("\n" + "="*70)
    print("✅ ALL PATCHES COMPLETED!")
    print("="*70)
    print("\n📋 What was fixed:")
    print("   • Watchlist 'Refresh LTP': 0.5s delay between stocks")
    print("   • Position monitoring: 0.3s delay between positions")
    print("   • Paper trader: 0.1s throttle on get_ltp calls")
    print()
    print("⏱️  Expected delays:")
    print("   • Watchlist (50 stocks): ~25 seconds")
    print("   • Position check (5 positions): ~1.5 seconds")
    print("   • Paper trade execution: +100ms per order")
    print()
    print("🚀 Next steps:")
    print("   1. Close the bot if running")
    print("   2. Run: python main.py")
    print("   3. Test 'Refresh LTP' button - should work without errors!")
    print()
    input("Press ENTER to exit...")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())