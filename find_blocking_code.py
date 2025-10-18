#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Find Blocking Code - Aggressive Search
File: find_blocking_code.py

Searches for any code that runs during GUI initialization
"""

import os
import re


def search_for_blocking_patterns(filepath, filename):
    """Search for blocking patterns in a file"""
    
    if not os.path.exists(filepath):
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    blocking_patterns = [
        (r'def __init__.*:', 'INIT METHOD'),
        (r'\.get_ltp\(', 'GET_LTP CALL'),
        (r'\.refresh.*\(', 'REFRESH CALL'),
        (r'for.*in.*symbols', 'SYMBOL LOOP'),
        (r'for.*in.*watchlist', 'WATCHLIST LOOP'),
        (r'\.analyze.*\(', 'ANALYZE CALL'),
        (r'\.subscribe.*\(', 'SUBSCRIBE CALL'),
        (r'\.fetch.*\(', 'FETCH CALL'),
        (r'time\.sleep\(', 'SLEEP CALL'),
        (r'\.update.*\(', 'UPDATE CALL'),
    ]
    
    findings = []
    
    for i, line in enumerate(lines):
        for pattern, name in blocking_patterns:
            if re.search(pattern, line):
                findings.append({
                    'file': filename,
                    'line': i + 1,
                    'type': name,
                    'code': line.strip()
                })
    
    return findings


def main():
    print("="*70)
    print("AGGRESSIVE BLOCKING CODE SEARCH")
    print("="*70)
    print()
    print("Searching all Python files for blocking operations...")
    print()
    
    all_findings = []
    
    # Search main files
    files_to_search = [
        ('main.py', 'main.py'),
        (r'ui\professional_trading_ui.py', 'UI'),
        (r'data_provider\angel_provider.py', 'PROVIDER'),
        (r'analyzer\enhanced_analyzer.py', 'ANALYZER'),
    ]
    
    for filepath, name in files_to_search:
        findings = search_for_blocking_patterns(filepath, name)
        if findings:
            all_findings.extend(findings)
    
    # Group by file
    if all_findings:
        current_file = None
        for finding in all_findings:
            if finding['file'] != current_file:
                current_file = finding['file']
                print(f"\n📂 {current_file}")
                print("-" * 70)
            
            print(f"Line {finding['line']:4d} | {finding['type']:20s} | {finding['code'][:50]}")
    
    print()
    print("="*70)
    print("SEARCH COMPLETE")
    print("="*70)
    print()
    
    # Now do a targeted search for __init__ methods
    print("\n🔍 Looking specifically for __init__ methods...\n")
    
    ui_file = r"ui\professional_trading_ui.py"
    if os.path.exists(ui_file):
        with open(ui_file, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Find all __init__ methods
        for i, line in enumerate(lines):
            if 'def __init__' in line:
                print(f"Found __init__ at line {i + 1}:")
                print(f"  {line.strip()}")
                
                # Show next 30 lines
                print("\n  First 30 lines of __init__:")
                for j in range(i + 1, min(i + 31, len(lines))):
                    if lines[j].strip():
                        indent = len(lines[j]) - len(lines[j].lstrip())
                        # Stop at next method
                        if indent <= 4 and 'def ' in lines[j]:
                            break
                        print(f"    {j+1:4d}: {lines[j].rstrip()}")
                
                print()
    
    print("\n" + "="*70)
    print("🎯 LIKELY CULPRITS:")
    print("="*70)
    print()
    print("Look for these patterns in the __init__ output above:")
    print("  • self.refresh_* or self.update_*")
    print("  • self.load_* or self.fetch_*")
    print("  • Loops (for/while) during initialization")
    print("  • get_ltp calls")
    print("  • Any method calls that might hit the API")
    print()
    input("Press ENTER to exit...")


if __name__ == "__main__":
    main()