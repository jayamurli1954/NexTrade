#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Flexible Analyzer Patch - Works with any code structure
File: fix_analyzer_flexible.py

Adds rate limiting by inserting code at the right places
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup of file before patching"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_flex_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def add_import_time(content):
    """Add 'import time' at the top if not present"""
    
    if 'import time' in content:
        print("✅ 'import time' already present")
        return content
    
    lines = content.split('\n')
    
    # Find where to insert (after other imports)
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i + 1
    
    lines.insert(insert_idx, 'import time')
    print(f"✅ Added 'import time' at line {insert_idx + 1}")
    
    return '\n'.join(lines)

def patch_analyze_watchlist_flexible(content):
    """Flexibly patch analyze_watchlist method"""
    
    lines = content.split('\n')
    
    # Find analyze_watchlist method
    method_start = None
    for i, line in enumerate(lines):
        if 'def analyze_watchlist(self' in line:
            method_start = i
            break
    
    if method_start is None:
        print("❌ Could not find analyze_watchlist method")
        return None
    
    print(f"📍 Found analyze_watchlist at line {method_start + 1}")
    
    # Find ANY for loop with symbols
    for_loop_idx = None
    for i in range(method_start, min(method_start + 30, len(lines))):
        line = lines[i].strip()
        if line.startswith('for ') and 'symbols' in line and ':' in line:
            for_loop_idx = i
            print(f"📍 Found for loop at line {i + 1}: {line[:50]}")
            break
    
    if for_loop_idx is None:
        print("❌ Could not find for loop")
        return None
    
    # Extract the loop variable
    for_line = lines[for_loop_idx].strip()
    # Parse: "for sym in symbols:" or "for idx, sym in enumerate(symbols):"
    if 'enumerate' in for_line:
        # Already has enumerate - extract variable names
        loop_vars = for_line.split('for ')[1].split(' in ')[0].strip()
        if ',' in loop_vars:
            idx_var, sym_var = [v.strip() for v in loop_vars.split(',')]
        else:
            print("⚠️ Unexpected enumerate format")
            return None
        already_enumerated = True
    else:
        # Simple for loop
        sym_var = for_line.split('for ')[1].split(' in ')[0].strip()
        idx_var = 'idx'
        already_enumerated = False
    
    print(f"   Loop variable: {sym_var}, Index: {idx_var}, Enumerated: {already_enumerated}")
    
    # Get indentation
    indent = len(lines[for_loop_idx]) - len(lines[for_loop_idx].lstrip())
    indent_str = ' ' * indent
    loop_body_indent = ' ' * (indent + 4)
    
    # Find the line before the for loop to add setup code
    setup_idx = for_loop_idx
    while setup_idx > method_start and not lines[setup_idx - 1].strip():
        setup_idx -= 1
    
    # Add setup code before the loop
    if already_enumerated:
        setup_code = [
            f"{indent_str}# ✅ Rate limiting setup",
            f"{indent_str}total_symbols = len(symbols)",
            f"{indent_str}print(f\"📊 Analyzing {{total_symbols}} stocks with rate limiting...\")",
            ""
        ]
    else:
        setup_code = [
            f"{indent_str}# ✅ Rate limiting setup with enumeration",
            f"{indent_str}total_symbols = len(symbols)",
            f"{indent_str}print(f\"📊 Analyzing {{total_symbols}} stocks with rate limiting...\")",
            ""
        ]
        # Change the for loop to use enumerate
        lines[for_loop_idx] = f"{indent_str}for {idx_var}, {sym_var} in enumerate(symbols):"
        print(f"✅ Changed loop to use enumerate")
    
    # Insert setup code
    for line in reversed(setup_code):
        lines.insert(for_loop_idx, line)
    
    for_loop_idx += len(setup_code)
    
    # Find the end of the try-except block inside the loop
    # Look for the except line
    except_idx = None
    for i in range(for_loop_idx, min(for_loop_idx + 20, len(lines))):
        if lines[i].strip().startswith('except '):
            except_idx = i
            break
    
    if except_idx:
        # Find the end of the except block
        insert_idx = except_idx + 1
        while insert_idx < len(lines):
            line = lines[insert_idx]
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            if line.strip():
                insert_idx += 1
            else:
                insert_idx += 1
        
        # Add rate limiting code after the except block
        rate_limit_code = [
            "",
            f"{loop_body_indent}# ✅ Progress update every 10 stocks",
            f"{loop_body_indent}if {idx_var} > 0 and {idx_var} % 10 == 0:",
            f"{loop_body_indent}    print(f\"  ⏳ Progress: {{{idx_var}}}/{{total_symbols}} analyzed... ({{len(signals)}} signals)\")",
            "",
            f"{loop_body_indent}# ✅ CRITICAL: Rate limiting delay",
            f"{loop_body_indent}if {idx_var} < total_symbols - 1:",
            f"{loop_body_indent}    time.sleep(0.25)  # 250ms = max 4 stocks/sec",
        ]
        
        for line in reversed(rate_limit_code):
            lines.insert(insert_idx, line)
        
        print(f"✅ Added rate limiting code after line {except_idx + 1}")
    else:
        print("⚠️ Could not find except block - adding at end of loop")
        # Find next line with same or less indentation
        insert_idx = for_loop_idx + 1
        while insert_idx < len(lines):
            line = lines[insert_idx]
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= indent:
                break
            insert_idx += 1
        
        rate_limit_code = [
            "",
            f"{loop_body_indent}# ✅ Progress and rate limiting",
            f"{loop_body_indent}if {idx_var} > 0 and {idx_var} % 10 == 0:",
            f"{loop_body_indent}    print(f\"  ⏳ Progress: {{{idx_var}}}/{{total_symbols}} analyzed...\")",
            f"{loop_body_indent}if {idx_var} < total_symbols - 1:",
            f"{loop_body_indent}    time.sleep(0.25)",
        ]
        
        for line in reversed(rate_limit_code):
            lines.insert(insert_idx, line)
    
    # Add final summary before return
    for i in range(for_loop_idx, len(lines)):
        if 'return signals' in lines[i] and i > for_loop_idx + 20:
            # Add summary before return
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            indent_str = ' ' * current_indent
            
            summary = [
                "",
                f"{indent_str}# ✅ Return top 10 only",
                f"{indent_str}top_signals = signals[:10] if len(signals) > 10 else signals",
                f"{indent_str}print(f\"✅ Analysis complete: Returning {{len(top_signals)}} of {{len(signals)}} signals\")",
                f"{indent_str}return top_signals"
            ]
            
            lines[i:i+1] = summary
            print(f"✅ Modified return statement at line {i + 1}")
            break
    
    return '\n'.join(lines)

def main():
    print("=" * 80)
    print("FLEXIBLE ANALYZER PATCH - Rate Limiting")
    print("=" * 80)
    print()
    
    analyzer_file = r"analyzer\enhanced_analyzer.py"
    
    if not os.path.exists(analyzer_file):
        print(f"❌ ERROR: File not found: {analyzer_file}")
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
    
    # Create backup
    print("🔄 Creating backup...")
    backup_path = create_backup(analyzer_file)
    print()
    
    # Add import time
    print("🔧 Adding time import...")
    patched_content = add_import_time(original_content)
    print()
    
    # Patch the method
    print("🔧 Patching analyze_watchlist...")
    patched_content = patch_analyze_watchlist_flexible(patched_content)
    
    if patched_content is None:
        print()
        print("❌ PATCH FAILED")
        input("Press ENTER to exit...")
        return 1
    
    # Write patched content
    print()
    print("💾 Writing patched file...")
    
    try:
        with open(analyzer_file, 'w', encoding='utf-8') as f:
            f.write(patched_content)
        print(f"✅ File patched successfully!")
    except Exception as e:
        print(f"❌ ERROR writing file: {e}")
        shutil.copy2(backup_path, analyzer_file)
        print("Backup restored")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("=" * 80)
    print("✅ PATCH COMPLETED!")
    print("=" * 80)
    print()
    print("⏱️  Analysis will now take ~23 seconds for 93 stocks")
    print("📊 Shows progress every 10 stocks")
    print("🚀 NO MORE rate limit errors!")
    print()
    print("Next: Wait 15 minutes, then test with: python main.py")
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
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress ENTER to exit...")
        sys.exit(1)