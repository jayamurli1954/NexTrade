#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Patch: Fix Qt.AlignCenter in positions_tab.py
"""

import os

filepath = "ui_new/tabs/positions_tab.py"

print("🔧 Fixing Qt.AlignCenter in positions_tab.py...")

# Read file
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the alignment
content = content.replace(
    "no_pos.setAlignment(0x0004)  # Qt.AlignCenter",
    "no_pos.setAlignment(Qt.AlignCenter)"
)

# Write back
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Fixed!")
print()
print("Now run: python test_new_ui.py")
