#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Direct Indentation Fix
File: direct_indent_fix.py

Fixes the specific indentation error at line 410-412
"""

import os
import shutil
from datetime import datetime


def main():
    print("="*70)
    print("DIRECT INDENTATION FIX")
    print("="*70)
    print()
    
    ui_file = r"ui\professional_trading_ui.py"
    
    print(f"📂 Reading: {ui_file}")
    
    with open(ui_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{ui_file}.backup_directfix_{timestamp}"
    shutil.copy2(ui_file, backup_path)
    print(f"✅ Backup: {backup_path}")
    print()
    
    # Find the problematic lines around 410-412
    print("🔍 Looking for the error around line 410...")
    print()
    
    # Show lines 408-415
    print("Current state:")
    for i in range(407, min(415, len(lines))):
        print(f"  Line {i+1}: {repr(lines[i])}")
    
    print()
    
    # The error says line 410 has a 'for' with no body
    # Line 412 has another 'for'
    # This means the for loop at 410 is empty
    
    # Check line 410 (index 409)
    if 'for' in lines[409]:
        print(f"🔍 Found 'for' statement at line 410:")
        print(f"   {lines[409].strip()}")
        
        # Check if line 411 (index 410) is properly indented
        if len(lines) > 410:
            line_410_indent = len(lines[409]) - len(lines[409].lstrip())
            line_411_indent = len(lines[410]) - len(lines[410].lstrip())
            
            print(f"   Line 410 indent: {line_410_indent}")
            print(f"   Line 411 indent: {line_411_indent}")
            
            # If line 411 doesn't have more indent, the for loop is empty
            if line_411_indent <= line_410_indent:
                print()
                print("❌ Problem: for loop at line 410 has no body!")
                print()
                print("Fix: Adding 'pass' statement to empty for loop")
                
                # Insert a pass statement
                indent = ' ' * (line_410_indent + 4)
                lines.insert(410, f"{indent}pass  # Empty loop - removed blocking code\n")
                
                print("✅ Fixed!")
    
    # Also check if there are any other empty for loops
    print()
    print("🔍 Checking for other empty loops...")
    
    fixed_count = 0
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        if line.strip().startswith('for ') and ':' in line:
            # This is a for loop
            loop_indent = len(line) - len(line.lstrip())
            next_line = lines[i + 1]
            next_indent = len(next_line) - len(next_line.lstrip())
            
            # Check if next line is not indented more (empty loop)
            if next_line.strip() and next_indent <= loop_indent:
                print(f"   Found empty for loop at line {i+1}")
                print(f"   {line.strip()}")
                
                # Insert pass
                indent = ' ' * (loop_indent + 4)
                lines.insert(i + 1, f"{indent}pass  # Empty loop\n")
                fixed_count += 1
                i += 1  # Skip the line we just inserted
        
        i += 1
    
    print(f"   Fixed {fixed_count} empty loops")
    
    # Write fixed file
    print()
    print("💾 Writing fixed file...")
    
    with open(ui_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("✅ File fixed!")
    
    print()
    print("="*70)
    print("✅ INDENTATION ERROR FIXED!")
    print("="*70)
    print()
    print("🧪 Test now:")
    print("   python main.py")
    print()
    input("Press ENTER to exit...")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())