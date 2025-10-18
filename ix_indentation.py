#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Indentation Error in UI File
File: fix_indentation.py
"""

import os
import shutil
from datetime import datetime

def main():
    print("="*70)
    print("FIX INDENTATION ERROR")
    print("="*70)
    print()
    
    ui_file = r"ui\professional_trading_ui.py"
    
    if not os.path.exists(ui_file):
        print(f"❌ File not found: {ui_file}")
        input("Press ENTER to exit...")
        return 1
    
    print(f"📂 Reading: {ui_file}")
    
    try:
        with open(ui_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"❌ Error reading: {e}")
        input("Press ENTER to exit...")
        return 1
    
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{ui_file}.backup_indent_{timestamp}"
    with open(ui_file, 'r', encoding='utf-8') as f:
        backup_content = f.read()
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(backup_content)
    print(f"✅ Backup: {backup_path}")
    print()
    
    # Find and fix the indentation issue around line 397
    print("🔍 Looking for indentation errors around line 397...")
    
    fixed = False
    for i in range(390, min(405, len(lines))):
        line = lines[i]
        
        # Check if this is the problematic line
        if 'self.watchlist_list.insert' in line:
            print(f"📍 Found at line {i + 1}: {line.rstrip()}")
            
            # Check the previous line's indentation
            prev_line = lines[i - 1] if i > 0 else ""
            
            # Get the indentation of surrounding code
            # Look backwards for a line with code to match indentation
            ref_indent = 0
            for j in range(i - 1, max(0, i - 10), -1):
                if lines[j].strip() and not lines[j].strip().startswith('#'):
                    ref_indent = len(lines[j]) - len(lines[j].lstrip())
                    print(f"   Reference line {j + 1} has indent: {ref_indent}")
                    break
            
            # Fix the indentation
            current_indent = len(line) - len(line.lstrip())
            print(f"   Current indent: {current_indent}, Should be: {ref_indent}")
            
            if current_indent != ref_indent:
                # Re-indent the line
                fixed_line = ' ' * ref_indent + line.lstrip()
                lines[i] = fixed_line
                print(f"   ✅ Fixed indentation")
                fixed = True
                break
    
    if not fixed:
        print("⚠️  Could not automatically fix. Trying broader fix...")
        
        # Look for the watchlist refresh method and fix all indentation
        in_method = False
        method_indent = 0
        
        for i, line in enumerate(lines):
            if 'def refresh_watchlist' in line or 'def _refresh_watchlist' in line:
                in_method = True
                method_indent = len(line) - len(line.lstrip())
                print(f"📍 Found method at line {i + 1}, base indent: {method_indent}")
                continue
            
            if in_method and line.strip():
                current_indent = len(line) - len(line.lstrip())
                
                # If we've left the method (indent back to class level or less)
                if current_indent <= method_indent and line.strip().startswith('def '):
                    in_method = False
                    continue
                
                # Fix any rate limiting comments/code that might be misaligned
                if i >= 390 and i <= 405:
                    if 'Rate limiting' in line or 'time.sleep' in line:
                        # This should be inside the loop body
                        expected_indent = method_indent + 12  # function + for loop + if/try
                        if current_indent != expected_indent:
                            lines[i] = ' ' * expected_indent + line.lstrip()
                            print(f"   ✅ Fixed line {i + 1}")
                            fixed = True
    
    if not fixed:
        print("\n❌ Could not automatically fix the indentation.")
        print("\n🔧 Manual fix required:")
        print(f"1. Open: {ui_file}")
        print("2. Go to line 397")
        print("3. Fix the indentation to match surrounding code")
        print("4. The line should be inside the for loop")
        print()
        input("Press ENTER to exit...")
        return 1
    
    # Write the fixed content
    print()
    print("💾 Writing fixed file...")
    
    try:
        with open(ui_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("✅ File fixed!")
    except Exception as e:
        print(f"❌ Error writing: {e}")
        # Restore backup
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_content = f.read()
        with open(ui_file, 'w', encoding='utf-8') as f:
            f.write(backup_content)
        print("Backup restored")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("="*70)
    print("✅ INDENTATION FIXED!")
    print("="*70)
    print()
    print("🚀 Now try: python main.py")
    print()
    input("Press ENTER to exit...")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())