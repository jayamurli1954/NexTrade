import os
import shutil
from datetime import datetime

ui_file = "ui/professional_trading_ui.py"

print("Fixing UI file...")

# Backup
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"ui/professional_trading_ui.py.backup_{timestamp}"
shutil.copy2(ui_file, backup)
print(f"Backup: {backup}")

# Read
with open(ui_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Find where it breaks
pos = content.find("columns = ('symbol")

if pos > 0:
    # Keep everything before
    fixed = content[:pos]
    
    # Add complete ending
    ending = """        columns = ('symbol', 'qty', 'avg_price', 'current_price', 'pnl', 'pnl_pct', 'action')
        self.position_tree = ttk.Treeview(box, columns=columns, show='headings', height=15)
        
        self.position_tree.heading('symbol', text='Symbol')
        self.position_tree.heading('qty', text='Qty')
        self.position_tree.heading('avg_price', text='Avg Price')
        self.position_tree.heading('current_price', text='Live Price')
        self.position_tree.heading('pnl', text='P&L (₹)')
        self.position_tree.heading('pnl_pct', text='P&L %')
        self.position_tree.heading('action', text='Action')
        
        self.position_tree.column('symbol', width=100)
        self.position_tree.column('qty', width=80)
        self.position_tree.column('avg_price', width=120)
        self.position_tree.column('current_price', width=120)
        self.position_tree.column('pnl', width=120)
        self.position_tree.column('pnl_pct', width=100)
        self.position_tree.column('action', width=100)
        
        self.position_tree.pack(fill="both", expand=True)
        self.position_tree.bind('<Button-1>', self._on_position_click)
"""
    
    fixed += ending
    
    # Write
    with open(ui_file, 'w', encoding='utf-8') as f:
        f.write(fixed)
    
    print("DONE! File fixed.")
else:
    print("File already complete")

input("Press Enter...")