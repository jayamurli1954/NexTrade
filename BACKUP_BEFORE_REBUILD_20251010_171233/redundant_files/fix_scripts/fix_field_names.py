"""
Final fix: Standardize all field names to match UI expectations
Changes: entry_price -> avg_price, quantity -> qty
"""

from pathlib import Path

def fix_field_names():
    """Standardize field names throughout PaperTrader"""
    
    paper_trader_file = Path('order_manager/paper_trader.py')
    
    if not paper_trader_file.exists():
        print(f"❌ File not found: {paper_trader_file}")
        return False
    
    # Backup
    backup_file = Path('order_manager/paper_trader.py.backup_final')
    print(f"📦 Creating backup: {backup_file}")
    
    with open(paper_trader_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Backup created")
    
    # Replace field names to match UI expectations
    replacements = [
        ("'entry_price'", "'avg_price'"),
        ("pos['entry_price']", "pos['avg_price']"),
        ("'quantity':", "'qty':"),
        ("pos['quantity']", "pos['qty']"),
        ("pos.get('quantity')", "pos.get('qty')"),
        ("entry_price=price", "avg_price=price"),
        ("'entry_price': price", "'avg_price': price"),
        ("pos['entry_price'] *", "pos['avg_price'] *"),
        ("- pos['entry_price']", "- pos['avg_price']"),
    ]
    
    for old, new in replacements:
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            print(f"✓ Replaced '{old}' -> '{new}' ({count} times)")
    
    # Fix holdings_snapshot to use correct field names
    old_snapshot = """            positions_dict[symbol] = {
                'symbol': symbol,
                'quantity': pos['quantity'],
                'entry_price': pos['entry_price'],"""
    
    new_snapshot = """            positions_dict[symbol] = {
                'symbol': symbol,
                'qty': pos['qty'],
                'avg_price': pos['avg_price'],"""
    
    if old_snapshot in content:
        content = content.replace(old_snapshot, new_snapshot)
        print("✓ Fixed holdings_snapshot field names")
    
    # Write fixed content
    with open(paper_trader_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ All field names standardized in: {paper_trader_file}")
    print(f"📦 Backup saved to: {backup_file}")
    
    return True

def main():
    """Main execution"""
    print("\n" + "="*80)
    print(" "*20 + "FIELD NAME STANDARDIZATION FIX")
    print("="*80 + "\n")
    
    print("This fixes ALL field name mismatches:")
    print("  - entry_price → avg_price")
    print("  - quantity → qty")
    print("\nThese match what the UI expects.\n")
    
    if fix_field_names():
        print("\n" + "="*80)
        print("✅ FINAL FIX COMPLETE")
        print("="*80)
        print("\nAll field names now match UI expectations.")
        print("Pre-Market Analysis should work without errors.")
        print("\nTest with: python main.py")
        print("\nCommit after testing:")
        print("  git add order_manager/paper_trader.py")
        print("  git commit -m 'fix: Standardize field names to match UI (avg_price, qty)'")
        print("  git tag -a v1.1.0-stable -m 'Stable intraday trading with UI compatibility'")
    else:
        print("\n❌ Fix failed")

if __name__ == "__main__":
    main()