import os
import shutil
from datetime import datetime

ui_file = "ui/professional_trading_ui.py"

print("Fixing indentation...")

# Backup
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"ui/professional_trading_ui.py.backup_{timestamp}"
shutil.copy2(ui_file, backup)
print(f"Backup: {backup}")

# Read
with open(ui_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the problem line
fixed_lines = []
found_problem = False

for i, line in enumerate(lines):
    # If we find the duplicate/misaligned columns line
    if "columns = ('symbol', 'qty', 'avg_price', 'current_price', 'pnl', 'pnl_pct', 'action')" in line:
        if found_problem:
            # Skip duplicate
            print(f"Skipping duplicate at line {i+1}")
            continue
        found_problem = True
    
    fixed_lines.append(line)

# Write fixed version
with open(ui_file, 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print(f"Fixed! Removed duplicate line.")
print(f"Backup saved to: {backup}")
input("Press Enter...")