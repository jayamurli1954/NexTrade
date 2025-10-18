#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cleanup and Backup Script
File: cleanup_and_backup.py

Prepares for weekend rebuild:
1. Creates full backup
2. Identifies and removes redundant files
3. Organizes file structure
"""

import os
import shutil
import json
from datetime import datetime
from pathlib import Path


def create_full_backup():
    """Create complete backup before cleanup"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"BACKUP_BEFORE_REBUILD_{timestamp}"
    
    print("="*70)
    print("CREATING FULL BACKUP")
    print("="*70)
    print()
    print(f"📦 Backup location: {backup_dir}")
    print()
    
    # Create backup directory
    os.makedirs(backup_dir, exist_ok=True)
    
    # Directories to backup
    dirs_to_backup = [
        'ui',
        'analyzer',
        'data_provider',
        'order_manager',
        'config',
        'data',
        'logs'
    ]
    
    files_to_backup = [
        'main.py',
        'trade_logger.py',
        'console_handler.py'
    ]
    
    # Backup directories
    for dir_name in dirs_to_backup:
        if os.path.exists(dir_name):
            dest = os.path.join(backup_dir, dir_name)
            shutil.copytree(dir_name, dest)
            print(f"✅ Backed up: {dir_name}/")
    
    # Backup files
    for file_name in files_to_backup:
        if os.path.exists(file_name):
            shutil.copy2(file_name, backup_dir)
            print(f"✅ Backed up: {file_name}")
    
    print()
    print(f"✅ Full backup created: {backup_dir}")
    print()
    
    return backup_dir


def identify_redundant_files():
    """Identify files that can be safely removed"""
    
    print("="*70)
    print("IDENTIFYING REDUNDANT FILES")
    print("="*70)
    print()
    
    redundant = {
        'backup_files': [],
        'fix_scripts': [],
        'diagnostic_scripts': [],
        'temp_files': [],
    }
    
    # Find all files in current directory
    for item in os.listdir('.'):
        if os.path.isfile(item):
            # Backup files
            if '.backup_' in item or item.startswith('backup_'):
                redundant['backup_files'].append(item)
            
            # Fix/patch scripts
            elif item.startswith('fix_') and item.endswith('.py'):
                redundant['fix_scripts'].append(item)
            
            # Diagnostic scripts
            elif item.startswith('diagnose_') and item.endswith('.py'):
                redundant['diagnostic_scripts'].append(item)
            
            # Temp/test files
            elif any(x in item.lower() for x in ['test_', 'temp_', 'old_', 'deprecated_']):
                redundant['temp_files'].append(item)
    
    # Check UI directory for backups
    if os.path.exists('ui'):
        for item in os.listdir('ui'):
            if '.backup_' in item:
                redundant['backup_files'].append(f"ui/{item}")
    
    # Check analyzer directory for backups
    if os.path.exists('analyzer'):
        for item in os.listdir('analyzer'):
            if '.backup_' in item:
                redundant['backup_files'].append(f"analyzer/{item}")
    
    # Check data_provider directory for backups
    if os.path.exists('data_provider'):
        for item in os.listdir('data_provider'):
            if '.backup_' in item:
                redundant['backup_files'].append(f"data_provider/{item}")
    
    # Print summary
    total = sum(len(files) for files in redundant.values())
    
    print(f"📊 Found {total} redundant files:")
    print()
    
    for category, files in redundant.items():
        if files:
            print(f"  {category.replace('_', ' ').title()}: {len(files)}")
            for f in files[:5]:  # Show first 5
                print(f"    • {f}")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more")
            print()
    
    return redundant


def cleanup_redundant_files(redundant_files, backup_dir):
    """Move redundant files to backup directory"""
    
    print("="*70)
    print("CLEANING UP REDUNDANT FILES")
    print("="*70)
    print()
    
    redundant_backup = os.path.join(backup_dir, "redundant_files")
    os.makedirs(redundant_backup, exist_ok=True)
    
    removed_count = 0
    
    for category, files in redundant_files.items():
        if not files:
            continue
        
        category_dir = os.path.join(redundant_backup, category)
        os.makedirs(category_dir, exist_ok=True)
        
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    # Move to backup
                    dest = os.path.join(category_dir, os.path.basename(file_path))
                    shutil.move(file_path, dest)
                    removed_count += 1
                    
            except Exception as e:
                print(f"  ⚠️  Could not move {file_path}: {e}")
    
    print(f"✅ Moved {removed_count} redundant files to backup")
    print()


def create_new_structure():
    """Create clean directory structure for new system"""
    
    print("="*70)
    print("CREATING NEW STRUCTURE")
    print("="*70)
    print()
    
    new_dirs = [
        'core',           # Core trading logic
        'core/websocket', # WebSocket provider
        'ui_new',         # New modular UI
        'ui_new/tabs',    # UI tabs
        'workers',        # Background workers
        'logs/cumulative' # Cumulative logs
    ]
    
    for dir_path in new_dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"✅ Created: {dir_path}/")
    
    print()


def save_cleanup_report(backup_dir, redundant_files):
    """Save cleanup report"""
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'backup_location': backup_dir,
        'files_removed': sum(len(files) for files in redundant_files.values()),
        'categories': {k: len(v) for k, v in redundant_files.items()},
        'next_steps': [
            'Weekend rebuild starting',
            'New modular architecture',
            'Cumulative tracking system',
            'WebSocket integration',
            'Ready for Monday'
        ]
    }
    
    report_file = os.path.join(backup_dir, 'cleanup_report.json')
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"📄 Cleanup report saved: {report_file}")


def main():
    print()
    print("="*70)
    print("WEEKEND REBUILD - PREPARATION")
    print("="*70)
    print()
    print("This script will:")
    print("  1. Create full backup of current system")
    print("  2. Identify redundant files (backups, old fixes, etc.)")
    print("  3. Clean up and organize")
    print("  4. Prepare for new modular system")
    print()
    print("⚠️  Your current bot will be backed up safely")
    print("✅ You can restore anytime if needed")
    print()
    
    choice = input("Ready to proceed? (yes/no): ").lower().strip()
    
    if choice != 'yes':
        print("\nCancelled. No changes made.")
        return 1
    
    print()
    
    # Step 1: Full backup
    backup_dir = create_full_backup()
    
    # Step 2: Identify redundant files
    redundant_files = identify_redundant_files()
    
    # Step 3: Confirm cleanup
    print("="*70)
    print("CLEANUP CONFIRMATION")
    print("="*70)
    print()
    print(f"Found {sum(len(f) for f in redundant_files.values())} redundant files")
    print()
    print("These files will be MOVED (not deleted) to:")
    print(f"  {backup_dir}/redundant_files/")
    print()
    
    confirm = input("Proceed with cleanup? (yes/no): ").lower().strip()
    
    if confirm != 'yes':
        print("\nCleanup skipped. Backup created only.")
        return 0
    
    print()
    
    # Step 4: Cleanup
    cleanup_redundant_files(redundant_files, backup_dir)
    
    # Step 5: Create new structure
    create_new_structure()
    
    # Step 6: Save report
    save_cleanup_report(backup_dir, redundant_files)
    
    print()
    print("="*70)
    print("✅ PREPARATION COMPLETE!")
    print("="*70)
    print()
    print("📦 Summary:")
    print(f"   • Full backup: {backup_dir}/")
    print(f"   • Redundant files moved: {sum(len(f) for f in redundant_files.values())}")
    print(f"   • New structure created")
    print()
    print("📋 What's backed up:")
    print("   • All UI files")
    print("   • All analyzer files")
    print("   • All provider files")
    print("   • All config and data")
    print("   • Everything is safe!")
    print()
    print("🗂️  New directories created:")
    print("   • core/ - Core trading logic")
    print("   • core/websocket/ - WebSocket provider")
    print("   • ui_new/ - New modular UI")
    print("   • ui_new/tabs/ - Individual tab modules")
    print("   • workers/ - Background workers")
    print("   • logs/cumulative/ - Cumulative tracking")
    print()
    print("🚀 Next Steps:")
    print("   1. Phase 1: Build cumulative trading system")
    print("   2. Phase 2: Build WebSocket provider")
    print("   3. Phase 3: Build new modular UI")
    print("   4. Phase 4: Testing and polish")
    print("   5. Monday: Go live with professional bot!")
    print()
    print(f"📄 Detailed report: {backup_dir}/cleanup_report.json")
    print()
    input("Press ENTER to exit...")
    return 0


if __name__ == "__main__":
    import sys
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress ENTER to exit...")
        sys.exit(1)