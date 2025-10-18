"""
Final fix for PaperTrader UI compatibility
Changes positions from list to dict format
"""

from pathlib import Path

def fix_positions_format():
    """Fix holdings_snapshot to return positions as dict instead of list"""
    
    paper_trader_file = Path('order_manager/paper_trader.py')
    
    if not paper_trader_file.exists():
        print(f"❌ File not found: {paper_trader_file}")
        return False
    
    # Backup
    backup_file = Path('order_manager/paper_trader.py.backup3')
    print(f"📦 Creating backup: {backup_file}")
    
    with open(paper_trader_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Backup created")
    
    # Find the holdings_snapshot method and replace positions format
    old_positions = "'positions': positions_list"
    new_positions = "'positions': {symbol: pos for symbol, pos in self.positions.items()}"
    
    if old_positions in content:
        content = content.replace(old_positions, new_positions)
        print("✓ Changed positions from list to dict format")
    else:
        print("⚠️  Old format not found, trying alternative...")
        
        # Alternative: replace the entire positions building section
        old_block = """        # Build positions list
        positions_list = []
        for symbol, pos in self.positions.items():
            positions_list.append({
                'symbol': symbol,
                'quantity': pos['quantity'],
                'entry_price': pos['entry_price'],
                'current_price': pos['current_price'],
                'pnl': pos['pnl'],
                'type': pos['position_type'],
                'stoploss': pos.get('stoploss'),
                'target': pos.get('target')
            })"""
        
        new_block = """        # Build positions dict for UI compatibility
        positions_dict = {}
        for symbol, pos in self.positions.items():
            positions_dict[symbol] = {
                'symbol': symbol,
                'quantity': pos['quantity'],
                'entry_price': pos['entry_price'],
                'current_price': pos['current_price'],
                'pnl': pos['pnl'],
                'type': pos['position_type'],
                'stoploss': pos.get('stoploss'),
                'target': pos.get('target')
            }"""
        
        if old_block in content:
            content = content.replace(old_block, new_block)
            content = content.replace("'positions': positions_list", "'positions': positions_dict")
            print("✓ Changed positions building logic to dict format")
        else:
            print("❌ Could not find positions section to replace")
            return False
    
    # Write updated content
    with open(paper_trader_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Fix applied to: {paper_trader_file}")
    print(f"📦 Backup saved to: {backup_file}")
    
    return True

def main():
    """Main execution"""
    print("\n" + "="*80)
    print(" "*25 + "POSITIONS FORMAT FIX")
    print("="*80 + "\n")
    
    print("This fixes the 'list' object has no attribute 'items' error")
    print("by changing positions from list to dict format.\n")
    
    if fix_positions_format():
        print("\n" + "="*80)
        print("✅ FIX COMPLETE")
        print("="*80)
        print("\nPositions now returned as dict (compatible with UI).")
        print("\nTest with: python main.py")
    else:
        print("\n❌ Fix failed - check error messages above")

if __name__ == "__main__":
    main()