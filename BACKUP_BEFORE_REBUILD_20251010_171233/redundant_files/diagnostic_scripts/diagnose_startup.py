#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnose Startup Delay
File: diagnose_startup.py

Finds what's blocking the GUI from opening
"""

import os
import re


def analyze_main_py():
    """Check what main.py does before GUI starts"""
    
    if not os.path.exists('main.py'):
        print("❌ main.py not found")
        return
    
    print("="*70)
    print("ANALYZING main.py")
    print("="*70)
    print()
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Find where GUI is started
    gui_start_line = None
    for i, line in enumerate(lines):
        if 'ProfessionalTradingUI' in line and '(' in line:
            gui_start_line = i
            print(f"🔍 GUI created at line {i + 1}:")
            print(f"   {line.strip()}")
            break
    
    if gui_start_line:
        # Check what happens after GUI creation
        print()
        print("📋 Code after GUI creation:")
        for i in range(gui_start_line + 1, min(gui_start_line + 20, len(lines))):
            line = lines[i].strip()
            if line and not line.startswith('#'):
                print(f"   Line {i + 1}: {line}")
                
                # Flag suspicious calls
                if any(x in line.lower() for x in ['analyze', 'fetch', 'get_', 'load', 'update']):
                    print(f"      ⚠️  SUSPICIOUS - This might block!")


def analyze_ui_init():
    """Check what UI __init__ does"""
    
    ui_file = r"ui\professional_trading_ui.py"
    if not os.path.exists(ui_file):
        print("\n❌ UI file not found")
        return
    
    print()
    print("="*70)
    print("ANALYZING UI __init__")
    print("="*70)
    print()
    
    with open(ui_file, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Find __init__ method
    init_line = None
    for i, line in enumerate(lines):
        if 'def __init__(self' in line and 'ProfessionalTradingUI' in content[max(0, i-100):i]:
            init_line = i
            print(f"🔍 UI __init__ at line {i + 1}")
            break
    
    if init_line:
        # Find all method calls in __init__
        print()
        print("📋 Methods called in __init__:")
        
        in_init = True
        for i in range(init_line + 1, min(init_line + 200, len(lines))):
            line = lines[i]
            
            # Check if we've left __init__
            if line.strip().startswith('def ') and 'self' in line:
                break
            
            if 'self.' in line and '(' in line:
                method = line.strip()
                print(f"   Line {i + 1}: {method[:80]}")
                
                # Flag suspicious calls
                if any(x in method.lower() for x in ['analyze', 'fetch', 'refresh', 'load', 'update', 'get_ltp', 'subscribe']):
                    print(f"      🚨 BLOCKING CALL - This runs during startup!")


def analyze_provider_connect():
    """Check what happens during provider.connect()"""
    
    provider_file = r"data_provider\angel_provider.py"
    if not os.path.exists(provider_file):
        print("\n❌ Provider file not found")
        return
    
    print()
    print("="*70)
    print("ANALYZING provider.connect()")
    print("="*70)
    print()
    
    with open(provider_file, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Find connect method
    connect_line = None
    for i, line in enumerate(lines):
        if 'def connect(self' in line:
            connect_line = i
            print(f"🔍 connect() at line {i + 1}")
            break
    
    if connect_line:
        print()
        print("📋 What connect() does:")
        
        for i in range(connect_line, min(connect_line + 100, len(lines))):
            line = lines[i]
            
            # Look for blocking operations
            if any(x in line for x in ['sleep', 'get_', 'fetch', 'load', 'subscribe', 'for ', 'while ']):
                print(f"   Line {i + 1}: {line.strip()[:80]}")
                
                if 'sleep' in line:
                    print(f"      ⏳ DELAY detected")
                if any(x in line for x in ['for ', 'while ']):
                    print(f"      🔄 LOOP detected - might be slow")


def main():
    print("="*70)
    print("STARTUP DELAY DIAGNOSIS")
    print("="*70)
    print()
    print("Finding what's blocking the GUI from opening...")
    print()
    
    analyze_main_py()
    analyze_ui_init()
    analyze_provider_connect()
    
    print()
    print("="*70)
    print("DIAGNOSIS COMPLETE")
    print("="*70)
    print()
    print("🔍 Common culprits:")
    print("   1. Watchlist refresh during startup")
    print("   2. Auto-running analyzer")
    print("   3. WebSocket subscription loops")
    print("   4. Portfolio/position loading")
    print("   5. Pre-market analysis auto-start")
    print()
    print("📋 Next: Review the output above and identify the blocker")
    print()
    input("Press ENTER to exit...")


if __name__ == "__main__":
    main()