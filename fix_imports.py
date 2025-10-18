#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Fix: Update Import Paths in Tab Modules
Run this to fix the ModuleNotFoundError
"""

import os

def fix_imports():
    """Fix import paths in tab modules"""
    
    tabs_dir = "ui_new/tabs"
    
    # Files that need fixing
    files_to_fix = {
        "dashboard_tab.py": [
            ("from data_handler import TradeDataHandler", "from ui_new.data_handler import TradeDataHandler")
        ],
        "history_tab.py": [
            ("from data_handler import TradeDataHandler", "from ui_new.data_handler import TradeDataHandler")
        ]
    }
    
    print("🔧 Fixing import paths in tab modules...")
    print()
    
    for filename, replacements in files_to_fix.items():
        filepath = os.path.join(tabs_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"⚠️  {filename} not found - skipping")
            continue
        
        # Read file
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Apply fixes
        for old, new in replacements:
            if old in content:
                content = content.replace(old, new)
                print(f"✅ Fixed: {filename}")
                print(f"   Changed: {old}")
                print(f"   To:      {new}")
            else:
                print(f"ℹ️  {filename} - already fixed or no match found")
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    print()
    print("🎉 All imports fixed!")
    print()
    print("Now run: python test_new_ui.py")

if __name__ == "__main__":
    fix_imports()