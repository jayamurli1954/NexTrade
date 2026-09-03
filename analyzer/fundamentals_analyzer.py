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

Data sources (in order):
1. Local research store (Screener.in bulk download under research/data/fundamentals/)
2. yfinance (Yahoo Finance) fallback for symbols outside the watchlist store
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from research.fundamentals_loader import build_fundamentals_highlights, load_fundamentals_from_store

logger = logging.getLogger("FundamentalsAnalyzer")


class FundamentalsAnalyzer:
    """
    Analyze fundamental metrics and return a score 0-100
    """

    def __init__(self, data_provider):
        self.data_provider = data_provider
        self.cache: Dict[str, Dict[str, Any]] = {}

        try:
            import yfinance as yf

            self.yf = yf
            self.has_yfinance = True
            logger.info("yfinance available for fundamentals fallback")
        except ImportError:
            self.has_yfinance = False
            logger.warning("yfinance not installed - local store only")

    def analyze_fundamentals(self, symbol: str) -> int:
        """Analyze fundamentals and return score 0-100."""
        return int(self.analyze_fundamentals_bundle(symbol).get("score") or 0)

    def analyze_fundamentals_bundle(self, symbol: str) -> Dict[str, Any]:
        """
        Gate score (legacy) + FI-2 display intelligence from FundamentalService.

        Returns:
            {
              "score": int,                      # LEGACY — used for BUY/SELL points only
              "highlights": list[str],           # legacy raw highlights
              "investment_thesis": list[str],    # FI-2 display
              "factor_scores": dict | None,
              "factor_badges": dict | None,
              "factor_trends": dict | None,
              "valuation_relatives": dict | None,
              "ai_summary_seed": None,           # filled by OpportunityEngine with direction
              "fundamentals_meta": dict | None,
              "source": "local" | "yfinance" | None,  # gate score source
              "display_source": "factor_store" | None,
            }
        """
        cache_key = f"{symbol}_{datetime.now().strftime('%Y-%m-%d')}_fi2"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # --- Display path (FI-2): Fundamental Service → factor store ---
        display: Dict[str, Any] = {}
        try:
            from research.fundamental_service import get_fundamental_service

            intel = get_fundamental_service().get_symbol_intelligence(symbol)
            if intel:
                display = {
                    "investment_thesis": list(intel.get("investment_thesis") or []),
                    "factor_scores": intel.get("factor_scores"),
                    "factor_badges": intel.get("factor_badges"),
                    "factor_trends": intel.get("factor_trends"),
                    "valuation_relatives": intel.get("valuation_relatives"),
                    "fundamentals_meta": {
                        "source": "factor_store",
                        "factor_version": intel.get("factor_version"),
                        "generated_at": intel.get("generated_at"),
                        "fiscal_year": intel.get("fiscal_year"),
                        "as_of_label": intel.get("as_of_label"),
                    },
                    "display_source": "factor_store",
                }
        except Exception as e:
            logger.debug("Factor display unavailable for %s: %s", symbol, e)

        # --- Gate path: legacy local/yfinance score (unchanged math) ---
        fundamentals = self._fetch_fundamentals(symbol)
        if not fundamentals:
            bundle = {
                "score": 0,
                "highlights": [],
                "source": None,
                "metrics": None,
                **{
                    "investment_thesis": display.get("investment_thesis") or [],
                    "factor_scores": display.get("factor_scores"),
                    "factor_badges": display.get("factor_badges"),
                    "factor_trends": display.get("factor_trends"),
                    "valuation_relatives": display.get("valuation_relatives"),
                    "fundamentals_meta": display.get("fundamentals_meta"),
                    "display_source": display.get("display_source"),
                },
            }
            self.cache[cache_key] = bundle
            return bundle

        source = str(fundamentals.get("_source") or "unknown")
        metrics = {k: v for k, v in fundamentals.items() if not str(k).startswith("_")}
        score = self._calculate_score(metrics)
        highlights = build_fundamentals_highlights(metrics, source=source)

        bundle = {
            "score": score,
            "highlights": highlights,
            "source": source,
            "metrics": metrics,
            "investment_thesis": display.get("investment_thesis") or [],
            "factor_scores": display.get("factor_scores"),
            "factor_badges": display.get("factor_badges"),
            "factor_trends": display.get("factor_trends"),
            "valuation_relatives": display.get("valuation_relatives"),
            "fundamentals_meta": display.get("fundamentals_meta"),
            "display_source": display.get("display_source"),
        }
        self.cache[cache_key] = bundle
        logger.info("%s fundamentals gate (%s): %s/100 - %s", symbol, source, score, self._get_rating(score))
        return bundle

    def _fetch_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        local = load_fundamentals_from_store(symbol)
        if local:
            logger.debug("Loaded local fundamentals for %s", symbol)
            return local

        if not self.has_yfinance:
            logger.warning("No local fundamentals for %s and yfinance unavailable", symbol)
            return None

        return self._fetch_fundamentals_yfinance(symbol)

    def _fetch_fundamentals_yfinance(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            ticker_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
            ticker = self.yf.Ticker(ticker_symbol)
            info = ticker.info

            fundamentals = {
                "pe_ratio": info.get("trailingPE", info.get("forwardPE", None)),
                "pb_ratio": info.get("priceToBook", None),
                "debt_to_equity": info.get("debtToEquity", None),
                "roe": info.get("returnOnEquity", None),
                "profit_margin": info.get("profitMargins", None),
                "revenue_growth": info.get("revenueGrowth", None),
                "dividend_yield": info.get("dividendYield", None),
                "market_cap": info.get("marketCap", None),
                "current_ratio": info.get("currentRatio", None),
                "quick_ratio": info.get("quickRatio", None),
                "_source": "yfinance",
            }

            if fundamentals["roe"] and fundamentals["roe"] > 1:
                fundamentals["roe"] = fundamentals["roe"] / 100
            if fundamentals["profit_margin"] and fundamentals["profit_margin"] > 1:
                fundamentals["profit_margin"] = fundamentals["profit_margin"] / 100
            if fundamentals["revenue_growth"] and fundamentals["revenue_growth"] > 1:
                fundamentals["revenue_growth"] = fundamentals["revenue_growth"] / 100

            logger.debug("%s yfinance fundamentals: %s", symbol, fundamentals)
            return fundamentals
        except Exception as e:
            logger.error("Failed to fetch yfinance fundamentals for %s: %s", symbol, e)
            return None

    def _calculate_score(self, fundamentals: Dict[str, Any]) -> int:
        """
        Calculate fundamental score 0-100 based on metrics.

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

        pe = fundamentals.get("pe_ratio")
        if pe:
            if pe < 15:
                score += 20
            elif pe < 25:
                score += 15
            elif pe < 35:
                score += 10
            elif pe < 50:
                score += 5

        dte = fundamentals.get("debt_to_equity")
        if dte is not None:
            if dte < 0.5:
                score += 15
            elif dte < 1.0:
                score += 12
            elif dte < 2.0:
                score += 8
            elif dte < 3.0:
                score += 4

        roe = fundamentals.get("roe")
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

        pm = fundamentals.get("profit_margin")
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

        rg = fundamentals.get("revenue_growth")
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

        cr = fundamentals.get("current_ratio")
        if cr:
            if cr > 2.0:
                score += 10
            elif cr > 1.5:
                score += 8
            elif cr > 1.0:
                score += 6
            elif cr > 0.8:
                score += 3

        dy = fundamentals.get("dividend_yield")
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

    def _get_rating(self, score: int) -> str:
        if score >= 80:
            return "Excellent"
        if score >= 65:
            return "Good"
        if score >= 50:
            return "Fair"
        if score >= 35:
            return "Weak"
        return "Poor"

    def get_detailed_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        bundle = self.analyze_fundamentals_bundle(symbol)
        if not bundle.get("metrics"):
            return None
        return {
            "symbol": symbol,
            "score": bundle["score"],
            "rating": self._get_rating(bundle["score"]),
            "metrics": bundle["metrics"],
            "highlights": bundle.get("highlights") or [],
            "source": bundle.get("source"),
            "timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    class MockDataProvider:
        pass

    analyzer = FundamentalsAnalyzer(MockDataProvider())
    for test_symbol in ["RELIANCE", "TCS", "INFY", "HDFCBANK"]:
        bundle = analyzer.analyze_fundamentals_bundle(test_symbol)
        print(f"\n{'=' * 60}\n{test_symbol}: {bundle['score']}/100 ({bundle['source']})")
        for line in bundle.get("highlights") or []:
            print(f"  - {line}")
