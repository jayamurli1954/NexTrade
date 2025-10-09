#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Pre-Market Signal Display - Show Top 10 Only
File: fix_premarket_top10.py

Issue: Pre-market shows all 37 signals, but we only want top 10 highest confidence
Fix: Sort by confidence and display only top 10 signals
"""

import os
import shutil
from datetime import datetime

def create_backup(filepath):
    """Create backup of file before patching"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_top10_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def patch_premarket_method(content):
    """Patch the _run_premarket_analysis method to show top 10 only"""
    
    lines = content.split('\n')
    
    # Find the on_success function within _run_premarket_analysis
    success_func_start = None
    for i, line in enumerate(lines):
        if 'def on_success(result):' in line and i > 0:
            # Make sure it's inside _run_premarket_analysis
            for j in range(max(0, i-50), i):
                if 'def _run_premarket_analysis(self):' in lines[j]:
                    success_func_start = i
                    break
            if success_func_start:
                break
    
    if success_func_start is None:
        print("❌ ERROR: Could not find on_success function in _run_premarket_analysis")
        return None
    
    print(f"📍 Found on_success function at line {success_func_start + 1}")
    
    # Find the line that clears the tree
    clear_tree_idx = None
    for i in range(success_func_start, min(success_func_start + 30, len(lines))):
        if 'self.premarket_tree.delete(item)' in lines[i]:
            clear_tree_idx = i
            break
    
    if clear_tree_idx is None:
        print("❌ ERROR: Could not find tree clearing code")
        return None
    
    # Find the for loop that inserts signals
    insert_loop_idx = None
    for i in range(clear_tree_idx, min(clear_tree_idx + 20, len(lines))):
        if "for sig in result['signals']" in lines[i]:
            insert_loop_idx = i
            break
    
    if insert_loop_idx is None:
        print("❌ ERROR: Could not find signal insertion loop")
        return None
    
    print(f"📍 Found signal insertion loop at line {insert_loop_idx + 1}")
    
    # Get the indentation of the for loop
    indent = len(lines[insert_loop_idx]) - len(lines[insert_loop_idx].lstrip())
    indent_str = ' ' * indent
    
    # Insert sorting and limiting code before the for loop
    new_lines = [
        f"{indent_str}# ✅ Sort by confidence (descending) and take top 10",
        f"{indent_str}sorted_signals = sorted(result['signals'], key=lambda x: x.get('confidence', 0), reverse=True)",
        f"{indent_str}top_signals = sorted_signals[:10]",
        f"{indent_str}",
        f"{indent_str}# Update info text to show filtered count",
        f"{indent_str}total_found = len(result['signals'])",
        f"{indent_str}showing_count = len(top_signals)",
    ]
    
    # Modify the info text line
    info_text_idx = None
    for i in range(clear_tree_idx, insert_loop_idx):
        if 'info_text = f"""Timestamp:' in lines[i] or 'info_text = f"Timestamp:' in lines[i]:
            info_text_idx = i
            break
    
    if info_text_idx:
        # Find the end of the info_text assignment (might span multiple lines)
        info_text_end = info_text_idx
        for i in range(info_text_idx, min(info_text_idx + 10, len(lines))):
            if '"""' in lines[i] and i > info_text_idx:
                info_text_end = i
                break
        
        # Modify the analyzed line to show "Showing X of Y signals"
        for i in range(info_text_idx, info_text_end + 1):
            if 'Analyzed:' in lines[i]:
                # Replace the signals info
                old_line = lines[i]
                # Keep everything before "Signals:"
                if '| Signals:' in old_line:
                    before_signals = old_line.split('| Signals:')[0]
                    lines[i] = before_signals + f"| Showing: {{showing_count}} of {{total_found}} signals | High Confidence: {{result['high_confidence_signals']}}\"\"\""
                    print(f"✅ Modified info text at line {i + 1}")
    
    # Insert the new lines before the for loop
    lines = lines[:insert_loop_idx] + new_lines + lines[insert_loop_idx:]
    
    # Now adjust the insert_loop_idx since we added lines
    insert_loop_idx += len(new_lines)
    
    # Modify the for loop to use top_signals instead of result['signals']
    if "for sig in result['signals']" in lines[insert_loop_idx]:
        lines[insert_loop_idx] = lines[insert_loop_idx].replace("result['signals']", "top_signals")
        print(f"✅ Modified loop to use top_signals at line {insert_loop_idx + 1}")
    
    return '\n'.join(lines)

def patch_analyzer_method(content):
    """Also patch the regular analyzer to show top 10"""
    
    lines = content.split('\n')
    
    # Find the on_success function within _run_analysis
    success_func_start = None
    for i, line in enumerate(lines):
        if 'def on_success(signals):' in line:
            # Make sure it's inside _run_analysis
            for j in range(max(0, i-50), i):
                if 'def _run_analysis(self):' in lines[j]:
                    success_func_start = i
                    break
            if success_func_start:
                break
    
    if success_func_start is None:
        print("⚠️  Could not find on_success in _run_analysis (might already be patched)")
        return content
    
    print(f"📍 Found _run_analysis on_success at line {success_func_start + 1}")
    
    # Find the for loop
    insert_loop_idx = None
    for i in range(success_func_start, min(success_func_start + 50, len(lines))):
        if "for sig in signals:" in lines[i]:
            insert_loop_idx = i
            break
    
    if insert_loop_idx is None:
        return content
    
    # Get indentation
    indent = len(lines[insert_loop_idx]) - len(lines[insert_loop_idx].lstrip())
    indent_str = ' ' * indent
    
    # Insert sorting code
    new_lines = [
        f"{indent_str}# ✅ Sort by confidence and take top 10",
        f"{indent_str}sorted_signals = sorted(signals, key=lambda x: x.get('confidence', 0), reverse=True)",
        f"{indent_str}top_signals = sorted_signals[:10]",
        f"{indent_str}",
    ]
    
    # Find and modify info text
    for i in range(success_func_start, insert_loop_idx):
        if 'info_text = f"""Timestamp:' in lines[i]:
            # Find the line with "Signals Found:"
            for j in range(i, min(i + 10, len(lines))):
                if 'Signals Found:' in lines[j]:
                    lines[j] = lines[j].replace('{len(signals)}', '{len(top_signals)} of {len(signals)}')
                    print(f"✅ Modified analyzer info text at line {j + 1}")
    
    # Insert new lines
    lines = lines[:insert_loop_idx] + new_lines + lines[insert_loop_idx:]
    insert_loop_idx += len(new_lines)
    
    # Modify the loop
    if "for sig in signals:" in lines[insert_loop_idx]:
        lines[insert_loop_idx] = lines[insert_loop_idx].replace("signals:", "top_signals:")
        print(f"✅ Modified analyzer loop at line {insert_loop_idx + 1}")
    
    return '\n'.join(lines)

def main():
    print("=" * 70)
    print("SIGNAL DISPLAY FIX - Show Top 10 Only")
    print("=" * 70)
    print()
    print("Changes:")
    print("  • Pre-Market Analyzer: Shows top 10 highest confidence signals")
    print("  • Regular Analyzer: Shows top 10 highest confidence signals")
    print("  • Info text shows: 'Showing 10 of 37 signals'")
    print()
    
    ui_file = r"ui\professional_trading_ui.py"
    
    if not os.path.exists(ui_file):
        print(f"❌ ERROR: File not found: {ui_file}")
        input("Press ENTER to exit...")
        return 1
    
    print(f"📂 Target file: {ui_file}")
    print()
    
    # Read current content
    try:
        with open(ui_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"❌ ERROR reading file: {e}")
        input("Press ENTER to exit...")
        return 1
    
    # Create backup
    print("🔄 Creating backup...")
    try:
        backup_path = create_backup(ui_file)
    except Exception as e:
        print(f"❌ ERROR creating backup: {e}")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("🔧 Patching Pre-Market Analyzer...")
    
    # Patch premarket method
    patched_content = patch_premarket_method(original_content)
    
    if patched_content is None:
        print("❌ Failed to patch Pre-Market Analyzer")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("🔧 Patching Regular Analyzer...")
    
    # Patch regular analyzer method
    patched_content = patch_analyzer_method(patched_content)
    
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
        print("🔄 Restoring from backup...")
        try:
            shutil.copy2(backup_path, ui_file)
            print("✅ Backup restored")
        except:
            print("❌ Could not restore backup!")
        input("Press ENTER to exit...")
        return 1
    
    print()
    print("=" * 70)
    print("✅ PATCH COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print()
    print("📋 What was fixed:")
    print("   • Pre-Market now shows TOP 10 highest confidence signals only")
    print("   • Regular Analyzer shows TOP 10 highest confidence signals only")
    print("   • Info shows 'Showing 10 of 37 signals' so you know total found")
    print()
    print("🎯 Why this is better:")
    print("   • Focus on best opportunities (max 5 positions anyway)")
    print("   • Less clutter, easier to decide")
    print("   • Sorted by confidence (best first)")
    print()
    print("🚀 Next step:")
    print("   python main.py")
    print()
    print("🔄 To restore if needed:")
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