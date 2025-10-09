#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Complete Analyzer Fix - Rate Limiting + Progress + Top 10
File: fix_analyzer_complete.py

Fixes:
1. ✅ Adds rate limiting (0.25s delay between stocks = 4 per second max)
2. ✅ Shows progress every 10 stocks
3. ✅ Ensures only top 10 signals returned
4. ✅ Prevents "Access denied because of exceeding access rate" errors
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup of file before patching"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_complete_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def patch_analyze_watchlist(content):
    """Add rate limiting and progress to analyze_watchlist"""
    
    lines = content.split('\n')
    
    # Find analyze_watchlist method
    method_start = None
    for i, line in enumerate(lines):
        if 'def analyze_watchlist(self, symbols, exchange="NSE"):' in line:
            method_start = i
            break
    
    if method_start is None:
        print("❌ Could not find analyze_watchlist method")
        return None
    
    print(f"📍 Found analyze_watchlist at line {method_start + 1}")
    
    # Find the for loop
    for_loop_idx = None
    for i in range(method_start, min(method_start + 20, len(lines))):
        if 'for sym in symbols:' in lines[i]:
            for_loop_idx = i
            break
    
    if for_loop_idx is None:
        print("❌ Could not find for loop in analyze_watchlist")
        return None
    
    print(f"📍 Found for loop at line {for_loop_idx + 1}")
    
    # Get indentation
    indent = len(lines[for_loop_idx]) - len(lines[for_loop_idx].lstrip())
    indent_str = ' ' * indent
    loop_body_indent = ' ' * (indent + 4)
    
    # Replace the for loop with enhanced version
    new_loop = f"""{indent_str}# ✅ FIXED: Added rate limiting and progress tracking
{indent_str}import time
{indent_str}total_symbols = len(symbols)
{indent_str}print(f"📊 Analyzing {{total_symbols}} stocks with rate limiting...")
{indent_str}
{indent_str}for idx, sym in enumerate(symbols):
{loop_body_indent}# Show progress every 10 stocks
{loop_body_indent}if idx > 0 and idx % 10 == 0:
{loop_body_indent}    print(f"  ⏳ Progress: {{idx}}/{{total_symbols}} stocks analyzed... ({{len(signals)}} signals so far)")
{loop_body_indent}
{loop_body_indent}try:
{loop_body_indent}    signal = self.analyze_symbol(sym, exchange)
{loop_body_indent}    if signal:
{loop_body_indent}        signals.append(signal)
{loop_body_indent}except Exception as e:
{loop_body_indent}    logger.error(f"Error analyzing {{sym}}: {{e}}")
{loop_body_indent}
{loop_body_indent}# ✅ CRITICAL: Add delay to prevent rate limiting
{loop_body_indent}# Wait 250ms between stocks = max 4 requests per second
{loop_body_indent}if idx < total_symbols - 1:  # Don't wait after last stock
{loop_body_indent}    time.sleep(0.25)"""
    
    # Find the end of the existing try-except block inside the loop
    loop_end_idx = for_loop_idx
    brace_count = 0
    in_loop = False
    
    for i in range(for_loop_idx, min(for_loop_idx + 15, len(lines))):
        line = lines[i]
        
        if 'for sym in symbols:' in line:
            in_loop = True
            continue
        
        if in_loop:
            # Look for the next line with same or less indentation as the for loop
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= indent:
                loop_end_idx = i
                break
            
            # Or look for the signals.sort line
            if 'signals.sort' in line:
                loop_end_idx = i
                break
    
    print(f"📍 Loop ends at line {loop_end_idx + 1}")
    
    # Replace the loop section
    lines[for_loop_idx:loop_end_idx] = new_loop.split('\n')
    
    # Find the signals.sort line and ensure we return top 10
    for i in range(method_start, len(lines)):
        if 'signals.sort(key=lambda x:' in lines[i]:
            # Check next few lines for return statement
            for j in range(i, min(i + 10, len(lines))):
                if 'return signals' in lines[j] and '[:' not in lines[j]:
                    # Modify to return top 10 only
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    indent_str = ' ' * current_indent
                    
                    lines[j] = f"{indent_str}# ✅ Return top 10 highest confidence signals only"
                    lines.insert(j + 1, f"{indent_str}top_signals = signals[:10]")
                    lines.insert(j + 2, f"{indent_str}print(f\"✅ Analysis complete: Returning {{len(top_signals)}} of {{len(signals)}} signals (top 10)\")")
                    lines.insert(j + 3, f"{indent_str}return top_signals")
                    
                    # Remove old return
                    if j + 4 < len(lines) and 'return signals' in lines[j + 4]:
                        del lines[j + 4]
                    
                    print(f"✅ Modified return statement at line {j + 1}")
                    break
            break
    
    return '\n'.join(lines)

def patch_premarket_analysis(content):
    """Ensure premarket returns top 10 (already has [:10] but verify)"""
    
    lines = content.split('\n')
    
    # Find run_premarket_analysis method
    method_start = None
    for i, line in enumerate(lines):
        if 'def run_premarket_analysis(self, symbols, exchange="NSE"):' in line:
            method_start = i
            break
    
    if method_start is None:
        print("⚠️  Could not find run_premarket_analysis (might be okay)")
        return content
    
    print(f"📍 Found run_premarket_analysis at line {method_start + 1}")
    
    # Verify it has [:10] limit
    has_limit = False
    for i in range(method_start, min(method_start + 50, len(lines))):
        if "'signals': signals[:10]" in lines[i]:
            has_limit = True
            print(f"✅ Pre-market already limits to top 10 at line {i + 1}")
            break
    
    if not has_limit:
        print("⚠️  Pre-market doesn't have [:10] limit - might show all signals")
        # Find the signals assignment in result dict
        for i in range(method_start, min(method_start + 50, len(lines))):
            if "'signals': signals" in lines[i] and '[:' not in lines[i]:
                lines[i] = lines[i].replace("'signals': signals", "'signals': signals[:10]  # Top 10 only")
                print(f"✅ Added [:10] limit to pre-market at line {i + 1}")
                break
    
    return '\n'.join(lines)

def main():
    print("=" * 80)
    print("COMPLETE ANALYZER FIX - Rate Limiting + Top 10 Signals")
    print("=" * 80)
    print()
    print("This patch will:")
    print("  1. Add 0.25 second delay between each stock analysis")
    print("  2. Show progress every 10 stocks")
    print("  3. Ensure only top 10 highest confidence signals returned")
    print("  4. Prevent 'Access denied because of exceeding access rate' errors")
    print()
    print("Expected behavior:")
    print("  • Analyzing 93 stocks will take ~23 seconds (instead of instant)")
    print("  • Console shows: 'Progress: 30/93 stocks analyzed...'")
    print("  • Returns: 'Returning 10 of 37 signals (top 10)'")
    print("  • NO MORE rate limit errors!")
    print()
    
    analyzer_file = r"analyzer\enhanced_analyzer.py"
    
    if not os.path.exists(analyzer_file):
        print(f"❌ ERROR: File not found: {analyzer_file}")
        print()
        print("Make sure you're running this from:")
        print("   c:\\Users\\Dell\\tradingbot_new\\")
        print()
        input("Press ENTER to exit...")
        return 1
    
    print(f"📂 Target file: {analyzer_file}")
    print()
    
    # Read content
    try:
        with open(analyzer_file, 'r', encoding='utf-8') as f:
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
        backup_path = create_backup(analyzer_file)
    except Exception as e:
        print(f"❌ ERROR creating backup: {e}")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("🔧 Patching analyzer methods...")
    print()
    
    # Patch analyze_watchlist
    patched_content = patch_analyze_watchlist(original_content)
    
    if patched_content is None:
        print()
        print("❌ PATCH FAILED - File not modified")
        input("Press ENTER to exit...")
        return 1
    
    # Patch premarket
    patched_content = patch_premarket_analysis(patched_content)
    
    # Write patched content
    print()
    print("💾 Writing patched file...")
    
    try:
        with open(analyzer_file, 'w', encoding='utf-8') as f:
            f.write(patched_content)
        print(f"✅ File patched successfully!")
    except Exception as e:
        print(f"❌ ERROR writing file: {e}")
        print()
        print("🔄 Restoring from backup...")
        try:
            shutil.copy2(backup_path, analyzer_file)
            print("✅ Backup restored")
        except:
            print("❌ Could not restore backup!")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("=" * 80)
    print("✅ PATCH COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print()
    print("📋 What was fixed:")
    print("   • Added time.sleep(0.25) between each stock")
    print("   • Progress updates every 10 stocks")
    print("   • Returns top 10 highest confidence signals only")
    print("   • Pre-market also limited to top 10")
    print()
    print("⏱️  Expected timing:")
    print("   • 10 stocks: ~2.5 seconds")
    print("   • 25 stocks: ~6 seconds")
    print("   • 50 stocks: ~12 seconds")
    print("   • 93 stocks: ~23 seconds")
    print()
    print("📊 Console output example:")
    print("   📊 Analyzing 93 stocks with rate limiting...")
    print("   ⏳ Progress: 10/93 stocks analyzed... (3 signals so far)")
    print("   ⏳ Progress: 20/93 stocks analyzed... (7 signals so far)")
    print("   ...")
    print("   ✅ Analysis complete: Returning 10 of 37 signals (top 10)")
    print()
    print("🚀 Next step:")
    print("   python main.py")
    print()
    print("🔄 To restore if needed:")
    print(f"   copy {os.path.basename(backup_path)} {analyzer_file}")
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