#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Watchlist Tab Rate Limiting
File: fix_watchlist_ratelimit.py

Adds rate limiting to the Watchlist "Refresh LTP" button
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup of file before patching"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_watchlist_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def find_refresh_ltp_method(content):
    """Find the refresh LTP method in the UI file"""
    lines = content.split('\n')
    
    # Look for the refresh_ltp or similar method
    for i, line in enumerate(lines):
        if ('def refresh_ltp' in line or 
            'def _refresh_watchlist' in line or
            'def update_watchlist' in line):
            print(f"🔍 Found LTP refresh method at line {i + 1}: {line.strip()[:60]}")
            return i, lines
    
    return None, lines

def patch_watchlist_refresh(content):
    """Add rate limiting to watchlist LTP refresh"""
    
    lines = content.split('\n')
    
    # Find the method that refreshes watchlist LTPs
    method_idx, lines = find_refresh_ltp_method(content)
    
    if method_idx is None:
        print("❌ Could not find watchlist refresh method")
        print("⚠️  Searching for alternative patterns...")
        
        # Try to find where LTP is fetched in a loop for watchlist
        for i, line in enumerate(lines):
            if 'for' in line and 'watchlist' in line.lower():
                print(f"🔍 Found potential watchlist loop at line {i + 1}")
                method_idx = i
                break
    
    if method_idx is None:
        return None
    
    # Find the for loop that fetches LTPs
    for_loop_idx = None
    for i in range(method_idx, min(method_idx + 50, len(lines))):
        line = lines[i].strip()
        if line.startswith('for ') and ':' in line:
            print(f"🔍 Found for loop at line {i + 1}: {line[:60]}")
            for_loop_idx = i
            break
    
    if for_loop_idx is None:
        print("❌ Could not find for loop in refresh method")
        return None
    
    # Get indentation
    indent = len(lines[for_loop_idx]) - len(lines[for_loop_idx].lstrip())
    indent_str = ' ' * indent
    loop_body_indent = ' ' * (indent + 4)
    
    # Check if it already has enumerate
    for_line = lines[for_loop_idx].strip()
    if 'enumerate' not in for_line:
        # Extract loop variable
        if ' in ' in for_line:
            var_part = for_line.split('for ')[1].split(' in ')[0].strip()
            rest_part = for_line.split(' in ', 1)[1]
            
            # Modify to use enumerate
            lines[for_loop_idx] = f"{indent_str}for idx, {var_part} in enumerate({rest_part}"
            print(f"✅ Added enumerate to loop at line {for_loop_idx + 1}")
    
    # Find where to insert the delay - look for the end of the loop body
    # Find the next line with same or less indentation
    insert_idx = for_loop_idx + 1
    while insert_idx < len(lines):
        line = lines[insert_idx]
        if line.strip():
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent:
                break
        insert_idx += 1
    
    # Back up to insert before the end of loop
    insert_idx -= 1
    
    # Check if time import exists
    has_time_import = 'import time' in content
    
    # Add rate limiting code
    rate_limit_code = [
        "",
        f"{loop_body_indent}# ✅ Rate limiting: prevent API access denied",
        f"{loop_body_indent}time.sleep(0.5)  # 500ms delay = max 2 requests/sec",
    ]
    
    # Insert the code
    for line in reversed(rate_limit_code):
        lines.insert(insert_idx, line)
    
    print(f"✅ Added rate limiting at line {insert_idx + 1}")
    
    # Add import time if not present
    if not has_time_import:
        # Find where to insert import
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                lines.insert(i + 1, 'import time')
                print(f"✅ Added 'import time' at line {i + 2}")
                break
    
    return '\n'.join(lines)

def main():
    print("=" * 70)
    print("WATCHLIST TAB RATE LIMITING FIX")
    print("=" * 70)
    print()
    print("Issue: Clicking 'Refresh LTP' button causes rate limit errors")
    print("Fix: Add 0.5 second delay between each LTP request")
    print()
    
    # Try to find the UI file
    possible_paths = [
        r"ui\professional_trading_ui.py",
        r"ui\trading_ui.py",
        r"ui\main_ui.py",
        r"trading_ui.py",
    ]
    
    ui_file = None
    for path in possible_paths:
        if os.path.exists(path):
            ui_file = path
            break
    
    if ui_file is None:
        print("❌ ERROR: Could not find UI file")
        print()
        print("Searched for:")
        for path in possible_paths:
            print(f"  • {path}")
        input("\nPress ENTER to exit...")
        return 1
    
    print(f"📂 Target file: {ui_file}")
    print()
    
    # Read content
    try:
        with open(ui_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"❌ ERROR reading file: {e}")
        input("Press ENTER to exit...")
        return 1
    
    # Create backup
    print("📄 Creating backup...")
    try:
        backup_path = create_backup(ui_file)
    except Exception as e:
        print(f"❌ ERROR creating backup: {e}")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("🔧 Patching watchlist refresh method...")
    
    # Patch the method
    patched_content = patch_watchlist_refresh(original_content)
    
    if patched_content is None:
        print()
        print("❌ PATCH FAILED")
        print()
        print("Manual fix required:")
        print("1. Open the UI file")
        print("2. Find the method that refreshes watchlist LTPs")
        print("3. Add 'time.sleep(0.5)' at the end of the for loop")
        input("\nPress ENTER to exit...")
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
        print("📄 Restoring from backup...")
        try:
            shutil.copy2(backup_path, ui_file)
            print("✅ Backup restored")
        except:
            print("❌ Could not restore backup!")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("=" * 70)
    print("✅ PATCH COMPLETED!")
    print("=" * 70)
    print()
    print("📋 What was fixed:")
    print("   • Watchlist 'Refresh LTP' now has 0.5s delay per stock")
    print("   • Prevents 'Access denied because of exceeding access rate'")
    print("   • No more ₹1000.00 fallback prices")
    print()
    print("⏱️  Expected timing for Watchlist refresh:")
    print("   • 10 stocks: ~5 seconds")
    print("   • 25 stocks: ~12 seconds")
    print("   • 50 stocks: ~25 seconds")
    print("   • 93 stocks: ~46 seconds")
    print()
    print("🚀 Next steps:")
    print("   1. Restart the bot: Close and run 'python main.py'")
    print("   2. Go to Watchlist tab")
    print("   3. Click 'Refresh LTP'")
    print("   4. Verify prices update correctly (no ₹1000.00)")
    print()
    print("📄 To restore if needed:")
    print(f"   copy {os.path.basename(backup_path)} {ui_file}")
    print()
    
    input("Press ENTER to exit...")
    return 0

if __name__ == "__main__":
    import sys
    
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