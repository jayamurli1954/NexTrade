# analyzer/fundamentals_analyzer.py
"""
Fundamentals Analyzer for NSE/BSE stocks

Analyzes financial health metrics:
- P/E Ratio (Price-to-Earnings)
- Debt-to-Equity Ratio
- ROE (Return on Equity)
- Revenue Growth
- Profit Margins
- Dividend Yield

Data sources supported:
1. yfinance (Yahoo Finance) - Free, good for Indian stocks
2. NSE/BSE APIs - Official but may require parsing
3. Screener.in - Good Indian stock data but needs web scraping
"""

import logging
import pandas as pd
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("FundamentalsAnalyzer")


class FundamentalsAnalyzer:
    """
    Analyze fundamental metrics and return a score 0-100
    """
    
    def __init__(self, data_provider):
        self.data_provider = data_provider
        self.cache = {}  # Cache fundamentals for 24 hours

        # Try to import yfinance
        try:
            import yfinance as yf
            self.yf = yf
            self.has_yfinance = True
            logger.info("✅ yfinance available for fundamentals")
        except ImportError:
            self.has_yfinance = False
            logger.warning("⚠️ yfinance not installed - install with: pip install yfinance")

        # ✅ NEW: Initialize Screener.in scraper
        self.has_screener = False
        try:
            from data_provider.screener_scraper import get_screener_scraper
            self.screener = get_screener_scraper()
            self.has_screener = True
            logger.info("✅ Screener.in scraper available for fundamentals")
        except Exception as e:
            logger.warning(f"⚠️ Screener.in scraper initialization failed: {e}")
    
    def analyze_fundamentals(self, symbol):
        """
        Analyze fundamentals and return score 0-100
        
        Higher score = Better fundamentals for LONG positions
        """
        # Check cache (24-hour validity)
        cache_key = f"{symbol}_{datetime.now().strftime('%Y-%m-%d')}"
        if cache_key in self.cache:
            logger.debug(f"Using cached fundamentals for {symbol}")
            return self.cache[cache_key]
        
        try:
            fundamentals = self._fetch_fundamentals(symbol)
            
            if not fundamentals:
                logger.warning(f"No fundamentals data for {symbol}")
                return 0
            
            score = self._calculate_score(fundamentals)
            
            # Cache the result
            self.cache[cache_key] = score
            
            logger.info(f"{symbol} fundamentals: {score}/100 - {self._get_rating(score)}")
            return score
            
        except Exception as e:
            logger.error(f"Fundamentals error for {symbol}: {e}")
            return 0
    
    def _fetch_fundamentals(self, symbol):
        """
        Fetch fundamental data from available sources
        Priority: Screener.in (more accurate for Indian stocks) -> yfinance (fallback)
        """
        fundamentals = None

        # ✅ NEW: Try Screener.in first (better for Indian stocks)
        if self.has_screener:
            try:
                logger.debug(f"Fetching {symbol} fundamentals from Screener.in")
                screener_data = self.screener.scrape_fundamentals(symbol)

                if screener_data and not screener_data.get('error'):
                    # Convert Screener.in format to our standard format
                    fundamentals = {
                        'pe_ratio': screener_data.get('pe_ratio'),
                        'pb_ratio': screener_data.get('pb_ratio'),
                        'debt_to_equity': screener_data.get('debt_to_equity'),
                        'roe': screener_data.get('roe'),  # Already in percentage
                        'profit_margin': None,  # Not directly available
                        'revenue_growth': screener_data.get('sales_growth_3y'),  # 3Y sales growth
                        'dividend_yield': screener_data.get('dividend_yield'),
                        'market_cap': screener_data.get('market_cap'),
                        'current_ratio': None,  # Not available from Screener.in
                        'quick_ratio': None,
                        'roce': screener_data.get('roce'),  # Additional metric
                        'promoter_holding': screener_data.get('promoter_holding'),  # Additional metric
                        'source': 'screener.in'
                    }

                    # Normalize ROE and dividend yield to decimals (0-1 range) for compatibility
                    if fundamentals['roe'] and fundamentals['roe'] > 1:
                        fundamentals['roe'] = fundamentals['roe'] / 100

                    if fundamentals['dividend_yield'] and fundamentals['dividend_yield'] > 1:
                        fundamentals['dividend_yield'] = fundamentals['dividend_yield'] / 100

                    if fundamentals['revenue_growth'] and fundamentals['revenue_growth'] > 1:
                        fundamentals['revenue_growth'] = fundamentals['revenue_growth'] / 100

                    logger.info(f"✅ {symbol} fundamentals from Screener.in")
                    return fundamentals

            except Exception as e:
                logger.debug(f"Screener.in fetch failed for {symbol}: {e}")

        # Fallback to yfinance
        if not self.has_yfinance:
            logger.warning("No fundamental data sources available")
            return None

        try:
            logger.debug(f"Fetching {symbol} fundamentals from yfinance (fallback)")
            # For NSE stocks, append .NS suffix
            ticker_symbol = f"{symbol}.NS" if not symbol.endswith('.NS') else symbol

            ticker = self.yf.Ticker(ticker_symbol)
            info = ticker.info

            # Extract key metrics
            fundamentals = {
                'pe_ratio': info.get('trailingPE', info.get('forwardPE', None)),
                'pb_ratio': info.get('priceToBook', None),
                'debt_to_equity': info.get('debtToEquity', None),
                'roe': info.get('returnOnEquity', None),
                'profit_margin': info.get('profitMargins', None),
                'revenue_growth': info.get('revenueGrowth', None),
                'dividend_yield': info.get('dividendYield', None),
                'market_cap': info.get('marketCap', None),
                'current_ratio': info.get('currentRatio', None),
                'quick_ratio': info.get('quickRatio', None),
                'source': 'yfinance'
            }

            # Convert percentages to decimals if needed
            if fundamentals['roe'] and fundamentals['roe'] > 1:
                fundamentals['roe'] = fundamentals['roe'] / 100

            if fundamentals['profit_margin'] and fundamentals['profit_margin'] > 1:
                fundamentals['profit_margin'] = fundamentals['profit_margin'] / 100

            if fundamentals['revenue_growth'] and fundamentals['revenue_growth'] > 1:
                fundamentals['revenue_growth'] = fundamentals['revenue_growth'] / 100

            logger.info(f"✅ {symbol} fundamentals from yfinance")
            return fundamentals

        except Exception as e:
            logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
            return None
    
    def _calculate_score(self, fundamentals):
        """
        Calculate fundamental score 0-100 based on metrics
        
        Scoring breakdown:
        - P/E Ratio: 20 points (lower is better for value)
        - Debt-to-Equity: 15 points (lower is better)
        - ROE: 20 points (higher is better)
        - Profit Margin: 15 points (higher is better)
        - Revenue Growth: 15 points (higher is better)
        - Liquidity (Current Ratio): 10 points
        - Dividend Yield: 5 points (bonus for income)
        """
        score = 0
        max_score = 100
        
        # 1. P/E Ratio (20 points) - Lower is better for value
        pe = fundamentals.get('pe_ratio')
        if pe:
            if pe < 15:
                score += 20
            elif pe < 25:
                score += 15
            elif pe < 35:
                score += 10
            elif pe < 50:
                score += 5
            # Very high P/E (>50) gets 0 points
        
        # 2. Debt-to-Equity (15 points) - Lower is better
        dte = fundamentals.get('debt_to_equity')
        if dte is not None:
            if dte < 0.5:
                score += 15
            elif dte < 1.0:
                score += 12
            elif dte < 2.0:
                score += 8
            elif dte < 3.0:
                score += 4
            # High debt (>3) gets 0 points
        
        # 3. ROE (20 points) - Higher is better
        roe = fundamentals.get('roe')
        if roe:
            roe_pct = roe * 100 if roe < 1 else roe
            if roe_pct > 20:
                score += 20
            elif roe_pct > 15:
                score += 16
            elif roe_pct > 10:
                score += 12
            elif roe_pct > 5:
                score += 8
            elif roe_pct > 0:
                score += 4
        
        # 4. Profit Margin (15 points) - Higher is better
        pm = fundamentals.get('profit_margin')
        if pm:
            pm_pct = pm * 100 if pm < 1 else pm
            if pm_pct > 15:
                score += 15
            elif pm_pct > 10:
                score += 12
            elif pm_pct > 5:
                score += 9
            elif pm_pct > 2:
                score += 6
            elif pm_pct > 0:
                score += 3
        
        # 5. Revenue Growth (15 points) - Higher is better
        rg = fundamentals.get('revenue_growth')
        if rg:
            rg_pct = rg * 100 if rg < 1 else rg
            if rg_pct > 20:
                score += 15
            elif rg_pct > 15:
                score += 12
            elif rg_pct > 10:
                score += 10
            elif rg_pct > 5:
                score += 7
            elif rg_pct > 0:
                score += 4
            # Negative growth gets 0 points
        
        # 6. Current Ratio (10 points) - Liquidity measure
        cr = fundamentals.get('current_ratio')
        if cr:
            if cr > 2.0:
                score += 10
            elif cr > 1.5:
                score += 8
            elif cr > 1.0:
                score += 6
            elif cr > 0.8:
                score += 3
        
        # 7. Dividend Yield (5 points) - Bonus for income
        dy = fundamentals.get('dividend_yield')
        if dy:
            dy_pct = dy * 100 if dy < 1 else dy
            if dy_pct > 3:
                score += 5
            elif dy_pct > 2:
                score += 4
            elif dy_pct > 1:
                score += 3
            elif dy_pct > 0:
                score += 2
        
        return min(score, max_score)
    
    def _get_rating(self, score):
        """Convert score to rating"""
        if score >= 80:
            return "Excellent 🌟"
        elif score >= 65:
            return "Good ✅"
        elif score >= 50:
            return "Fair ⚠️"
        elif score >= 35:
            return "Weak ⚠️"
        else:
            return "Poor ❌"
    
    def get_detailed_analysis(self, symbol):
        """
        Get detailed fundamental analysis with all metrics
        """
        fundamentals = self._fetch_fundamentals(symbol)
        
        if not fundamentals:
            return None
        
        score = self._calculate_score(fundamentals)
        
        return {
            'symbol': symbol,
            'score': score,
            'rating': self._get_rating(score),
            'metrics': fundamentals,
            'timestamp': datetime.now().isoformat()
        }


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Mock data provider for testing
    class MockDataProvider:
        pass
    
    analyzer = FundamentalsAnalyzer(MockDataProvider())
    
    # Test with some NSE stocks
    test_symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK']
    
    for symbol in test_symbols:
        print(f"\n{'='*60}")
        print(f"Testing {symbol}")
        print('='*60)
        
        score = analyzer.analyze_fundamentals(symbol)
        print(f"Score: {score}/100")
        
        # Get detailed analysis
        detailed = analyzer.get_detailed_analysis(symbol)
        if detailed:
            print(f"Rating: {detailed['rating']}")
            print("\nKey Metrics:")
            for key, value in detailed['metrics'].items():
                if value is not None:
                    print(f"  {key}: {value}")
