#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Syntax Error in professional_trading_ui.py
File: fix_syntax_error.py

Fixes the missing closing parenthesis in enumerate line
"""

import os
import shutil
from datetime import datetime

def main():
    print("=" * 70)
    print("SYNTAX ERROR FIX")
    print("=" * 70)
    print()
    
    ui_file = r"ui\professional_trading_ui.py"
    
    if not os.path.exists(ui_file):
        print(f"❌ ERROR: File not found: {ui_file}")
        input("Press ENTER to exit...")
        return 1
    
    print(f"📂 Reading: {ui_file}")
    
    # Read content
    try:
        with open(ui_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ ERROR reading file: {e}")
        input("Press ENTER to exit...")
        return 1
    
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{ui_file}.backup_syntax_{timestamp}"
    shutil.copy2(ui_file, backup_path)
    print(f"✅ Backup: {backup_path}")
    print()
    
    # Fix the syntax error
    lines = content.split('\n')
    fixed = False
    
    for i, line in enumerate(lines):
        # Look for the broken enumerate line
        if 'for idx, sym in enumerate(self.watchlist:' in line:
            # Fix: close the enumerate parenthesis
            lines[i] = line.replace(
                'for idx, sym in enumerate(self.watchlist:',
                'for idx, sym in enumerate(self.watchlist):'
            )
            print(f"✅ Fixed line {i + 1}:")
            print(f"   OLD: {line.strip()}")
            print(f"   NEW: {lines[i].strip()}")
            fixed = True
            break
    
    if not fixed:
        print("❌ Could not find the syntax error line")
        print()
        print("The error is at line 376:")
        print("   for idx, sym in enumerate(self.watchlist:")
        print()
        print("Should be:")
        print("   for idx, sym in enumerate(self.watchlist):")
        print("                                             ^")
        print("                                    Added closing )")
        print()
        input("Press ENTER to exit...")
        return 1
    
    # Write fixed content
    print()
    print("💾 Writing fixed file...")
    
    try:
        with open(ui_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print("✅ File fixed successfully!")
    except Exception as e:
        print(f"❌ ERROR writing file: {e}")
        print("📄 Restoring backup...")
        shutil.copy2(backup_path, ui_file)
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("=" * 70)
    print("✅ SYNTAX ERROR FIXED!")
    print("=" * 70)
    print()
    print("🚀 Now try again:")
    print("   python main.py")
    print()
    
    input("Press ENTER to exit...")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())