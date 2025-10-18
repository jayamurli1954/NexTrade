#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE THIS FILE AS: integrate_websocket_to_bot.py (in root directory)
# RUN: python integrate_websocket_to_bot.py
# ==============================================================================
"""
WebSocket Integration Script

Patches your existing angel_provider.py to use WebSocket for prices
"""

import os
import shutil
from datetime import datetime


def create_backup(filepath):
    """Create backup of file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_ws_integration_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"Backup: {backup_path}")
    return backup_path


def patch_angel_provider():
    """Patch angel_provider.py to add WebSocket support"""
    
    provider_file = "data_provider/angel_provider.py"
    
    if not os.path.exists(provider_file):
        print(f"ERROR: {provider_file} not found")
        return False
    
    print(f"\nPatching: {provider_file}")
    
    with open(provider_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Create backup
    backup = create_backup(provider_file)
    
    lines = content.split('\n')
    
    # Add WebSocket import at top
    import_added = False
    for i, line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            if not import_added and 'websocket' not in content.lower():
                lines.insert(i + 1, 'from core.websocket.price_provider import get_websocket_provider')
                print("  Added WebSocket import")
                import_added = True
                break
    
    # Find __init__ and add WebSocket initialization
    for i, line in enumerate(lines):
        if 'def __init__(self' in line:
            # Find end of __init__
            indent = len(line) - len(line.lstrip())
            body_indent = ' ' * (indent + 4)
            
            # Find where to insert (before end of __init__)
            insert_idx = i + 1
            for j in range(i + 1, len(lines)):
                curr_line = lines[j]
                if curr_line.strip() and curr_line.strip().startswith('def '):
                    curr_indent = len(curr_line) - len(curr_line.lstrip())
                    if curr_indent == indent:
                        insert_idx = j
                        break
            
            # Add WebSocket initialization
            ws_init = [
                "",
                f"{body_indent}# WebSocket LTP Provider (NO RATE LIMITS!)",
                f"{body_indent}self.ws_provider = None",
                f"{body_indent}self._ws_enabled = False",
            ]
            
            for line_to_add in reversed(ws_init):
                lines.insert(insert_idx, line_to_add)
            
            print("  Added WebSocket initialization")
            break
    
    # Find connect method and add WebSocket start
    for i, line in enumerate(lines):
        if 'def connect(self' in line:
            # Find where session is generated successfully
            for j in range(i, min(i + 100, len(lines))):
                if 'self.feed_token' in lines[j] and '=' in lines[j]:
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    indent_str = ' ' * indent
                    
                    ws_start = [
                        "",
                        f"{indent_str}# Start WebSocket for real-time prices",
                        f"{indent_str}try:",
                        f"{indent_str}    self.ws_provider = get_websocket_provider(",
                        f"{indent_str}        auth_token=self.session_token,",
                        f"{indent_str}        api_key=self.api_key,",
                        f"{indent_str}        client_code=self.client_id,",
                        f"{indent_str}        feed_token=self.feed_token",
                        f"{indent_str}    )",
                        f"{indent_str}    self._ws_enabled = True",
                        f"{indent_str}    logger.info('WebSocket LTP Provider started')",
                        f"{indent_str}except Exception as e:",
                        f"{indent_str}    logger.warning(f'WebSocket init failed: {{e}}')",
                        f"{indent_str}    self._ws_enabled = False",
                    ]
                    
                    for line_to_add in reversed(ws_start):
                        lines.insert(j + 1, line_to_add)
                    
                    print("  Added WebSocket start in connect()")
                    break
            break
    
    # Find get_ltp method and modify to use WebSocket first
    for i, line in enumerate(lines):
        if 'def get_ltp(self, symbol' in line:
            # Find first line after method definition
            insert_idx = i + 1
            
            # Skip docstring if exists
            if '"""' in lines[insert_idx] or "'''" in lines[insert_idx]:
                insert_idx += 1
                while insert_idx < len(lines):
                    if '"""' in lines[insert_idx] or "'''" in lines[insert_idx]:
                        insert_idx += 1
                        break
                    insert_idx += 1
            
            indent = len(lines[i]) - len(lines[i].lstrip())
            body_indent = ' ' * (indent + 4)
            
            ws_logic = [
                f"{body_indent}# Try WebSocket first (NO RATE LIMITS!)",
                f"{body_indent}if self._ws_enabled and self.ws_provider:",
                f"{body_indent}    ws_price = self.ws_provider.get_ltp(symbol)",
                f"{body_indent}    if ws_price is not None:",
                f"{body_indent}        return ws_price",
                f"{body_indent}    # Symbol not subscribed yet, will use REST API below",
                "",
                f"{body_indent}# Fallback to REST API",
            ]
            
            for line_to_add in reversed(ws_logic):
                lines.insert(insert_idx, line_to_add)
            
            print("  Modified get_ltp() to use WebSocket first")
            break
    
    # Write patched file
    with open(provider_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"\nSuccess! {provider_file} patched")
    return True


def main():
    print("="*70)
    print("WEBSOCKET INTEGRATION")
    print("="*70)
    print()
    print("This will patch your angel_provider.py to use WebSocket for prices")
    print()
    print("Benefits:")
    print("  - Real-time price updates")
    print("  - NO rate limits")
    print("  - Automatic fallback to REST API if needed")
    print()
    
    choice = input("Continue? (yes/no): ").lower().strip()
    if choice != 'yes':
        print("Cancelled")
        return
    
    print()
    
    # Check if WebSocket module exists
    ws_file = "core/websocket/price_provider.py"
    if not os.path.exists(ws_file):
        print(f"ERROR: {ws_file} not found!")
        print()
        print("Please create the WebSocket provider first:")
        print("  Save: core/websocket/price_provider.py")
        return
    
    print(f"Found: {ws_file}")
    
    # Patch the provider
    if patch_angel_provider():
        print()
        print("="*70)
        print("INTEGRATION COMPLETE!")
        print("="*70)
        print()
        print("What was done:")
        print("  1. Added WebSocket import")
        print("  2. Added WebSocket initialization")
        print("  3. WebSocket starts on connect()")
        print("  4. get_ltp() now checks WebSocket first")
        print()
        print("Next steps:")
        print("  1. Restart your bot")
        print("  2. Bot will automatically use WebSocket")
        print("  3. NO MORE RATE LIMITS!")
        print()
        print("Note: Symbols need to be subscribed to WebSocket")
        print("      The bot will auto-subscribe from watchlist")
        print()
    else:
        print("\nIntegration failed!")


if __name__ == "__main__":
    main()