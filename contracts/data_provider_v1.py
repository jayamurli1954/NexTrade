# contracts/data_provider_v1.py
"""Version 1 Data Provider Contract - DO NOT MODIFY"""
from typing import TypedDict, List, Optional
from datetime import datetime

class PortfolioHolding(TypedDict):
    symbol: str
    quantity: int
    avg_price: float
    current_price: float
    pnl: float
    pnl_percent: float

class FundsInfo(TypedDict):
    available_cash: float
    used_margin: float
    available_margin: float
    total_collateral: float

class DataProviderInterface:
    """All providers MUST implement these"""
    
    def get_ltp(self, symbol: str, exchange: str) -> Optional[float]:
        raise NotImplementedError
    
    def get_holdings(self) -> List[PortfolioHolding]:
        raise NotImplementedError
    
    def get_funds(self) -> FundsInfo:
        raise NotImplementedError
    
    def is_connected(self) -> bool:
        raise NotImplementedError