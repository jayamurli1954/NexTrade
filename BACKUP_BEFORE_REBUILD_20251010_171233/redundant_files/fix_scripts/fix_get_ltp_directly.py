#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EMERGENCY FIX - Add Rate Limiting Inside get_ltp Function
File: fix_get_ltp_directly.py

This adds rate limiting at the SOURCE - inside the get_ltp method itself.
This guarantees rate limiting for ALL calls, no matter where they come from.
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_getltp_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup: {backup_path}")
    return backup_path

def patch_get_ltp_function(content):
    """Add rate limiting directly inside get_ltp method"""
    
    lines = content.split('\n')
    
    # Find the get_ltp function definition
    get_ltp_idx = None
    for i, line in enumerate(lines):
        if 'def get_ltp(self, symbol: str, exchange: str)' in line:
            get_ltp_idx = i
            print(f"🔍 Found get_ltp at line {i + 1}")
            break
    
    if get_ltp_idx is None:
        print("❌ Could not find get_ltp function")
        return None
    
    # Get the function's indentation
    func_indent = len(lines[get_ltp_idx]) - len(lines[get_ltp_idx].lstrip())
    body_indent = ' ' * (func_indent + 4)
    
    # Find the first line of the function body (after the def line)
    insert_idx = get_ltp_idx + 1
    
    # Skip docstring if present
    if '"""' in lines[insert_idx] or "'''" in lines[insert_idx]:
        # Find end of docstring
        in_docstring = True
        insert_idx += 1
        while insert_idx < len(lines) and in_docstring:
            if '"""' in lines[insert_idx] or "'''" in lines[insert_idx]:
                in_docstring = False
                insert_idx += 1
                break
            insert_idx += 1
    
    # Add rate limiting code at the very start of the function
    rate_limit_code = [
        f"{body_indent}# ✅ GLOBAL RATE LIMITING - Applied to ALL get_ltp calls",
        f"{body_indent}import time",
        f"{body_indent}import threading",
        f"{body_indent}",
        f"{body_indent}# Thread-safe rate limiting using a lock",
        f"{body_indent}if not hasattr(self, '_ltp_lock'):",
        f"{body_indent}    self._ltp_lock = threading.Lock()",
        f"{body_indent}    self._last_ltp_call = 0",
        f"{body_indent}",
        f"{body_indent}with self._ltp_lock:",
        f"{body_indent}    # Enforce minimum 0.5 second delay between ANY get_ltp calls",
        f"{body_indent}    elapsed = time.time() - self._last_ltp_call",
        f"{body_indent}    if elapsed < 0.5:",
        f"{body_indent}        time.sleep(0.5 - elapsed)",
        f"{body_indent}    self._last_ltp_call = time.time()",
        f"{body_indent}",
    ]
    
    # Insert the rate limiting code
    for line_to_insert in reversed(rate_limit_code):
        lines.insert(insert_idx, line_to_insert)
    
    print(f"✅ Added global rate limiting at line {insert_idx + 1}")
    print("   This applies to ALL get_ltp calls from anywhere in the code!")
    
    return '\n'.join(lines)

def main():
    print("="*70)
    print("EMERGENCY FIX - Global Rate Limiting in get_ltp")
    print("="*70)
    print()
    print("This fix adds rate limiting INSIDE the get_ltp function itself.")
    print("This means:")
    print("  • EVERY get_ltp call will be rate limited")
    print("  • Minimum 0.5 second delay between ANY two get_ltp calls")
    print("  • Thread-safe (uses locks)")
    print("  • Works even if called from multiple threads")
    print()
    print("Expected behavior:")
    print("  • Max 2 LTP requests per second (from anywhere)")
    print("  • No more duplicate rapid-fire requests")
    print("  • NO MORE 'Access denied' errors")
    print()
    input("Press ENTER to apply this fix...")
    print()
    
    provider_file = r"data_provider\angel_provider.py"
    
    if not os.path.exists(provider_file):
        print(f"❌ File not found: {provider_file}")
        input("Press ENTER to exit...")
        return 1
    
    print(f"📂 Target: {provider_file}")
    
    # Read content
    try:
        with open(provider_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading: {e}")
        input("Press ENTER to exit...")
        return 1
    
    # Create backup
    backup_path = create_backup(provider_file)
    print()
    
    # Patch get_ltp
    print("🔧 Patching get_ltp function...")
    patched_content = patch_get_ltp_function(content)
    
    if patched_content is None:
        print("❌ Patch failed")
        input("Press ENTER to exit...")
        return 1
    
    # Write patched file
    print()
    print("💾 Writing patched file...")
    
    try:
        with open(provider_file, 'w', encoding='utf-8') as f:
            f.write(patched_content)
        print("✅ File patched successfully!")
    except Exception as e:
        print(f"❌ Error writing: {e}")
        shutil.copy2(backup_path, provider_file)
        print("Backup restored")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("="*70)
    print("✅ EMERGENCY FIX APPLIED!")
    print("="*70)
    print()
    print("📋 What was done:")
    print("   • Added rate limiting INSIDE get_ltp function")
    print("   • Thread-safe lock prevents parallel calls")
    print("   • Enforces 0.5 second minimum delay between ANY calls")
    print("   • Works for: Analyzer, Watchlist, Position Monitor, Paper Trader")
    print()
    print("⏱️  Expected behavior:")
    print("   • Max 2 get_ltp calls per second (global)")
    print("   • All requests will be automatically throttled")
    print("   • Console logs will show slower but steady LTP fetches")
    print()
    print("🚀 CRITICAL NEXT STEPS:")
    print("   1. Close the bot COMPLETELY")
    print("   2. Wait 5 seconds")
    print("   3. Run: python main.py")
    print("   4. Test watchlist refresh")
    print("   5. Should see steady LTP updates, NO rate limit errors!")
    print()
    print("📊 What you'll see:")
    print("   12:35:01 | ✓ REAL LTP for ABB: ₹5185.00")
    print("   12:35:02 | ✓ REAL LTP for ADANIENT: ₹2547.60  (0.5s later)")
    print("   12:35:02 | ✓ REAL LTP for LODHA: ₹1152.10     (0.5s later)")
    print("   ...")
    print()
    input("Press ENTER to exit...")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())