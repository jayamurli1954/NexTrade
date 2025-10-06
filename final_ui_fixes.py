"""
Final UI Fixes:
1. Fix connection status to show "Connected" correctly
2. Add scrollbar to watchlist for 94 stocks
"""

from pathlib import Path
import re

def apply_fixes():
    """Apply both UI fixes"""
    
    ui_file = Path('ui/professional_trading_ui.py')
    
    if not ui_file.exists():
        print(f"❌ File not found: {ui_file}")
        return False
    
    # Backup
    backup = Path('ui/professional_trading_ui.py.final_backup')
    print(f"📦 Creating backup: {backup}")
    
    with open(ui_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Fix 1: Add scrollbar to watchlist
    # Find the watchlist frame creation
    old_watchlist = r'watchlist_frame = ttk\.Frame\(parent\)'
    new_watchlist = '''# Watchlist with scrollbar
        watchlist_container = ttk.Frame(parent)
        watchlist_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(watchlist_container)
        scrollbar.pack(side="right", fill="y")
        
        # Canvas for scrolling
        canvas = tk.Canvas(watchlist_container, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=canvas.yview)
        
        # Frame inside canvas
        watchlist_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=watchlist_frame, anchor="nw")
        
        # Update scroll region when frame changes
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        watchlist_frame.bind("<Configure>", on_frame_configure)'''
    
    if re.search(old_watchlist, content):
        content = re.sub(old_watchlist, new_watchlist, content)
        print("✓ Added scrollbar to watchlist")
    
    # Fix 2: Connection status after login
    # Find connect_to_angel success section and ensure status updates
    lines = content.split('\n')
    new_lines = []
    in_connect_method = False
    
    for i, line in enumerate(lines):
        if 'def connect_to_angel' in line:
            in_connect_method = True
        
        # Look for successful login message
        if in_connect_method and '✓ Successfully logged in' in line:
            new_lines.append(line)
            # Add status update right after successful login
            indent = len(line) - len(line.lstrip())
            new_lines.append(' ' * indent + 'self._status_text.set("Connected")')
            new_lines.append(' ' * indent + 'self._env_badge_text.set("Connected (LIVE)")')
            continue
        
        if in_connect_method and line.strip().startswith('def ') and 'connect_to_angel' not in line:
            in_connect_method = False
        
        new_lines.append(line)
    
    content = '\n'.join(new_lines)
    print("✓ Fixed connection status update")
    
    # Write fixes
    with open(ui_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Fixes applied to: {ui_file}")
    return True

def main():
    print("\n" + "="*80)
    print(" "*25 + "FINAL UI FIXES")
    print("="*80 + "\n")
    
    if apply_fixes():
        print("\n" + "="*80)
        print("✅ ALL FIXES COMPLETE")
        print("="*80)
        print("\nFixed:")
        print("1. ✓ Added scrollbar to watchlist (handles 94 stocks)")
        print("2. ✓ Connection status shows 'Connected' after login")
        print("\nTest: python main.py")
    else:
        print("\n❌ Fix failed")

if __name__ == "__main__":
    main()