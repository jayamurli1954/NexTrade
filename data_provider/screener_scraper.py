"""
Screener.in Data Scraper

Scrapes fundamental data from Screener.in for Indian stocks.
Provides comprehensive fundamental metrics for analysis.

Data scraped:
- Market Cap
- Current Price
- PE Ratio, PB Ratio
- Dividend Yield
- ROE (Return on Equity)
- ROCE (Return on Capital Employed)
- Debt to Equity
- Sales Growth (3Y, 5Y)
- Profit Growth (3Y, 5Y)
- Promoter Holding
- And more...

Features:
- Caching (60-min duration) to reduce load
- Rate limiting (respectful scraping)
- Error handling with fallback
"""

import logging
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from typing import Dict, Optional
import json
import os
from pathlib import Path
import time

logger = logging.getLogger(__name__)

class ScreenerScraper:
    """
    Scraper for Screener.in fundamental data
    """

    def __init__(self, cache_dir: str = "data/screener_cache"):
        """
        Initialize Screener scraper

        Args:
            cache_dir: Directory for caching scraped data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.base_url = "https://www.screener.in/company/"
        self.cache_duration = 60  # minutes

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 2  # seconds between requests

        # Headers to mimic browser request
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        logger.info("Screener.in scraper initialized")

    def _get_cache_path(self, symbol: str) -> Path:
        """Get cache file path for a symbol"""
        return self.cache_dir / f"{symbol}_screener.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache is still valid"""
        if not cache_path.exists():
            return False

        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)

            cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
            age_minutes = (datetime.now() - cache_time).total_seconds() / 60

            return age_minutes < self.cache_duration

        except Exception as e:
            logger.debug(f"Cache validation failed: {e}")
            return False

    def _load_from_cache(self, symbol: str) -> Optional[Dict]:
        """Load data from cache"""
        cache_path = self._get_cache_path(symbol)

        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                logger.debug(f"Loaded {symbol} data from cache")
                return cache_data
            except Exception as e:
                logger.debug(f"Failed to load cache: {e}")

        return None

    def _save_to_cache(self, symbol: str, data: Dict):
        """Save data to cache"""
        try:
            cache_path = self._get_cache_path(symbol)
            data['timestamp'] = datetime.now().isoformat()

            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {symbol} data to cache")

        except Exception as e:
            logger.debug(f"Failed to save cache: {e}")

    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _clean_symbol(self, symbol: str) -> str:
        """Clean symbol for Screener.in URL"""
        # Remove exchange suffix
        symbol = symbol.replace('.NS', '').replace('.BO', '')
        # Screener uses uppercase
        return symbol.upper()

    def _parse_number(self, text: str) -> Optional[float]:
        """
        Parse number from text, handling Indian notation (Cr, Lakhs, etc.)

        Examples:
        - "1,234.56" -> 1234.56
        - "12.5 Cr." -> 125000000
        - "500 Lakhs" -> 50000000
        - "25.3%" -> 25.3
        """
        if not text or text.strip() == '-' or text.strip() == '':
            return None

        try:
            # Remove commas and percentage signs
            text = text.replace(',', '').replace('%', '').strip()

            # Handle Crores (Cr)
            if 'Cr' in text or 'cr' in text:
                num = float(re.search(r'[-+]?\d*\.?\d+', text).group())
                return num * 10000000  # 1 Crore = 10 million

            # Handle Lakhs
            if 'Lakh' in text or 'lakh' in text:
                num = float(re.search(r'[-+]?\d*\.?\d+', text).group())
                return num * 100000  # 1 Lakh = 100,000

            # Regular number
            return float(re.search(r'[-+]?\d*\.?\d+', text).group())

        except Exception as e:
            logger.debug(f"Failed to parse number '{text}': {e}")
            return None

    def _extract_metrics(self, soup: BeautifulSoup) -> Dict:
        """Extract fundamental metrics from parsed HTML"""
        metrics = {}

        try:
            # Market Cap
            market_cap = soup.find('span', string=re.compile('Market Cap', re.I))
            if market_cap:
                value = market_cap.find_next('span', class_='number')
                if value:
                    metrics['market_cap'] = self._parse_number(value.text)

            # Current Price
            price = soup.find('span', class_='number', id='top-ratios')
            if price:
                metrics['current_price'] = self._parse_number(price.text)

            # PE Ratio
            pe = soup.find('span', string=re.compile('Stock P/E', re.I))
            if pe:
                value = pe.find_next('span', class_='number')
                if value:
                    metrics['pe_ratio'] = self._parse_number(value.text)

            # PB Ratio
            pb = soup.find('span', string=re.compile('Price to Book', re.I))
            if pb:
                value = pb.find_next('span', class_='number')
                if value:
                    metrics['pb_ratio'] = self._parse_number(value.text)

            # Dividend Yield
            dividend = soup.find('span', string=re.compile('Dividend Yield', re.I))
            if dividend:
                value = dividend.find_next('span', class_='number')
                if value:
                    metrics['dividend_yield'] = self._parse_number(value.text)

            # ROE
            roe = soup.find('span', string=re.compile('ROE', re.I))
            if roe:
                value = roe.find_next('span', class_='number')
                if value:
                    metrics['roe'] = self._parse_number(value.text)

            # ROCE
            roce = soup.find('span', string=re.compile('ROCE', re.I))
            if roce:
                value = roce.find_next('span', class_='number')
                if value:
                    metrics['roce'] = self._parse_number(value.text)

            # Debt to Equity
            debt = soup.find('span', string=re.compile('Debt to equity', re.I))
            if debt:
                value = debt.find_next('span', class_='number')
                if value:
                    metrics['debt_to_equity'] = self._parse_number(value.text)

            # Sales Growth (look for compound growth tables)
            sales_growth = soup.find('td', string=re.compile('Sales growth', re.I))
            if sales_growth:
                # Try to get 3Y growth
                growth_3y = sales_growth.find_next('td')
                if growth_3y:
                    metrics['sales_growth_3y'] = self._parse_number(growth_3y.text)

            # Profit Growth
            profit_growth = soup.find('td', string=re.compile('Profit growth', re.I))
            if profit_growth:
                # Try to get 3Y growth
                growth_3y = profit_growth.find_next('td')
                if growth_3y:
                    metrics['profit_growth_3y'] = self._parse_number(growth_3y.text)

            # Promoter Holding
            promoter = soup.find('span', string=re.compile('Promoter holding', re.I))
            if promoter:
                value = promoter.find_next('span', class_='number')
                if value:
                    metrics['promoter_holding'] = self._parse_number(value.text)

            logger.debug(f"Extracted {len(metrics)} metrics")

        except Exception as e:
            logger.error(f"Error extracting metrics: {e}")

        return metrics

    def scrape_fundamentals(self, symbol: str) -> Dict:
        """
        Scrape fundamental data for a symbol from Screener.in

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'TCS', 'INFY')

        Returns:
            Dict containing fundamental metrics
        """
        # Clean symbol
        symbol_clean = self._clean_symbol(symbol)

        # Check cache first
        cached = self._load_from_cache(symbol_clean)
        if cached:
            return cached

        # Rate limiting
        self._rate_limit()

        try:
            # Build URL
            url = f"{self.base_url}{symbol_clean}/"
            logger.debug(f"Fetching {url}")

            # Make request
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract metrics
            metrics = self._extract_metrics(soup)

            if not metrics:
                logger.warning(f"No metrics extracted for {symbol_clean}")
                return {'symbol': symbol_clean, 'error': 'no_data'}

            # Add metadata
            metrics['symbol'] = symbol_clean
            metrics['source'] = 'screener.in'
            metrics['scraped_at'] = datetime.now().isoformat()

            # Cache the result
            self._save_to_cache(symbol_clean, metrics)

            logger.info(f"📊 {symbol_clean} fundamentals scraped: PE={metrics.get('pe_ratio', 'N/A')}, ROE={metrics.get('roe', 'N/A')}%")

            return metrics

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Symbol {symbol_clean} not found on Screener.in")
                return {'symbol': symbol_clean, 'error': 'not_found'}
            else:
                logger.error(f"HTTP error scraping {symbol_clean}: {e}")
                return {'symbol': symbol_clean, 'error': 'http_error'}

        except Exception as e:
            logger.error(f"Error scraping {symbol_clean}: {e}")
            return {'symbol': symbol_clean, 'error': 'scraping_error'}

    def calculate_fundamental_score(self, metrics: Dict) -> float:
        """
        Calculate fundamental score (0-100) from scraped metrics

        Scoring criteria:
        - PE Ratio: Lower is better (max 15 points)
        - ROE: Higher is better (max 15 points)
        - ROCE: Higher is better (max 10 points)
        - Debt to Equity: Lower is better (max 10 points)
        - Sales Growth: Higher is better (max 15 points)
        - Profit Growth: Higher is better (max 15 points)
        - Promoter Holding: Higher is better (max 10 points)
        - Dividend Yield: Higher is better (max 10 points)

        Returns:
            Score from 0 to 100
        """
        if metrics.get('error'):
            return 0.0

        score = 0.0

        # PE Ratio (lower is better)
        pe = metrics.get('pe_ratio')
        if pe:
            if pe < 15:
                score += 15
            elif pe < 25:
                score += 10
            elif pe < 35:
                score += 5

        # ROE (higher is better)
        roe = metrics.get('roe')
        if roe:
            if roe > 20:
                score += 15
            elif roe > 15:
                score += 10
            elif roe > 10:
                score += 5

        # ROCE (higher is better)
        roce = metrics.get('roce')
        if roce:
            if roce > 20:
                score += 10
            elif roce > 15:
                score += 7
            elif roce > 10:
                score += 4

        # Debt to Equity (lower is better)
        debt = metrics.get('debt_to_equity')
        if debt is not None:
            if debt < 0.5:
                score += 10
            elif debt < 1.0:
                score += 7
            elif debt < 2.0:
                score += 4

        # Sales Growth (higher is better)
        sales_growth = metrics.get('sales_growth_3y')
        if sales_growth:
            if sales_growth > 20:
                score += 15
            elif sales_growth > 10:
                score += 10
            elif sales_growth > 5:
                score += 5

        # Profit Growth (higher is better)
        profit_growth = metrics.get('profit_growth_3y')
        if profit_growth:
            if profit_growth > 20:
                score += 15
            elif profit_growth > 10:
                score += 10
            elif profit_growth > 5:
                score += 5

        # Promoter Holding (higher is better)
        promoter = metrics.get('promoter_holding')
        if promoter:
            if promoter > 60:
                score += 10
            elif promoter > 50:
                score += 7
            elif promoter > 40:
                score += 4

        # Dividend Yield (higher is better)
        dividend = metrics.get('dividend_yield')
        if dividend:
            if dividend > 3:
                score += 10
            elif dividend > 2:
                score += 7
            elif dividend > 1:
                score += 4

        return min(100.0, score)


# Singleton instance
_screener_instance = None

def get_screener_scraper() -> ScreenerScraper:
    """Get or create Screener scraper singleton"""
    global _screener_instance
    if _screener_instance is None:
        _screener_instance = ScreenerScraper()
    return _screener_instance
