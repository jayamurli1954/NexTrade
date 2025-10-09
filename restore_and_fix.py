import os
import shutil

# Use the most recent backup
backup = "ui/professional_trading_ui.py.backup_20251007_221549"
ui_file = "ui/professional_trading_ui.py"

print("Restoring from backup...")

# Restore backup
shutil.copy2(backup, ui_file)

# Read
with open(ui_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the incomplete line and remove everything after it
# Looking for the line that has ONLY "columns = ('symbol" and nothing else
lines = content.split('\n')
fixed_lines = []
found_break = False

for line in lines:
    # Check if this is the broken line
    if line.strip() == "columns = ('symbol" or (line.strip().startswith("columns = ('symbol") and not line.strip().endswith("'action')")):
        print(f"Found broken line: {line[:50]}")
        found_break = True
        # Add complete version
        indent = len(line) - len(line.lstrip())
        fixed_lines.append(' ' * indent + "columns = ('symbol', 'qty', 'avg_price', 'current_price', 'pnl', 'pnl_pct', 'action')")
        fixed_lines.append(' ' * indent + "self.position_tree = ttk.Treeview(box, columns=columns, show='headings', height=15)")
        fixed_lines.append(' ' * indent + "")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('symbol', text='Symbol')")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('qty', text='Qty')")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('avg_price', text='Avg Price')")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('current_price', text='Live Price')")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('pnl', text='P&L (₹)')")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('pnl_pct', text='P&L %')")
        fixed_lines.append(' ' * indent + "self.position_tree.heading('action', text='Action')")
        fixed_lines.append(' ' * indent + "")
        fixed_lines.append(' ' * indent + "self.position_tree.column('symbol', width=100)")
        fixed_lines.append(' ' * indent + "self.position_tree.column('qty', width=80)")
        fixed_lines.append(' ' * indent + "self.position_tree.column('avg_price', width=120)")
        fixed_lines.append(' ' * indent + "self.position_tree.column('current_price', width=120)")
        fixed_lines.append(' ' * indent + "self.position_tree.column('pnl', width=120)")
        fixed_lines.append(' ' * indent + "self.position_tree.column('pnl_pct', width=100)")
        fixed_lines.append(' ' * indent + "self.position_tree.column('action', width=100)")
        fixed_lines.append(' ' * indent + "")
        fixed_lines.append(' ' * indent + "self.position_tree.pack(fill='both', expand=True)")
        fixed_lines.append(' ' * indent + "self.position_tree.bind('<Button-1>', self._on_position_click)")
        break  # Stop here, file was truncated after this
    else:
        if not found_break:
            fixed_lines.append(line)

# Write
with open(ui_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print("DONE! File restored and fixed properly.")
input("Press Enter...")