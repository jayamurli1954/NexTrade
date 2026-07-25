# contracts/broker_adapter_v1.py
"""
Canonical Broker Adapter & Event Stream Abstract Interfaces for NexTrade (Sub-Phase 4B).
Defines pure abstract interfaces for synchronous request/response broker operations
and asynchronous broker event streams.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Dict, Any

from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderModificationRequest,
    BrokerOrderResult,
    BrokerOrder,
    BrokerPosition,
    BrokerAccount,
    BrokerEvent,
)
from contracts.broker_capabilities import BrokerCapabilities


class BrokerAdapter(ABC):
    """
    Abstract Base Class for synchronous, request/response broker integration.
    Operates strictly on canonical broker domain models (BrokerOrderRequest, BrokerOrderResult).
    Does NOT depend on Phase 3 core contracts (ExecutionRequest/ExecutionResult).
    """

    @abstractmethod
    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        """Submit an order to the broker. Returns canonical BrokerOrderResult."""
        pass

    @abstractmethod
    def get_order(self, broker_order_id: str) -> Optional[BrokerOrder]:
        """Fetch current status and fill state of a specific order."""
        pass

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        """Cancel an open order with the broker."""
        pass

    @abstractmethod
    def modify_order(self, request: BrokerOrderModificationRequest) -> BrokerOrderResult:
        """Modify an existing open order's quantity or price parameters."""
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """Fetch current open position for a symbol."""
        pass

    @abstractmethod
    def get_account(self) -> BrokerAccount:
        """Fetch broker account equity, buying power, and cash balance."""
        pass

    @abstractmethod
    def get_open_orders(self) -> List[BrokerOrder]:
        """Fetch all currently active/open orders."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Check connection state and health metrics of the broker adapter."""
        pass

    @abstractmethod
    def get_capabilities(self) -> BrokerCapabilities:
        """Return the immutable BrokerCapabilities matrix for this adapter."""
        pass


class BrokerEventStream(ABC):
    """
    Abstract Base Class for asynchronous broker event callback streams.
    Decoupled from synchronous request/response operations to prepare for Phase 4E.
    """

    @abstractmethod
    def subscribe(self, event_type: str, callback: Callable[[BrokerEvent], None]) -> None:
        """Subscribe a callback handler to an event stream topic."""
        pass

    @abstractmethod
    def unsubscribe(self, event_type: str) -> None:
        """Unsubscribe from an event stream topic."""
        pass

    @abstractmethod
    def poll_events(self) -> List[BrokerEvent]:
        """Poll and return pending queued broker events."""
        pass
