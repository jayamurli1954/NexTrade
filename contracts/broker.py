# contracts/broker.py
"""
Canonical Broker Interface Contract & Exception Hierarchy for NexTrade.
Defines abstract broker protocol for order execution, management, and account state.
Strictly independent of market data provider interfaces.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from contracts.order import Order, OrderModification
from contracts.trade import Trade
from contracts.position import Position
from contracts.funds import FundsInfo


# ----------------------------------------------------------------------
# Normalized Domain Broker Exceptions
# ----------------------------------------------------------------------

class BrokerError(Exception):
    """Base exception for all domain broker operations."""
    pass


class NetworkError(BrokerError):
    """Network connectivity error, socket error, or API timeout."""
    pass


class InsufficientFundsError(BrokerError):
    """Order placement or modification rejected due to insufficient cash or margin."""
    pass


class OrderNotFoundError(BrokerError):
    """Requested order_id not found on broker system."""
    pass


class OrderValidationError(BrokerError):
    """Order parameters rejected by pre-submission broker rules (e.g., tick size, invalid price)."""
    pass


class BrokerAuthenticationError(BrokerError):
    """Broker session expired, invalid credentials, or unauthorized access."""
    pass


# ----------------------------------------------------------------------
# Canonical Abstract Broker Interface Protocol
# ----------------------------------------------------------------------

class BrokerInterface(ABC):
    """
    Abstract Broker Protocol for order execution and account management.
    Session/connection lifecycle is handled by concrete adapter implementations.
    Market data calls (LTP, historical candles) belong exclusively to DataProviderInterface.
    """

    @abstractmethod
    def place_order(self, order: Order, idempotency_key: Optional[str] = None) -> Order:
        """
        Submit a domain Order to the broker.
        Returns the updated domain Order object (with broker_order_id and updated status).
        
        Note: idempotency_key provides client-side or native broker deduplication
        to protect against duplicate order placement during network retries.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """
        Cancel an open pending order by broker/domain order_id.
        Returns the updated domain Order object with status = CANCELLED.
        """
        pass

    @abstractmethod
    def modify_order(self, order_id: str, changes: OrderModification) -> Order:
        """
        Modify parameters of an open pending limit or stop order.
        Returns the updated domain Order object.
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        """
        Fetch and reconcile current execution status of a specific order.
        Returns the updated domain Order object.
        """
        pass

    @abstractmethod
    def get_open_orders(self) -> List[Order]:
        """
        Fetch all active, pending, or partially filled domain Orders.
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        Fetch current portfolio positions mapped to domain Position dataclasses.
        """
        pass

    @abstractmethod
    def get_account_funds(self) -> FundsInfo:
        """
        Fetch current account cash, used margin, and collateral mapped to domain FundsInfo.
        """
        pass

    @abstractmethod
    def get_trades(self, order_id: Optional[str] = None) -> List[Trade]:
        """
        Fetch trade execution fills mapped to domain Trade dataclasses.
        If order_id is specified, returns fills associated with that order.
        """
        pass
