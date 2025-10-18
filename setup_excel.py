#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE AS: setup_excel.py (in tradingbot_new root directory)
# RUN: python setup_excel.py
# ==============================================================================
"""
Setup utility to find or create trades_log.xlsx file
"""

import os
import pandas as pd
from datetime import datetime

def find_excel_files():
    """Search for Excel files in current directory and subdirectories"""
    print("🔍 Searching for Excel files...")
    print()
    
    excel_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith(('.xlsx', '.xls')) and 'trade' in file.lower():
                full_path = os.path.join(root, file)
                excel_files.append(full_path)
    
    return excel_files

def create_sample_excel():
    """Create a sample trades_log.xlsx file with demo data"""
    print("📝 Creating sample trades_log.xlsx...")
    
    # Sample trade data
    sample_data = {
        'Date': [
            '2025-10-11 09:30:00',
            '2025-10-11 10:15:00',
            '2025-10-11 11:00:00',
            '2025-10-11 13:30:00',
            '2025-10-11 14:45:00',
            '2025-10-12 09:45:00',
            '2025-10-12 10:30:00',
            '2025-10-12 11:15:00',
            '2025-10-12 13:00:00',
            '2025-10-12 14:30:00',
            '2025-10-12 15:00:00',
            '2025-10-12 15:15:00'
        ],
        'Symbol': ['INFY', 'TCS', 'RELIANCE', 'HDFC', 'ICICI', 'SBIN', 'ITC', 'INFY', 'TCS', 'WIPRO', 'HCLT', 'TECHM'],
        'Type': ['BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY', 'BUY'],
        'Entry Price': [1500.00, 3650.00, 2850.00, 1680.00, 1320.00, 810.00, 425.00, 1505.00, 3655.00, 480.00, 1650.00, 1480.00],
        'Exit Price': [1508.50, 3645.00, 2862.00, 1685.50, 1325.00, 812.50, 426.50, 1510.00, 3660.00, 479.00, 1655.00, 1485.00],
        'Quantity': [10, 5, 6, 8, 10, 15, 20, 10, 5, 20, 10, 8],
        'P&L': [85.00, -25.00, 72.00, 44.00, 50.00, 37.50, 30.00, 50.00, 25.00, -20.00, 50.00, 40.00],
        'Status': ['CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED', 'CLOSED']
    }
    
    df = pd.DataFrame(sample_data)
    
    # Save to Excel
    filename = 'trades_log.xlsx'
    df.to_excel(filename, index=False)
    
    print(f"✅ Created {filename} with {len(df)} sample trades")
    print(f"📁 Location: {os.path.abspath(filename)}")
    print()
    
    # Show summary
    total_pnl = df['P&L'].sum()
    winning = len(df[df['P&L'] > 0])
    losing = len(df[df['P&L'] < 0])
    win_rate = (winning / len(df) * 100) if len(df) > 0 else 0
    
    print("📊 Sample Data Summary:")
    print(f"   Total Trades: {len(df)}")
    print(f"   Total P&L: ₹{total_pnl:.2f}")
    print(f"   Winning Trades: {winning}")
    print(f"   Losing Trades: {losing}")
    print(f"   Win Rate: {win_rate:.1f}%")
    print()
    
    return filename

def main():
    print("=" * 60)
    print("📊 Trades Log Excel Setup Utility")
    print("=" * 60)
    print()
    
    # Check current directory
    print(f"📁 Current Directory: {os.getcwd()}")
    print()
    
    # Find existing Excel files
    excel_files = find_excel_files()
    
    if excel_files:
        print(f"✅ Found {len(excel_files)} Excel file(s) with 'trade' in the name:")
        print()
        for i, file in enumerate(excel_files, 1):
            print(f"   {i}. {file}")
            # Check if it has the right structure
            try:
                df = pd.read_excel(file)
                print(f"      → {len(df)} rows, Columns: {list(df.columns)[:5]}...")
            except Exception as e:
                print(f"      → Error reading: {e}")
        print()
        
        # Ask if user wants to use existing or create new
        print("Options:")
        print("  1. Use one of the files above (copy/rename to trades_log.xlsx)")
        print("  2. Create a new sample trades_log.xlsx file")
        print()
        
    else:
        print("❌ No Excel files with 'trade' in the name found.")
        print()
        print("Creating a sample file...")
        print()
        create_sample_excel()
    
    # Always offer to create sample
    response = input("Create a NEW sample trades_log.xlsx? (y/n): ").strip().lower()
    if response == 'y':
        create_sample_excel()
    
    print()
    print("=" * 60)
    print("✅ Setup Complete!")
    print()
    print("Next steps:")
    print("  1. Make sure trades_log.xlsx is in: c:\\Users\\Dell\\tradingbot_new\\")
    print("  2. Run: python test_new_ui.py")
    print("=" * 60)

if __name__ == "__main__":
    main()