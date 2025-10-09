#!/usr/bin/env python3
"""
Backup Script - Angel One Trading Bot
Creates timestamped backups before applying critical fixes
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

def create_backup():
    """Create timestamped backups of files to be modified"""
    
    # Get current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Define base path
    base_path = Path(r"c:\Users\Dell\tradingbot_new")
    
    # Files to backup
    files_to_backup = [
        "order_manager/paper_trader.py",
        "ui/professional_trading_ui.py"
    ]
    
    print("=" * 70)
    print("BACKUP SCRIPT - Critical Fixes Phase 1")
    print("=" * 70)
    print(f"\nTimestamp: {timestamp}")
    print(f"Base Path: {base_path}")
    print(f"\nFiles to backup: {len(files_to_backup)}")
    print()
    
    backup_count = 0
    
    for file_path in files_to_backup:
        source = base_path / file_path
        
        # Create backup filename
        backup_name = f"{source.name}.backup_{timestamp}"
        backup_path = source.parent / backup_name
        
        # Check if source exists
        if not source.exists():
            print(f"⚠️  SKIP: {file_path} (file not found)")
            continue
        
        # Create backup
        try:
            shutil.copy2(source, backup_path)
            file_size = source.stat().st_size / 1024  # KB
            print(f"✅ BACKED UP: {file_path}")
            print(f"   → {backup_name} ({file_size:.1f} KB)")
            backup_count += 1
        except Exception as e:
            print(f"❌ FAILED: {file_path}")
            print(f"   Error: {str(e)}")
    
    print()
    print("=" * 70)
    print(f"Backup Summary: {backup_count}/{len(files_to_backup)} files backed up")
    print("=" * 70)
    print()
    
    if backup_count == len(files_to_backup):
        print("✅ ALL FILES BACKED UP SUCCESSFULLY!")
        print("\nYou can now safely apply the critical fixes.")
        print("\nTo restore a backup later:")
        print(f"   copy <file>.backup_{timestamp} <file>")
        return True
    else:
        print("⚠️  SOME BACKUPS FAILED - Review errors above")
        return False

if __name__ == "__main__":
    try:
        success = create_backup()
        input("\nPress ENTER to close...")
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ BACKUP SCRIPT ERROR: {str(e)}")
        input("\nPress ENTER to close...")
        exit(1)