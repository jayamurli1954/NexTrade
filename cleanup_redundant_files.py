#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SCRIPT NAME: cleanup_redundant_files.py
# SAVE LOCATION: c:\Users\Dell\tradingbot_new\cleanup_redundant_files.py
# PURPOSE: Shows what files to DELETE and what to KEEP
# RUN COMMAND: python cleanup_redundant_files.py
# ==============================================================================

import os

print("=" * 80)
print("📄 SCRIPT: cleanup_redundant_files.py")
print("🧹 PURPOSE: Clean up redundant files")
print("=" * 80)
print()

# Files to KEEP in tradingbot_new/
KEEP_FILES = {
    "Root Directory (c:\\Users\\Dell\\tradingbot_new\\)": [
        "main.py",                      # Your main trading bot script
        "test_new_ui.py",               # UI test launcher
        "create_tab_modules.py",        # Tab generator (after first use, can delete)
        "trades_log.xlsx",              # Trade history data
        "stock_list.txt",               # Your stock list
        "requirements.txt",             # Python dependencies
        ".env or config files",         # API credentials
    ],
    
    "ui_new/ folder": [
        "main_window.py",               # Main UI coordinator (130 lines)
        "data_handler.py",              # Data management (200 lines)
    ],
    
    "ui_new/tabs/ folder": [
        "__init__.py",
        "dashboard_tab.py",
        "holdings_tab.py",
        "watchlist_tab.py",             # NEW - Watchlist monitor
        "positions_tab.py",
        "history_tab.py",
        "analyzer_tab.py",
        "premarket_tab.py",
        "settings_tab.py",
    ]
}

# Files/folders to DELETE or IGNORE
DELETE_OR_IGNORE = [
    "ui/ (old UI folder - if you have it)",
    "professional_trading_ui.py (old monolithic UI)",
    "trading_ui.py (old version)",
    "fix_imports.py (temporary fix script)",
    "patch_positions.py (temporary patch)",
    "__pycache__/ folders",
    "*.pyc files",
    "Any backup files (.bak, .old)",
]

print("✅ FILES TO KEEP:")
print("=" * 80)
for location, files in KEEP_FILES.items():
    print(f"\n📁 {location}")
    for f in files:
        print(f"   ✅ {f}")

print()
print()
print("🗑️  FILES/FOLDERS TO DELETE:")
print("=" * 80)
for item in DELETE_OR_IGNORE:
    print(f"   ❌ {item}")

print()
print()
print("🎯 RECOMMENDED FOLDER STRUCTURE:")
print("=" * 80)
print("""
c:\\Users\\Dell\\tradingbot_new\\
├── main.py                      ← Main trading bot
├── test_new_ui.py               ← UI launcher
├── trades_log.xlsx              ← Trade data
├── stock_list.txt               ← Stock list
├── .env                         ← API credentials
│
├── ui_new/                      ← New modular UI
│   ├── main_window.py           ← 130 lines coordinator
│   ├── data_handler.py          ← 200 lines data manager
│   │
│   └── tabs/                    ← Individual tab modules
│       ├── __init__.py
│       ├── dashboard_tab.py     ← 150 lines
│       ├── holdings_tab.py      ← 200 lines
│       ├── watchlist_tab.py     ← 180 lines (NEW!)
│       ├── positions_tab.py     ← 80 lines
│       ├── history_tab.py       ← 150 lines
│       ├── analyzer_tab.py      ← 100 lines
│       ├── premarket_tab.py     ← 100 lines
│       └── settings_tab.py      ← 150 lines
│
└── Other modules (analyzer, data_provider, etc.)
""")

print()
print("=" * 80)
print("🔍 CHECK YOUR FOLDER:")
print("=" * 80)
print()

# Check if common redundant files exist
redundant_checks = [
    ("ui/professional_trading_ui.py", "Old monolithic UI (1500+ lines)"),
    ("professional_trading_ui.py", "Old UI in root"),
    ("fix_imports.py", "Temporary fix script"),
    ("patch_positions.py", "Temporary patch"),
]

for filepath, desc in redundant_checks:
    if os.path.exists(filepath):
        print(f"⚠️  FOUND REDUNDANT: {filepath}")
        print(f"   Description: {desc}")
        print(f"   Action: Can be deleted")
        print()

# Check ui_new structure
if os.path.exists("ui_new"):
    print("✅ ui_new/ folder exists")
    
    if os.path.exists("ui_new/main_window.py"):
        with open("ui_new/main_window.py", 'r') as f:
            content = f.read()
            if "WatchlistTab" in content:
                print("   ✅ main_window.py includes Watchlist")
            else:
                print("   ⚠️  main_window.py MISSING Watchlist - needs update!")
    
    if os.path.exists("ui_new/tabs"):
        tabs = [f for f in os.listdir("ui_new/tabs") if f.endswith(".py")]
        print(f"   ✅ Found {len(tabs)} tab files")
        if "watchlist_tab.py" in tabs:
            print("      ✅ watchlist_tab.py exists")
        else:
            print("      ⚠️  watchlist_tab.py MISSING - run create_tab_modules.py")
else:
    print("⚠️  ui_new/ folder not found - needs to be created!")

print()
print("=" * 80)
print("✅ NEXT STEPS:")
print("=" * 80)
print()
print("1. Backup your working main.py and other important files")
print("2. Delete redundant files listed above")
print("3. Download the FINAL versions:")
print("   - main_window.py (with Watchlist)")
print("   - create_tab_modules.py (generates all 8 tabs)")
print("4. Run: python create_tab_modules.py")
print("5. Run: python test_new_ui.py")
print()