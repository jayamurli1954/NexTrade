"""
Fix Watchlist Format Issue
Converts watchlist from dict format to simple symbol list
"""

import json
from pathlib import Path

def fix_watchlist_format():
    """Fix the watchlist.json format to match what UI expects"""
    
    watchlist_file = Path('data/watchlist.json')
    
    if not watchlist_file.exists():
        print(f"❌ Watchlist file not found: {watchlist_file}")
        return False
    
    # Backup
    backup_file = Path('data/watchlist.json.backup')
    print(f"📦 Creating backup: {backup_file}")
    
    with open(watchlist_file, 'r') as f:
        current_data = json.load(f)
    
    with open(backup_file, 'w') as f:
        json.dump(current_data, f, indent=2)
    
    print(f"✓ Backup created with {len(current_data)} stocks")
    
    # Check current format
    if current_data and isinstance(current_data[0], dict):
        print("\n📊 Current format: List of dictionaries")
        print("Converting to simple symbol list...")
        
        # Extract just the symbols
        symbols = [stock['symbol'] for stock in current_data]
        
        # Save as simple list
        with open(watchlist_file, 'w') as f:
            json.dump(symbols, f, indent=2)
        
        print(f"✓ Converted to simple list format with {len(symbols)} symbols")
        
        # Show sample
        print("\n📋 Sample (first 5):")
        for sym in symbols[:5]:
            print(f"  - {sym}")
        
        return True
    
    elif current_data and isinstance(current_data[0], str):
        print("✓ Watchlist already in correct format (simple list)")
        return True
    
    else:
        print("❌ Unknown watchlist format")
        return False

def main():
    """Main execution"""
    print("\n" + "="*80)
    print(" "*25 + "WATCHLIST FORMAT FIXER")
    print("="*80 + "\n")
    
    if fix_watchlist_format():
        print("\n" + "="*80)
        print("✅ WATCHLIST FORMAT FIXED")
        print("="*80)
        print("\nThe watchlist is now compatible with the UI.")
        print("Test with: python main.py")
    else:
        print("\n❌ Fix failed")

if __name__ == "__main__":
    main()