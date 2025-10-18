#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostic Script - Check if patches were applied
File: diagnose_patches.py
"""

import os

def check_file(filepath, checks):
    """Check if a file has the expected patches"""
    print(f"\n{'='*70}")
    print(f"Checking: {filepath}")
    print('='*70)
    
    if not os.path.exists(filepath):
        print(f"❌ File not found!")
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False
    
    all_passed = True
    for check_name, check_text in checks:
        if check_text in content:
            print(f"✅ {check_name}")
        else:
            print(f"❌ MISSING: {check_name}")
            all_passed = False
    
    return all_passed

def main():
    print("="*70)
    print("PATCH DIAGNOSTIC TOOL")
    print("="*70)
    print("\nThis will check if yesterday's patches were actually applied.")
    print()
    
    # Check analyzer file
    analyzer_checks = [
        ("Import time statement", "import time"),
        ("Rate limiting setup", "# ✅ FIXED: Added rate limiting"),
        ("Sleep delay", "time.sleep(0.25)"),
        ("Enumerate loop", "for idx, sym in enumerate(symbols)"),
        ("Progress tracking", "Progress:"),
    ]
    
    analyzer_ok = check_file(r"analyzer\enhanced_analyzer.py", analyzer_checks)
    
    # Check UI file for premarket
    ui_checks = [
        ("Top 10 signals limit", "top_signals = sorted_signals[:10]"),
        ("Sorted signals", "sorted_signals = sorted"),
    ]
    
    ui_ok = check_file(r"ui\professional_trading_ui.py", ui_checks)
    
    print("\n" + "="*70)
    print("DIAGNOSIS SUMMARY")
    print("="*70)
    
    if analyzer_ok and ui_ok:
        print("✅ All patches appear to be applied correctly")
        print("\n⚠️  BUT you're still getting rate limit errors!")
        print("\nPossible causes:")
        print("1. The analyzer is being called multiple times simultaneously")
        print("2. There's another code path making LTP requests")
        print("3. The watchlist refresh is the culprit")
        print("4. Real-time monitoring thread is making requests")
        print("\nLet's check what's actually calling get_ltp...")
        
    elif not analyzer_ok:
        print("❌ Analyzer patches are MISSING or INCOMPLETE")
        print("\n🔧 Solution: Re-run the patch scripts:")
        print("   python fix_analyzer_complete.py")
        print("   OR")
        print("   python fix_analyzer_flexible.py")
        
    elif not ui_ok:
        print("⚠️  Analyzer is patched but UI patches missing")
        print("\n🔧 Solution: Re-run:")
        print("   python fix_premarket_top10.py")
    
    print("\n" + "="*70)
    print("NEXT STEP: Find who's calling get_ltp")
    print("="*70)
    print("\nSearching for LTP request code paths...")
    
    # Search for get_ltp calls
    files_to_search = [
        r"analyzer\enhanced_analyzer.py",
        r"ui\professional_trading_ui.py", 
        r"data_provider\angel_provider.py",
        r"order_manager\paper_trader.py",
    ]
    
    ltp_callers = []
    
    for filepath in files_to_search:
        if not os.path.exists(filepath):
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if 'get_ltp' in line.lower() and not line.strip().startswith('#'):
                    ltp_callers.append({
                        'file': filepath,
                        'line': i + 1,
                        'code': line.strip()
                    })
        except:
            pass
    
    print(f"\nFound {len(ltp_callers)} places calling get_ltp:\n")
    
    for caller in ltp_callers:
        print(f"📍 {caller['file']}:{caller['line']}")
        print(f"   {caller['code'][:80]}")
        print()
    
    print("="*70)
    print("\n⚡ CRITICAL FINDING:")
    print("\nThe rate limit errors are happening VERY FAST (11:54:17-11:54:29)")
    print("This suggests rapid-fire requests, likely from:")
    print("  1. Watchlist refresh button")
    print("  2. Real-time monitoring thread")
    print("  3. Multiple simultaneous analyzer calls")
    print()
    input("Press ENTER to exit...")

if __name__ == "__main__":
    main()