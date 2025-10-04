"""
Download Angel One Instrument Tokens - FIXED VERSION
Creates proper token mapping that works with your bot
"""

import requests
import json
import os

def download_angel_tokens():
    """Download Angel One instrument master and create token mapping"""
    print("="*70)
    print(" ANGEL ONE TOKEN DOWNLOADER - FIXED VERSION")
    print("="*70)
    print("\nDownloading instrument master from Angel One...")
    
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        instruments = response.json()
        print(f"✓ Downloaded {len(instruments)} instruments")
        
        # FIXED: Create proper token mapping for ALL exchanges
        token_map = {}
        nse_count = 0
        bse_count = 0
        
        for instrument in instruments:
            exch_seg = instrument.get('exch_seg', '')
            symbol = instrument.get('symbol')
            token = instrument.get('token')
            
            if symbol and token:
                # Store with exchange prefix - BOTH full and clean symbol
                key_full = f"{exch_seg}:{symbol}"
                token_map[key_full] = str(token)
                
                # CRITICAL FIX: Also store without -EQ suffix for easy lookup
                if symbol.endswith('-EQ'):
                    clean_symbol = symbol.replace('-EQ', '')
                    key_clean = f"{exch_seg}:{clean_symbol}"
                    token_map[key_clean] = str(token)
                
                if exch_seg == 'NSE':
                    nse_count += 1
                elif exch_seg == 'BSE':
                    bse_count += 1
        
        # Create data directory if it doesn't exist
        os.makedirs('data', exist_ok=True)
        
        # Save the full token mapping
        output_file = 'data/angel_tokens_map.json'
        with open(output_file, 'w') as f:
            json.dump(token_map, f, indent=2)
        
        print(f"\n✓ Token mapping saved to: {output_file}")
        print(f"✓ Total NSE tokens: {nse_count}")
        print(f"✓ Total BSE tokens: {bse_count}")
        print(f"✓ Total tokens: {len(token_map)}")
        
        # Verify the tokens are accessible
        print("\n" + "="*70)
        print(" VERIFICATION - Sample Tokens from Your Watchlist:")
        print("="*70)
        
        # Check tokens for stocks in your watchlist
        watchlist_stocks = [
            'RELIANCE', 'INFY', 'TCS', 'HDFCBANK', 'ICICIBANK', 
            'SBIN', 'CASTROLIND', 'BPCL'
        ]
        
        print(f"\n{'Symbol':<15} {'Exchange':<10} {'Token':<15} {'Status'}")
        print("-" * 60)
        
        for sym in watchlist_stocks:
            nse_key = f"NSE:{sym}"
            if nse_key in token_map:
                print(f"{sym:<15} {'NSE':<10} {token_map[nse_key]:<15} ✓ Found")
            else:
                print(f"{sym:<15} {'NSE':<10} {'N/A':<15} ✗ Missing")
        
        print("\n" + "="*70)
        print(" ✓ DOWNLOAD COMPLETE!")
        print("="*70)
        print("\nYour bot is now ready to fetch LIVE prices from Angel One!")
        print("Run 'python main.py' to start trading.")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Network Error: {e}")
        print("\nCreating fallback token file with your watchlist stocks...")
        
        # FIXED: Fallback tokens for your specific watchlist
        fallback_tokens = {
            "NSE:RELIANCE": "2885",
            "NSE:INFY": "1594",
            "NSE:TCS": "11536",
            "NSE:HDFCBANK": "1333",
            "NSE:ICICIBANK": "4963",
            "NSE:SBIN": "3045",
            "NSE:CASTROLIND": "1250",
            "NSE:BPCL": "526",
            "NSE:ITC": "1660",
            "NSE:BHARTIARTL": "10604",
            "NSE:HINDUNILVR": "1394",
            "NSE:LT": "11483"
        }
        
        os.makedirs('data', exist_ok=True)
        output_file = 'data/angel_tokens_map.json'
        
        with open(output_file, 'w') as f:
            json.dump(fallback_tokens, f, indent=2)
        
        print(f"✓ Created fallback token file: {output_file}")
        print(f"✓ Loaded {len(fallback_tokens)} tokens for your watchlist")
        print("\n⚠ Note: Limited to watchlist stocks. Try downloading again when online.")
        
        return False
    
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_token_file():
    """Verify the token file exists and is valid"""
    token_file = 'data/angel_tokens_map.json'
    
    if not os.path.exists(token_file):
        print(f"\n✗ Token file not found: {token_file}")
        print("Run 'python download_tokens.py' first!")
        return False
    
    try:
        with open(token_file, 'r') as f:
            tokens = json.load(f)
        
        print(f"\n✓ Token file verified: {len(tokens)} tokens loaded")
        
        # Check for watchlist stocks
        watchlist = ['RELIANCE', 'INFY', 'TCS', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'CASTROLIND', 'BPCL']
        found = 0
        
        for stock in watchlist:
            if f"NSE:{stock}" in tokens:
                found += 1
        
        print(f"✓ Found {found}/{len(watchlist)} watchlist stocks in token file")
        return True
        
    except Exception as e:
        print(f"\n✗ Error reading token file: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print(" STARTING TOKEN DOWNLOAD...")
    print("="*70 + "\n")
    
    success = download_angel_tokens()
    
    if success:
        print("\n" + "="*70)
        print(" VERIFYING TOKEN FILE...")
        print("="*70)
        verify_token_file()
    
    print("\n" + "="*70)
    print(" SETUP COMPLETE!")
    print("="*70)