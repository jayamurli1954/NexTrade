"""
Fix buy() and sell() methods to return tuple format (success, message)
instead of dict format for UI compatibility
"""

from pathlib import Path
import re

def fix_buy_sell_methods():
    """Update buy() and sell() to return tuples instead of dicts"""
    
    paper_trader_file = Path('order_manager/paper_trader.py')
    
    if not paper_trader_file.exists():
        print(f"❌ File not found: {paper_trader_file}")
        return False
    
    # Backup
    backup_file = Path('order_manager/paper_trader.py.backup4')
    print(f"📦 Creating backup: {backup_file}")
    
    with open(paper_trader_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Backup created")
    
    # Fix buy() method
    old_buy = r'''    def buy\(self, symbol, quantity, price, stoploss=None, target=None\):
        """
        Buy \(long\) position.*?
        """
        return self\.execute_order\(
            symbol=symbol,
            action='BUY',
            quantity=quantity,
            price=price,
            stoploss=stoploss,
            target=target
        \)'''
    
    new_buy = '''    def buy(self, symbol, quantity, price, stoploss=None, target=None):
        """Buy (long) position - Returns tuple (success, message)"""
        result = self.execute_order(
            symbol=symbol,
            action='BUY',
            quantity=quantity,
            price=price,
            stoploss=stoploss,
            target=target
        )
        # Return tuple format expected by UI: (success, message)
        return result['success'], result['message']'''
    
    # Fix sell() method
    old_sell = r'''    def sell\(self, symbol, quantity, price, stoploss=None, target=None\):
        """
        Sell \(short\) position.*?
        """
        if not self\.enable_intraday:
            return \{
                'success': False,
                'message': 'Short selling not enabled\. Set enable_intraday=True'
            \}
        
        return self\.execute_order\(
            symbol=symbol,
            action='SELL',
            quantity=quantity,
            price=price,
            stoploss=stoploss,
            target=target
        \)'''
    
    new_sell = '''    def sell(self, symbol, quantity, price, stoploss=None, target=None):
        """Sell (short) position - Intraday only - Returns tuple (success, message)"""
        if not self.enable_intraday:
            return False, 'Short selling not enabled. Set enable_intraday=True'
        
        result = self.execute_order(
            symbol=symbol,
            action='SELL',
            quantity=quantity,
            price=price,
            stoploss=stoploss,
            target=target
        )
        # Return tuple format expected by UI: (success, message)
        return result['success'], result['message']'''
    
    # Apply fixes
    content = re.sub(old_buy, new_buy, content, flags=re.DOTALL)
    content = re.sub(old_sell, new_sell, content, flags=re.DOTALL)
    
    # Alternative simpler replacement if regex fails
    if 'return result[\'success\'], result[\'message\']' not in content:
        print("⚠️  Regex didn't match, trying line-by-line replacement...")
        
        lines = content.split('\n')
        new_lines = []
        in_buy = False
        in_sell = False
        
        for i, line in enumerate(lines):
            if 'def buy(self, symbol, quantity, price' in line:
                in_buy = True
                new_lines.append(line)
                continue
            
            if 'def sell(self, symbol, quantity, price' in line:
                in_sell = True
                new_lines.append(line)
                continue
            
            if in_buy:
                if 'return self.execute_order(' in line:
                    # Replace with result storage
                    indent = len(line) - len(line.lstrip())
                    new_lines.append(' ' * indent + 'result = self.execute_order(')
                    continue
                elif line.strip() == ')':
                    new_lines.append(line)
                    indent = len(line) - len(line.lstrip())
                    new_lines.append(' ' * indent + "# Return tuple format expected by UI: (success, message)")
                    new_lines.append(' ' * indent + "return result['success'], result['message']")
                    in_buy = False
                    continue
            
            if in_sell:
                if "'success': False," in line and "'message':" in content[content.find(line):content.find(line)+200]:
                    # Replace dict return with tuple
                    indent = len(line) - len(line.lstrip())
                    new_lines.append(' ' * indent + "return False, 'Short selling not enabled. Set enable_intraday=True'")
                    # Skip next lines until closing brace
                    while i < len(lines) and '}' not in lines[i]:
                        i += 1
                    continue
                elif 'return self.execute_order(' in line:
                    indent = len(line) - len(line.lstrip())
                    new_lines.append(' ' * indent + 'result = self.execute_order(')
                    continue
                elif line.strip() == ')' and in_sell:
                    new_lines.append(line)
                    indent = len(line) - len(line.lstrip())
                    new_lines.append(' ' * indent + "# Return tuple format expected by UI: (success, message)")
                    new_lines.append(' ' * indent + "return result['success'], result['message']")
                    in_sell = False
                    continue
            
            new_lines.append(line)
        
        content = '\n'.join(new_lines)
        print("✓ Applied line-by-line replacement")
    else:
        print("✓ Applied regex replacement")
    
    # Write fixed content
    with open(paper_trader_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Fix applied to: {paper_trader_file}")
    print(f"📦 Backup saved to: {backup_file}")
    
    return True

def main():
    """Main execution"""
    print("\n" + "="*80)
    print(" "*20 + "BUY/SELL RETURN FORMAT FIX")
    print("="*80 + "\n")
    
    print("This fixes the 'too many values to unpack' error by changing")
    print("buy() and sell() methods to return (success, message) tuples.\n")
    
    if fix_buy_sell_methods():
        print("\n" + "="*80)
        print("✅ FIX COMPLETE")
        print("="*80)
        print("\nMethods now return tuple format: (success, message)")
        print("Pre-Market Analysis trade execution should work now.")
        print("\nTest with: python main.py")
    else:
        print("\n❌ Fix failed - check error messages above")

if __name__ == "__main__":
    main()