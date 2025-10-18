"""
Diagnostic script to check what's actually in the Angel One data
"""
import json
import requests

url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

print("Downloading Angel One data to analyze format...")
response = requests.get(url, timeout=30)
instruments = response.json()

print(f"\nTotal instruments: {len(instruments)}")

# Find RELIANCE in the data
print("\n" + "="*70)
print("Searching for RELIANCE in Angel One data:")
print("="*70)

reliance_found = []
for inst in instruments:
    if 'RELIANCE' in inst.get('symbol', '').upper() and inst.get('exch_seg') == 'NSE':
        reliance_found.append(inst)

print(f"\nFound {len(reliance_found)} RELIANCE entries:")
for i, inst in enumerate(reliance_found[:5], 1):  # Show first 5
    print(f"\n{i}. Symbol: {inst.get('symbol')}")
    print(f"   Name: {inst.get('name')}")
    print(f"   Token: {inst.get('token')}")
    print(f"   Exchange: {inst.get('exch_seg')}")
    print(f"   Instrument: {inst.get('instrumenttype')}")

# Check the actual structure
print("\n" + "="*70)
print("Sample instrument structure:")
print("="*70)
if instruments:
    print(json.dumps(instruments[0], indent=2))

# Look for equity stocks specifically
print("\n" + "="*70)
print("Looking for equity stocks in NSE:")
print("="*70)

watchlist = ['RELIANCE', 'INFY', 'TCS', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'CASTROLIND', 'BPCL']

for stock in watchlist:
    found = False
    for inst in instruments:
        symbol = inst.get('symbol', '')
        if stock in symbol and inst.get('exch_seg') == 'NSE':
            print(f"\n{stock}:")
            print(f"  Full symbol: {symbol}")
            print(f"  Token: {inst.get('token')}")
            print(f"  Instrument type: {inst.get('instrumenttype')}")
            found = True
            break
    
    if not found:
        print(f"\n{stock}: NOT FOUND")