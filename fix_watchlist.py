#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Automatic Patch Script - Fix Watchlist Scrolling Issue
File: fix_watchlist.py

Run this script to automatically patch professional_trading_ui.py
Fixes the watchlist scrolling/flickering issue
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup of file before patching"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_before_watchlist_fix_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def patch_watchlist_method(content):
    """Patch the _update_watchlist_display method"""
    
    # Old method signature to find
    old_method_start = "    def _update_watchlist_display(self):"
    
    # Find the old method
    if old_method_start not in content:
        print("❌ ERROR: Could not find _update_watchlist_display method!")
        print("   The file may have been modified.")
        return None
    
    # Split content into lines
    lines = content.split('\n')
    
    # Find start of method
    method_start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("def _update_watchlist_display(self):"):
            method_start_idx = i
            break
    
    if method_start_idx is None:
        print("❌ ERROR: Could not locate method start")
        return None
    
    # Find end of method (next method definition or class end)
    method_end_idx = None
    indent_level = len(lines[method_start_idx]) - len(lines[method_start_idx].lstrip())
    
    for i in range(method_start_idx + 1, len(lines)):
        line = lines[i]
        
        # Skip empty lines and comments
        if not line.strip() or line.strip().startswith('#'):
            continue
        
        # Check if we hit another method or end of indentation
        current_indent = len(line) - len(line.lstrip())
        
        if current_indent <= indent_level and line.strip():
            method_end_idx = i
            break
    
    if method_end_idx is None:
        method_end_idx = len(lines)
    
    print(f"📍 Found method at lines {method_start_idx + 1} to {method_end_idx}")
    
    # New improved method
    new_method = '''    def _update_watchlist_display(self):
        """Update watchlist display - FIXED: Only updates prices, doesn't rebuild list"""
        
        # Get current number of items
        current_count = self.watchlist_list.size()
        
        # If count changed, rebuild the list
        if current_count != len(self.watchlist):
            self.watchlist_list.delete(0, tk.END)
            for sym in self.watchlist:
                self.watchlist_list.insert(tk.END, f"{sym:12} | LTP: Fetching...")
        
        # Now just update the prices without rebuilding
        for idx, sym in enumerate(self.watchlist):
            try:
                ltp = self.provider.get_ltp(sym, 'NSE')
                display = f"{sym:12} | LTP: ₹{ltp:8.2f}" if ltp else f"{sym:12} | LTP: N/A"
                
                # Update only if text changed (prevents flickering)
                if idx < self.watchlist_list.size():
                    current_text = self.watchlist_list.get(idx)
                    if current_text != display:
                        self.watchlist_list.delete(idx)
                        self.watchlist_list.insert(idx, display)
            except Exception as e:
                # If error, just show N/A
                display = f"{sym:12} | LTP: N/A"
                if idx < self.watchlist_list.size():
                    self.watchlist_list.delete(idx)
                    self.watchlist_list.insert(idx, display)
'''
    
    # Replace the old method with new one
    new_lines = lines[:method_start_idx] + new_method.split('\n') + lines[method_end_idx:]
    
    return '\n'.join(new_lines)

def main():
    print("=" * 70)
    print("WATCHLIST SCROLLING FIX - Automatic Patch")
    print("=" * 70)
    print()
    
    # File to patch
    ui_file = r"ui\professional_trading_ui.py"
    
    if not os.path.exists(ui_file):
        print(f"❌ ERROR: File not found: {ui_file}")
        print()
        print("Make sure you're running this from:")
        print("   c:\\Users\\Dell\\tradingbot_new\\")
        print()
        input("Press ENTER to exit...")
        return 1
    
    print(f"📂 Target file: {ui_file}")
    print()
    
    # Read current content
    try:
        with open(ui_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"❌ ERROR reading file: {e}")
        input("Press ENTER to exit...")
        return 1
    
    print(f"📖 File size: {len(original_content)} characters")
    print()
    
    # Create backup
    print("🔄 Creating backup...")
    try:
        backup_path = create_backup(ui_file)
    except Exception as e:
        print(f"❌ ERROR creating backup: {e}")
        input("Press ENTER to exit...")
        return 1
    
    print()
    
    # Patch the content
    print("🔧 Patching _update_watchlist_display method...")
    print()
    
    patched_content = patch_watchlist_method(original_content)
    
    if patched_content is None:
        print()
        print("❌ PATCH FAILED - File not modified")
        print()
        input("Press ENTER to exit...")
        return 1
    
    # Write patched content
    print()
    print("💾 Writing patched file...")
    
    try:
        with open(ui_file, 'w', encoding='utf-8') as f:
            f.write(patched_content)
        print(f"✅ File patched successfully!")
    except Exception as e:
        print(f"❌ ERROR writing file: {e}")
        print()
        print("🔄 Restoring from backup...")
        try:
            shutil.copy2(backup_path, ui_file)
            print("✅ Backup restored")
        except:
            print("❌ Could not restore backup!")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("=" * 70)
    print("✅ PATCH COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print()
    print("📋 What was fixed:")
    print("   • Watchlist now only updates prices (not stock names)")
    print("   • No more scrolling/jumping when prices refresh")
    print("   • Stock names remain static")
    print()
    print("🔄 To restore original file:")
    print(f"   copy {os.path.basename(backup_path)} {ui_file}")
    print()
    print("🚀 Next step:")
    print("   python main.py")
    print()
    
    input("Press ENTER to exit...")
    return 0

if __name__ == "__main__":
    import sys
    
    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Patch cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress ENTER to exit...")
        sys.exit(1)