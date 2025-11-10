"""
FinBERT News Sentiment Analysis Module

Uses FinBERT (Financial BERT) model for domain-specific sentiment analysis of financial news.
Fetches news from multiple sources and provides sentiment scores for trading signals.

Features:
- FinBERT model from HuggingFace (ProsusAI/finbert)
- Multi-source news fetching (NewsAPI, RSS feeds)
- Caching to reduce API calls and improve performance
- Fallback sentiment analysis if FinBERT unavailable
- Indian market-specific news sources

Sentiment Scores:
- Positive: 0.5 to 1.0 (Bullish)
- Neutral: -0.5 to 0.5
- Negative: -1.0 to -0.5 (Bearish)
"""

import logging
import requests
import feedparser
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
from pathlib import Path
import re

logger = logging.getLogger(__name__)

class FinBERTSentiment:
    """
    FinBERT-based sentiment analysis for financial news
    """

    def __init__(self, cache_dir: str = "data/news_cache"):
        """
        Initialize FinBERT sentiment analyzer

        Args:
            cache_dir: Directory for caching news and sentiment data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.tokenizer = None
        self.model_loaded = False

        # Try to load FinBERT model
        self._load_finbert_model()

        # News sources configuration
        self.news_sources = {
            'moneycontrol': 'https://www.moneycontrol.com/rss/marketreports.xml',
            'economictimes': 'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
            'business_standard': 'https://www.business-standard.com/rss/markets-106.rss',
        }

        # Cache duration (minutes)
        self.cache_duration = 30

        logger.info("FinBERT Sentiment Analyzer initialized")

    def _load_finbert_model(self):
        """Load FinBERT model from HuggingFace"""
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch

            logger.info("Loading FinBERT model from HuggingFace...")

            model_name = "ProsusAI/finbert"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

            # Set to evaluation mode
            self.model.eval()

            self.model_loaded = True
            logger.info("✅ FinBERT model loaded successfully")

        except ImportError:
            logger.warning("⚠️ transformers/torch not installed. Using fallback sentiment analysis.")
            logger.warning("Install with: pip install transformers torch")
            self.model_loaded = False

        except Exception as e:
            logger.error(f"❌ Failed to load FinBERT model: {e}")
            logger.warning("Using fallback sentiment analysis")
            self.model_loaded = False

    def _get_cache_path(self, symbol: str) -> Path:
        """Get cache file path for a symbol"""
        return self.cache_dir / f"{symbol}_sentiment.json"

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
        """Load sentiment data from cache"""
        cache_path = self._get_cache_path(symbol)

        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                logger.debug(f"Loaded {symbol} sentiment from cache")
                return cache_data
            except Exception as e:
                logger.debug(f"Failed to load cache: {e}")

        return None

    def _save_to_cache(self, symbol: str, data: Dict):
        """Save sentiment data to cache"""
        try:
            cache_path = self._get_cache_path(symbol)
            data['timestamp'] = datetime.now().isoformat()

            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {symbol} sentiment to cache")

        except Exception as e:
            logger.debug(f"Failed to save cache: {e}")

    def _fetch_news_from_rss(self, symbol: str) -> List[Dict]:
        """Fetch news from RSS feeds"""
        news_items = []
        symbol_clean = symbol.replace('.NS', '').replace('.BO', '')

        for source_name, rss_url in self.news_sources.items():
            try:
                feed = feedparser.parse(rss_url)

                for entry in feed.entries[:10]:  # Get latest 10 entries
                    title = entry.get('title', '')
                    description = entry.get('description', '') or entry.get('summary', '')

                    # Check if news is relevant to symbol
                    if self._is_relevant(symbol_clean, title, description):
                        news_items.append({
                            'source': source_name,
                            'title': title,
                            'description': description,
                            'published': entry.get('published', ''),
                            'link': entry.get('link', '')
                        })

                logger.debug(f"Fetched {len(news_items)} relevant items from {source_name}")

            except Exception as e:
                logger.debug(f"Failed to fetch from {source_name}: {e}")

        return news_items

    def _is_relevant(self, symbol: str, title: str, description: str) -> bool:
        """Check if news is relevant to the symbol"""
        text = (title + ' ' + description).lower()
        symbol_lower = symbol.lower()

        # Direct symbol match
        if symbol_lower in text:
            return True

        # Common symbol variations
        variations = [
            symbol_lower.replace('&', 'and'),
            symbol_lower.replace('ltd', ''),
            symbol_lower.replace('limited', ''),
        ]

        for var in variations:
            if var.strip() in text:
                return True

        # For broad market analysis, include general market news
        market_keywords = ['nifty', 'sensex', 'stock market', 'bse', 'nse', 'market']
        if any(keyword in text for keyword in market_keywords):
            return True

        return False

    def _analyze_with_finbert(self, text: str) -> Dict:
        """
        Analyze sentiment using FinBERT model

        Returns:
            Dict with sentiment scores: {positive, neutral, negative}
        """
        if not self.model_loaded:
            return self._fallback_sentiment(text)

        try:
            import torch

            # Tokenize and prepare input
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512, padding=True)

            # Get prediction
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

            # FinBERT returns: [positive, negative, neutral]
            scores = predictions[0].tolist()

            return {
                'positive': scores[0],
                'negative': scores[1],
                'neutral': scores[2]
            }

        except Exception as e:
            logger.error(f"FinBERT analysis failed: {e}")
            return self._fallback_sentiment(text)

    def _fallback_sentiment(self, text: str) -> Dict:
        """
        Fallback sentiment analysis using keyword matching
        Used when FinBERT is not available
        """
        text_lower = text.lower()

        # Positive keywords
        positive_keywords = [
            'gain', 'rally', 'surge', 'jump', 'climb', 'rise', 'up', 'high', 'profit',
            'bullish', 'positive', 'strong', 'growth', 'advance', 'upgrade', 'beat',
            'outperform', 'buy', 'recommend', 'optimistic', 'recovery', 'boost'
        ]

        # Negative keywords
        negative_keywords = [
            'fall', 'drop', 'decline', 'crash', 'plunge', 'tumble', 'down', 'loss',
            'bearish', 'negative', 'weak', 'concern', 'worry', 'risk', 'sell',
            'downgrade', 'miss', 'underperform', 'pessimistic', 'crisis', 'warning'
        ]

        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

        total = positive_count + negative_count

        if total == 0:
            return {'positive': 0.33, 'neutral': 0.34, 'negative': 0.33}

        positive_ratio = positive_count / total
        negative_ratio = negative_count / total
        neutral_ratio = 1.0 - (positive_ratio + negative_ratio)

        return {
            'positive': positive_ratio,
            'neutral': neutral_ratio,
            'negative': negative_ratio
        }

    def _calculate_sentiment_score(self, sentiment: Dict) -> float:
        """
        Calculate overall sentiment score from FinBERT output

        Returns:
            Score from -1.0 (very bearish) to +1.0 (very bullish)
        """
        positive = sentiment.get('positive', 0)
        negative = sentiment.get('negative', 0)
        neutral = sentiment.get('neutral', 0)

        # Weight positive and negative, ignore neutral
        score = (positive - negative)

        # Normalize to -1 to +1 range
        return max(-1.0, min(1.0, score))

    def analyze_symbol_sentiment(self, symbol: str) -> Dict:
        """
        Analyze news sentiment for a symbol

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'TCS.NS')

        Returns:
            Dict containing:
            - sentiment_score: -1.0 to +1.0
            - sentiment_label: 'BULLISH', 'NEUTRAL', 'BEARISH'
            - confidence: 0 to 100
            - news_count: Number of news items analyzed
            - top_headlines: List of relevant headlines
        """
        # Check cache first
        cached = self._load_from_cache(symbol)
        if cached:
            return cached

        # Fetch news
        news_items = self._fetch_news_from_rss(symbol)

        if not news_items:
            logger.debug(f"No news found for {symbol}")
            result = {
                'sentiment_score': 0.0,
                'sentiment_label': 'NEUTRAL',
                'confidence': 0,
                'news_count': 0,
                'top_headlines': [],
                'method': 'no_news'
            }
            self._save_to_cache(symbol, result)
            return result

        # Analyze sentiment for each news item
        sentiments = []
        headlines = []

        for item in news_items[:5]:  # Analyze top 5 news items
            text = item['title'] + '. ' + item['description']
            sentiment = self._analyze_with_finbert(text)
            score = self._calculate_sentiment_score(sentiment)

            sentiments.append(score)
            headlines.append({
                'title': item['title'],
                'sentiment': score,
                'source': item['source']
            })

        # Calculate average sentiment
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        # Calculate confidence based on consistency
        if sentiments:
            variance = sum((s - avg_sentiment) ** 2 for s in sentiments) / len(sentiments)
            confidence = max(0, min(100, 100 - (variance * 100)))
        else:
            confidence = 0

        # Determine label
        if avg_sentiment > 0.2:
            label = 'BULLISH'
        elif avg_sentiment < -0.2:
            label = 'BEARISH'
        else:
            label = 'NEUTRAL'

        result = {
            'sentiment_score': round(avg_sentiment, 3),
            'sentiment_label': label,
            'confidence': int(confidence),
            'news_count': len(news_items),
            'top_headlines': headlines,
            'method': 'finbert' if self.model_loaded else 'fallback'
        }

        # Cache the result
        self._save_to_cache(symbol, result)

        logger.info(f"📰 {symbol} Sentiment: {label} ({avg_sentiment:.3f}) | {len(news_items)} news | {confidence}% confidence")

        return result

    def get_market_sentiment(self) -> Dict:
        """
        Get overall market sentiment (Nifty/Sensex)

        Returns:
            Dict with market sentiment analysis
        """
        # Analyze major indices
        nifty_sentiment = self.analyze_symbol_sentiment('NIFTY')

        return {
            'market_sentiment': nifty_sentiment['sentiment_score'],
            'market_label': nifty_sentiment['sentiment_label'],
            'confidence': nifty_sentiment['confidence'],
            'news_count': nifty_sentiment['news_count']
        }


# Singleton instance
_finbert_instance = None

def get_finbert_analyzer() -> FinBERTSentiment:
    """Get or create FinBERT analyzer singleton"""
    global _finbert_instance
    if _finbert_instance is None:
        _finbert_instance = FinBERTSentiment()
    return _finbert_instance
