"""
Automated fix for PaperTrader UI compatibility
Replaces holdings_snapshot() method with UI-compatible version
"""

from pathlib import Path
import re

def fix_paper_trader():
    """Fix the holdings_snapshot method to return UI-compatible format"""
    
    paper_trader_file = Path('order_manager/paper_trader.py')
    
    if not paper_trader_file.exists():
        print(f"❌ File not found: {paper_trader_file}")
        return False
    
    # Backup
    backup_file = Path('order_manager/paper_trader.py.backup2')
    print(f"📦 Creating backup: {backup_file}")
    
    with open(paper_trader_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Backup created")
    
    # Find and replace holdings_snapshot method
    old_method = r'''    def holdings_snapshot\(self\):
        """Get current holdings as DataFrame \(compatible with UI\)"""
        if not self\.positions:
            return pd\.DataFrame\(\)
        
        holdings = \[\]
        for symbol, pos in self\.positions\.items\(\):
            holdings\.append\(\{
                'symbol': symbol,
                'quantity': pos\['quantity'\],
                'avg_price': pos\['entry_price'\],
                'ltp': pos\['current_price'\],
                'pnl': pos\['pnl'\],
                'type': pos\['position_type'\]
            \}\)
        
        return pd\.DataFrame\(holdings\)'''
    
    new_method = '''    def holdings_snapshot(self):
        """Get current holdings snapshot compatible with UI"""
        summary = self.get_summary()
        
        # Build positions list
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
            })
        
        # Return dict format expected by UI
        return {
            'total_positions': len(self.positions),
            'cash': self.cash,
            'used_margin': self.used_margin,
            'available_margin': self.get_available_margin(),
            'unrealized_pnl': summary['unrealized_pnl'],
            'portfolio_value': summary['portfolio_value'],
            'positions': positions_list
        }'''
    
    if re.search(old_method, content, re.MULTILINE):
        content = re.sub(old_method, new_method, content, flags=re.MULTILINE)
        print("✓ Replaced holdings_snapshot() method with UI-compatible version")
    else:
        # Try simpler replacement - just find the method and replace entire block
        lines = content.split('\n')
        new_lines = []
        in_holdings_method = False
        method_indent = None
        skip_until_next_def = False
        
        for i, line in enumerate(lines):
            if 'def holdings_snapshot(self):' in line:
                in_holdings_method = True
                method_indent = len(line) - len(line.lstrip())
                # Add new method
                new_lines.extend(new_method.split('\n'))
                skip_until_next_def = True
                continue
            
            if skip_until_next_def:
                # Skip lines until we reach next method or end of class
                if line.strip() and not line.strip().startswith('#'):
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= method_indent and (line.strip().startswith('def ') or line.strip().startswith('class ')):
                        skip_until_next_def = False
                        in_holdings_method = False
                        new_lines.append(line)
                    elif line.strip() == '':
                        # Empty line within method - skip
                        continue
                continue
            
            new_lines.append(line)
        
        content = '\n'.join(new_lines)
        print("✓ Replaced holdings_snapshot() method (alternative approach)")
    
    # Write updated content
    with open(paper_trader_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Fix applied to: {paper_trader_file}")
    print(f"📦 Backup saved to: {backup_file}")
    
    return True

def main():
    """Main execution"""
    print("\n" + "="*80)
    print(" "*20 + "PAPER TRADER UI COMPATIBILITY FIX")
    print("="*80 + "\n")
    
    print("This fixes the 'total_positions' KeyError by updating holdings_snapshot()")
    print("to return the format expected by the UI.\n")
    
    if fix_paper_trader():
        print("\n" + "="*80)
        print("✅ FIX COMPLETE")
        print("="*80)
        print("\nThe PaperTrader now returns UI-compatible data format.")
        print("\nTest with: python main.py")
        print("\nPre-Market Analysis should now work with buy() and sell() methods.")
    else:
        print("\n❌ Fix failed - check error messages above")

if __name__ == "__main__":
    main()