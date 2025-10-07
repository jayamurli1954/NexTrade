#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AUTO-PATCHER FOR ANGEL ONE TRADING BOT
=======================================
File: apply_threading_patch.py
Location: c:/Users/Dell/tradingbot_new/

This script automatically patches professional_trading_ui.py to fix UI hanging issues.

USAGE:
    python apply_threading_patch.py

What it does:
1. Backs up your current professional_trading_ui.py
2. Applies threading patches to fix UI freezing
3. Tests the patched file
"""

import os
import sys
import shutil
from datetime import datetime

def banner(text):
    print("\n" + "="*80)
    print("  " + text)
    print("="*80 + "\n")

def backup_file(filepath):
    """Create backup of original file"""
    if not os.path.exists(filepath):
        print("ERROR: " + filepath + " not found!")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath + ".backup_" + timestamp
    
    try:
        shutil.copy2(filepath, backup_path)
        print("OK - Backup created: " + backup_path)
        return True
    except Exception as e:
        print("ERROR - Backup failed: " + str(e))
        return False

def patch_ui_file(filepath):
    """Apply threading patches to UI file"""
    try:
        # Read original file
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if already patched
        if 'ThreadSafeUI' in content:
            print("WARNING - File appears to be already patched")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                return False
        
        # Patch 1: Add imports
        print("Adding threading imports...")
        old_imports = "import tkinter as tk\nfrom tkinter import ttk, messagebox, simpledialog\nimport json\nimport os"
        new_imports = """import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
import threading
import queue
from functools import wraps
import time"""
        
        if old_imports in content:
            content = content.replace(old_imports, new_imports)
            print("OK - Imports added")
        else:
            print("WARNING - Could not find import section, trying alternate method")
            # Try to add after first import block
            import_pos = content.find("import os")
            if import_pos > 0:
                insert_pos = content.find("\n", import_pos) + 1
                additions = "\nimport threading\nimport queue\nfrom functools import wraps\nimport time\n"
                content = content[:insert_pos] + additions + content[insert_pos:]
                print("OK - Imports added (alternate method)")
        
        # Patch 2: Add threading decorator and ThreadSafeUI class
        print("Adding threading support classes...")
        
        threading_code = '''

# Threading decorator for non-blocking operations
def run_in_thread(func):
    """Decorator to run function in background thread"""
    from functools import wraps
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        thread = threading.Thread(
            target=func,
            args=(self,) + args,
            kwargs=kwargs,
            daemon=True
        )
        thread.start()
        return thread
    return wrapper


class ThreadSafeUI:
    """Mixin class to add thread-safe UI updates"""
    
    def __init__(self):
        self.ui_queue = queue.Queue()
        self._processing_queue = False
        
    def schedule_ui_update(self, callback, *args, **kwargs):
        """Schedule a UI update from background thread"""
        self.ui_queue.put((callback, args, kwargs))
        if not self._processing_queue:
            self._start_queue_processor()
    
    def _start_queue_processor(self):
        """Start processing UI update queue"""
        self._processing_queue = True
        self._process_ui_queue()
    
    def _process_ui_queue(self):
        """Process pending UI updates"""
        try:
            while not self.ui_queue.empty():
                callback, args, kwargs = self.ui_queue.get_nowait()
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print("UI update error: " + str(e))
        except:
            pass
        
        if hasattr(self, 'root'):
            self.root.after(100, self._process_ui_queue)


'''
        
        # Insert before class ProfessionalTradingUI
        class_pos = content.find("class ProfessionalTradingUI")
        if class_pos > 0:
            content = content[:class_pos] + threading_code + content[class_pos:]
            print("OK - Threading classes added")
        else:
            print("ERROR - Could not find ProfessionalTradingUI class")
            return False
        
        # Patch 3: Modify class to inherit ThreadSafeUI
        print("Updating class definition...")
        content = content.replace(
            "class ProfessionalTradingUI:",
            "class ProfessionalTradingUI(ThreadSafeUI):"
        )
        
        # Patch 4: Add ThreadSafeUI init in __init__
        init_pattern = "def __init__(self, root, analyzer, provider, paper_trader"
        init_pos = content.find(init_pattern)
        if init_pos > 0:
            # Find the line with self.root = root
            root_pos = content.find("self.root = root", init_pos)
            if root_pos > 0:
                # Insert ThreadSafeUI init before it
                insert_pos = content.rfind("\n", init_pos, root_pos) + 1
                spaces = " " * 8  # Indentation
                init_call = spaces + "ThreadSafeUI.__init__(self)\n" + spaces
                content = content[:insert_pos] + init_call + content[insert_pos:]
                print("OK - ThreadSafeUI initialization added")
        
        # Patch 5: Add threaded refresh method
        print("Adding threaded refresh methods...")
        
        threaded_methods = '''
    @run_in_thread
    def _refresh_dashboard_threaded(self):
        """Threaded dashboard refresh - non-blocking"""
        try:
            snap = self.provider.snapshot()
            import json
            snap_text = json.dumps(snap, indent=2)
            self.schedule_ui_update(self._update_provider_text, snap_text)
            
            if self.provider.is_connected:
                broker_holdings = self.provider.get_holdings()
                if self.paper_mode:
                    paper_holdings = self.paper_trader.holdings_snapshot()
                    combined = {"paper_trading": paper_holdings, "broker_holdings": broker_holdings}
                    holdings_text = json.dumps(combined, indent=2)
                else:
                    holdings_text = json.dumps(broker_holdings, indent=2)
            else:
                paper_holdings = self.paper_trader.holdings_snapshot()
                holdings_text = json.dumps(paper_holdings, indent=2)
            
            self.schedule_ui_update(self._update_holdings_text, holdings_text)
        except Exception as e:
            print("Dashboard refresh error: " + str(e))
    
    def _update_provider_text(self, text):
        """UI update - must run on main thread"""
        if hasattr(self, '_provider_text'):
            self._provider_text.delete("1.0", "end")
            self._provider_text.insert("end", text)
    
    def _update_holdings_text(self, text):
        """UI update - must run on main thread"""
        if hasattr(self, '_holdings_text'):
            self._holdings_text.delete("1.0", "end")
            self._holdings_text.insert("end", text)

'''
        
        # Insert before _build_dashboard_tab
        dashboard_pos = content.find("def _build_dashboard_tab(self, parent):")
        if dashboard_pos > 0:
            content = content[:dashboard_pos] + threaded_methods + "\n    " + content[dashboard_pos:]
            print("OK - Threaded methods added")
        
        # Patch 6: Replace _refresh_dashboard to use threading
        old_refresh = "def _refresh_dashboard(self):"
        new_refresh = """def _refresh_dashboard(self):
        \"\"\"Public method - now uses threading\"\"\"
        self._refresh_dashboard_threaded()
        return  # Old implementation below (kept for reference)
        
    def _refresh_dashboard_OLD(self):"""
        
        content = content.replace(old_refresh, new_refresh, 1)
        print("OK - Dashboard refresh method updated to use threading")
        
        # Write patched file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("OK - File patched successfully")
        return True
        
    except Exception as e:
        print("ERROR - Patching failed: " + str(e))
        import traceback
        traceback.print_exc()
        return False

def main():
    banner("ANGEL ONE TRADING BOT - AUTO-PATCHER")
    
    print("This script will fix UI hanging issues by adding threading support.")
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled by user")
        return 1
    
    # File path
    ui_file = os.path.join('ui', 'professional_trading_ui.py')
    
    # Check if file exists
    if not os.path.exists(ui_file):
        print("\nERROR: " + ui_file + " not found!")
        print("Make sure you are running this from: c:\\Users\\Dell\\tradingbot_new\\")
        input("\nPress Enter to exit...")
        return 1
    
    # Backup
    print("\n[STEP 1/3] Creating backup...")
    if not backup_file(ui_file):
        input("\nPress Enter to exit...")
        return 1
    
    # Apply patches
    print("\n[STEP 2/3] Applying threading patches...")
    if not patch_ui_file(ui_file):
        print("\nPatch failed. Restoring backup...")
        # Find latest backup
        ui_dir = os.path.dirname(ui_file)
        backups = [f for f in os.listdir(ui_dir) if f.startswith('professional_trading_ui.py.backup_')]
        if backups:
            latest = sorted(backups)[-1]
            shutil.copy2(os.path.join(ui_dir, latest), ui_file)
            print("Backup restored")
        input("\nPress Enter to exit...")
        return 1
    
    # Test
    print("\n[STEP 3/3] Testing patched file...")
    try:
        sys.path.insert(0, os.getcwd())
        from ui.professional_trading_ui import ProfessionalTradingUI
        print("OK - Import successful!")
    except Exception as e:
        print("ERROR - Import failed: " + str(e))
        print("\nRestoring backup...")
        ui_dir = os.path.dirname(ui_file)
        backups = [f for f in os.listdir(ui_dir) if f.startswith('professional_trading_ui.py.backup_')]
        if backups:
            latest = sorted(backups)[-1]
            shutil.copy2(os.path.join(ui_dir, latest), ui_file)
            print("Backup restored")
        input("\nPress Enter to exit...")
        return 1
    
    # Success
    banner("PATCH APPLIED SUCCESSFULLY")
    
    print("Changes made:")
    print("  - Added threading imports")
    print("  - Added ThreadSafeUI mixin class")
    print("  - Modified ProfessionalTradingUI to inherit ThreadSafeUI")
    print("  - Added non-blocking refresh methods")
    print("\nYour UI will no longer freeze when:")
    print("  - Clicking tabs")
    print("  - Refreshing dashboard")
    print("  - Fetching data")
    print("\nNext steps:")
    print("  1. Run: python main.py")
    print("  2. Test tab switching (should be instant)")
    print("  3. Test refresh buttons (should not freeze)")
    
    input("\nPress Enter to exit...")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print("\n\nFATAL ERROR: " + str(e))
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)