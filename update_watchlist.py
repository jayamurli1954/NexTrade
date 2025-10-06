"""
Stock Symbol Mapper for Angel One Watchlist
Uses comprehensive manual mapping database for accurate matching
"""

import pandas as pd
import json
from pathlib import Path

# Comprehensive mapping database for major Indian stocks
STOCK_SYMBOL_MAP = {
    'ABB INDIA': 'ABB',
    'ADANI ENTERPRISES': 'ADANIENT',
    'ADANI GREEN ENERGY': 'ADANIGREEN',
    'ADANI PORTS & SEZ': 'ADANIPORTS',
    'ADANI POWER': 'ADANIPOWER',
    'ADANI TOTAL GAS': 'ATGL',
    'AMBUJA CEMENT': 'AMBUJACEM',
    'APOLLO HOSPITALS': 'APOLLOHOSP',
    'ASIAN PAINTS': 'ASIANPAINT',
    'AVENUE SUPERMARTS': 'DMART',
    'AXIS BANK': 'AXISBANK',
    'BAJAJ AUTO': 'BAJAJ-AUTO',
    'BAJAJ FINANCE': 'BAJFINANCE',
    'BAJAJ FINSERV': 'BAJAJFINSV',
    'BAJAJ HOLDINGS & INVESTMENT': 'BAJAJHLDNG',
    'BANK OF BARODA': 'BANKBARODA',
    'BHARAT ELECTRONICS': 'BEL',
    'BHARTI AIRTEL': 'BHARTIARTL',
    'BHEL': 'BHEL',
    'BOSCH': 'BOSCHLTD',
    'BPCL': 'BPCL',
    'BRITANNIA': 'BRITANNIA',
    'CANARA BANK': 'CANBK',
    'CHOLAMANDALAM INVEST': 'CHOLAFIN',
    'CIPLA': 'CIPLA',
    'COAL INDIA': 'COALINDIA',
    'DABUR': 'DABUR',
    'DIVIS LABORATORIES': 'DIVISLAB',
    'DLF': 'DLF',
    'DR. REDDYS LAB': 'DRREDDY',
    'EICHER MOTORS': 'EICHERMOT',
    'ETERNAL LTD': 'ETERNALLTD',
    'GAIL': 'GAIL',
    'GODREJ CONSUMER': 'GODREJCP',
    'GRASIM': 'GRASIM',
    'HAVELLS INDIA': 'HAVELLS',
    'HCL TECHNOLOGIES': 'HCLTECH',
    'HDFC BANK': 'HDFCBANK',
    'HDFC LIFE INSURANCE': 'HDFCLIFE',
    'HERO MOTOCORP': 'HEROMOTOCO',
    'HINDALCO': 'HINDALCO',
    'HINDUSTAN AERO.': 'HAL',
    'HINDUSTAN UNILEVER': 'HINDUNILVR',
    'ICICI BANK': 'ICICIBANK',
    'ICICI LOMBARD GENERAL INSURANCE': 'ICICIGI',
    'ICICI PRUDENTIAL LIFE INSURANCE': 'ICICIPRULI',
    'INDUSIND BANK': 'INDUSINDBK',
    'INFO EDGE': 'NAUKRI',
    'INFOSYS': 'INFY',
    'INTERGLOBE AVIATION (INDIGO)': 'INDIGO',
    'IOC': 'IOC',
    'IRCTC': 'IRCTC',
    'IRFC': 'IRFC',
    'ITC': 'ITC',
    'JINDAL STEEL & POWER': 'JINDALSTEL',
    'JSW ENERGY': 'JSWENERGY',
    'JSW STEEL': 'JSWSTEEL',
    'KOTAK MAHINDRA BANK': 'KOTAKBANK',
    'L&T': 'LT',
    'LIFE INSURANCE CORPORATION': 'LICI',
    'M&M': 'M&M',
    'MACROTECH DEVELOPERS': 'LODHA',
    'MARUTI SUZUKI': 'MARUTI',
    'NESTLE': 'NESTLEIND',
    'NHPC': 'NHPC',
    'NTPC': 'NTPC',
    'ONGC': 'ONGC',
    'PIDILITE INDUSTRIES': 'PIDILITIND',
    'PNB': 'PNB',
    'POWER FINANCE CORPORATION': 'PFC',
    'POWER GRID': 'POWERGRID',
    'REC': 'RECLTD',
    'RELIANCE IND.': 'RELIANCE',
    'SAMVARDHANA MOTHERSON': 'MOTHERSON',
    'SBI': 'SBIN',
    'SBI LIFE INSURANCE': 'SBILIFE',
    'SHREE CEMENT': 'SHREECEM',
    'SIEMENS': 'SIEMENS',
    'SUN PHARMA': 'SUNPHARMA',
    'TATA CONSUMER': 'TATACONSUM',
    'TATA MOTORS': 'TATAMOTORS',
    'TATA POWER': 'TATAPOWER',
    'TATA STEEL': 'TATASTEEL',
    'TCS': 'TCS',
    'TECH MAHINDRA': 'TECHM',
    'TITAN': 'TITAN',
    'TORRENT PHARMA': 'TORNTPHARM',
    'TRENT': 'TRENT',
    'TVS MOTORS': 'TVSMOTOR',
    'ULTRATECH CEMENT': 'ULTRACEMCO',
    'UNION BANK': 'UNIONBANK',
    'VARUN BEVERAGES': 'VBL',
    'VEDANTA': 'VEDL',
    'WIPRO': 'WIPRO'
}

def load_angel_tokens():
    """Load Angel One tokens from available file"""
    token_file = Path('data/angel_tokens_map.json')
    
    if not token_file.exists():
        print(f"Warning: {token_file} not found")
        return {}
    
    with open(token_file, 'r') as f:
        tokens = json.load(f)
    
    print(f"✓ Loaded {len(tokens)} tokens from Angel One")
    return tokens

def get_token_for_symbol(symbol, tokens):
    """Get token for a trading symbol"""
    # Try different formats
    formats = [
        f'NSE:{symbol}-EQ',
        f'NSE:{symbol}',
        f'{symbol}-EQ',
        symbol
    ]
    
    for fmt in formats:
        if fmt in tokens:
            return tokens[fmt]
    
    return None

def main():
    """Main function"""
    
    print("\n" + "="*80)
    print(" "*20 + "STOCK WATCHLIST CREATOR v2.0")
    print("="*80 + "\n")
    
    # 1. Load stock list from Excel
    excel_file = Path('stock_list.xlsx')
    if not excel_file.exists():
        print(f"❌ Excel file not found: {excel_file}")
        return
    
    print(f"📂 Reading stock list from: {excel_file}")
    
    # Read Excel
    df = pd.read_excel(excel_file, header=None)
    
    # Extract all stock names
    all_stocks = []
    for col in df.columns:
        stocks = df[col].dropna().astype(str).tolist()
        all_stocks.extend(stocks)
    
    # Remove duplicates
    unique_stocks = sorted(set([s.strip().upper() for s in all_stocks if s.strip()]))
    
    print(f"✓ Found {len(all_stocks)} stock entries")
    print(f"✓ Unique stocks: {len(unique_stocks)}")
    
    # 2. Load Angel One tokens
    angel_tokens = load_angel_tokens()
    
    # 3. Match stocks using manual mapping
    print("\n📊 Matching stocks using symbol database...\n")
    
    matched_stocks = []
    unmatched_stocks = []
    
    for stock in unique_stocks:
        if stock in STOCK_SYMBOL_MAP:
            symbol = STOCK_SYMBOL_MAP[stock]
            token = get_token_for_symbol(symbol, angel_tokens) if angel_tokens else None
            
            matched_stocks.append({
                'input_name': stock,
                'symbol': symbol,
                'token': token or 'UNKNOWN',
                'exchange': 'NSE'
            })
            
            status = f"✓ {stock:40s} → {symbol}"
            if token:
                status += f" (Token: {token})"
            print(status)
        else:
            unmatched_stocks.append(stock)
            print(f"✗ {stock:40s} → NOT IN DATABASE")
    
    # 4. Summary
    print("\n" + "="*80)
    print("MATCHING SUMMARY")
    print("="*80)
    print(f"Total stocks:        {len(unique_stocks)}")
    print(f"Matched:             {len(matched_stocks)} ({len(matched_stocks)/len(unique_stocks)*100:.1f}%)")
    print(f"Not matched:         {len(unmatched_stocks)} ({len(unmatched_stocks)/len(unique_stocks)*100:.1f}%)")
    
    # 5. Create watchlist
    watchlist = []
    for stock in matched_stocks:
        watchlist.append({
            'symbol': stock['symbol'],
            'token': stock['token'],
            'exchange': stock['exchange'],
            'name': stock['input_name']
        })
    
    # 6. Save watchlist
    watchlist_file = Path('data/watchlist.json')
    with open(watchlist_file, 'w') as f:
        json.dump(watchlist, f, indent=2)
    
    print(f"\n✓ Watchlist saved to: {watchlist_file}")
    print(f"✓ {len(watchlist)} stocks added")
    
    # 7. Display sample
    print("\n📋 WATCHLIST PREVIEW (First 10):")
    print("="*80)
    for i, stock in enumerate(watchlist[:10], 1):
        token_info = f"Token: {stock['token']}" if stock['token'] != 'UNKNOWN' else "Token: Not found"
        print(f"{i:2d}. {stock['symbol']:15s} - {stock['name']:30s} ({token_info})")
    
    if len(watchlist) > 10:
        print(f"... and {len(watchlist) - 10} more stocks")
    
    # 8. Unmatched stocks
    if unmatched_stocks:
        print(f"\n⚠️  {len(unmatched_stocks)} UNMATCHED STOCKS:")
        print("="*80)
        for stock in unmatched_stocks:
            print(f"  - {stock}")
        
        unmatched_file = Path('data/unmatched_stocks.txt')
        with open(unmatched_file, 'w') as f:
            for stock in unmatched_stocks:
                f.write(f"{stock}\n")
        print(f"\n✓ Saved to: {unmatched_file}")
    
    print("\n" + "="*80)
    print("✅ WATCHLIST CREATION COMPLETE")
    print("="*80)
    print("\nYour bot will now load these stocks from data/watchlist.json")

if __name__ == "__main__":
    main()