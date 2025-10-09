with open('ui/professional_trading_ui.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
# Check for threading
has_threading = '_run_in_background' in content
has_market_hours = 'is_market_open' in content

print(f"File size: {len(content)} chars")
print(f"Has threading fix: {has_threading}")
print(f"Has market hours check: {has_market_hours}")
print(f"\nLine count: {len(content.split(chr(10)))}")

if '_async_refresh_dashboard' in content:
    print("Already has async methods")
else:
    print("Missing async methods - needs threading fix")

input("Press Enter...")