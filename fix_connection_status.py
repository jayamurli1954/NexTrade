"""
Automated Fix for Connection Status Display Issue
Fixes the UI to correctly show "Connected" status after successful login
"""

import re
from pathlib import Path

def fix_connection_status():
    """Fix the connection status display bug in professional_trading_ui.py"""
    
    ui_file = Path('ui/professional_trading_ui.py')
    
    if not ui_file.exists():
        print(f"❌ UI file not found: {ui_file}")
        return False
    
    # Backup original file
    backup_file = Path('ui/professional_trading_ui.py.backup')
    print(f"📦 Creating backup: {backup_file}")
    
    with open(ui_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Backup created")
    
    # Fix 1: Update _update_connection_status method
    old_method = r'''def _update_connection_status\(self, live: bool = False\):
        """Update connection status display"""
        try:
            if self\.data_provider and hasattr\(self\.data_provider, 'api'\):
                self\._env_badge_text\.set\(f"Disconnected \(\{'LIVE' if live else 'PAPER'\}\)"\)
            else:
                self\._env_badge_text\.set\(f"Disconnected \(\{'LIVE' if live else 'PAPER'\}\)"\)
        except Exception as e:
            print\(f"Status update error: \{e\}"\)'''
    
    new_method = '''def _update_connection_status(self, live: bool = False):
        """Update connection status display"""
        try:
            if self.data_provider and hasattr(self.data_provider, 'api'):
                # Check if actually connected
                if hasattr(self.data_provider, 'is_connected'):
                    if self.data_provider.is_connected():
                        self._env_badge_text.set(f"Connected ({'LIVE' if live else 'PAPER'})")
                        self._status_text.set("Connected")
                    else:
                        self._env_badge_text.set(f"Disconnected ({'LIVE' if live else 'PAPER'})")
                        self._status_text.set("Disconnected")
                else:
                    # If no is_connected method, assume connected if API exists
                    self._env_badge_text.set(f"Connected ({'LIVE' if live else 'PAPER'})")
                    self._status_text.set("Connected")
            else:
                self._env_badge_text.set(f"Disconnected ({'LIVE' if live else 'PAPER'})")
                self._status_text.set("Disconnected")
        except Exception as e:
            print(f"Status update error: {e}")'''
    
    if re.search(old_method, content, re.MULTILINE):
        content = re.sub(old_method, new_method, content, flags=re.MULTILINE)
        print("✓ Fixed _update_connection_status method")
    else:
        # Try simpler pattern match
        if 'def _update_connection_status(self, live: bool = False):' in content:
            # Find and replace the method
            lines = content.split('\n')
            new_lines = []
            in_method = False
            method_indent = None
            skip_until_next_def = False
            
            for line in lines:
                if 'def _update_connection_status(self, live: bool = False):' in line:
                    in_method = True
                    method_indent = len(line) - len(line.lstrip())
                    new_lines.extend(new_method.split('\n'))
                    skip_until_next_def = True
                    continue
                
                if skip_until_next_def:
                    # Check if we've reached the next method
                    if line.strip().startswith('def ') and not line.strip().startswith('def _update_connection_status'):
                        skip_until_next_def = False
                        in_method = False
                        new_lines.append(line)
                    elif line.strip() == '' or (len(line) - len(line.lstrip())) <= method_indent:
                        # Empty line or dedented line means end of method
                        if line.strip() and not line.strip().startswith('#'):
                            skip_until_next_def = False
                            in_method = False
                            new_lines.append(line)
                else:
                    new_lines.append(line)
            
            content = '\n'.join(new_lines)
            print("✓ Fixed _update_connection_status method (alternative approach)")
    
    # Fix 2: Remove the incorrect "Disconnected" line in connect_to_angel method
    # Find and comment out line 833: self._status_text.set("Disconnected")
    lines = content.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines, 1):
        if 'self._status_text.set("Disconnected")' in line and 'connect_to_angel' in content[max(0, content[:content.find(line)].rfind('def ')):content.find(line)]:
            # Comment out this line
            indent = len(line) - len(line.lstrip())
            fixed_lines.append(' ' * indent + '# ' + line.lstrip() + '  # Fixed: Was incorrectly setting to Disconnected after login')
            print(f"✓ Commented out incorrect Disconnected status on line {i}")
        else:
            fixed_lines.append(line)
    
    content = '\n'.join(fixed_lines)
    
    # Write fixed content
    with open(ui_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Connection status fix applied to: {ui_file}")
    print(f"📦 Original backed up to: {backup_file}")
    
    return True

def main():
    """Main execution"""
    print("\n" + "="*80)
    print(" "*20 + "CONNECTION STATUS FIX UTILITY")
    print("="*80 + "\n")
    
    print("This script will fix the connection status display issue where")
    print("the UI shows 'Disconnected' even after successful login.\n")
    
    if fix_connection_status():
        print("\n" + "="*80)
        print("✅ FIX COMPLETE")
        print("="*80)
        print("\nNext steps:")
        print("1. Test the bot: python main.py")
        print("2. Click 'Connect' and verify status shows 'Connected'")
        print("3. If issues occur, restore backup: copy ui\\professional_trading_ui.py.backup ui\\professional_trading_ui.py")
    else:
        print("\n❌ Fix failed - please check error messages above")

if __name__ == "__main__":
    main()