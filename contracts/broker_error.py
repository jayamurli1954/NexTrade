# contracts/broker_error.py
"""
Broker Error Taxonomy & Normalization Layer for NexTrade (Sub-Phase 4B).
Classifies raw external broker errors into deterministic error categories and
determines whether errors represent pre-submission rejections or post-submission ambiguity.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional

from contracts.broker_domain import BrokerOrderStatus


class BrokerErrorType(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    RATE_LIMIT = "RATE_LIMIT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    TIMEOUT = "TIMEOUT"
    BROKER_REJECTED = "BROKER_REJECTED"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    MARKET_CLOSED = "MARKET_CLOSED"
    UNSUPPORTED_ORDER = "UNSUPPORTED_ORDER"
    UNKNOWN_BROKER_ERROR = "UNKNOWN_BROKER_ERROR"


@dataclass(frozen=True)
class BrokerError:
    """Normalized, immutable error payload from a broker operation."""
    error_type: BrokerErrorType
    message: str
    code: str = ""
    is_pre_submission: bool = True
    retryable: bool = False
    raw_details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def is_pre_submission_error(error_type: BrokerErrorType) -> bool:
    """
    Returns True if the error occurs provably before the broker accepts/acknowledges the order.
    Yields BrokerOrderStatus.REJECTED (Invariant E15).
    """
    pre_submission_types = {
        BrokerErrorType.AUTHENTICATION_ERROR,
        BrokerErrorType.AUTHORIZATION_ERROR,
        BrokerErrorType.VALIDATION_ERROR,
        BrokerErrorType.INSUFFICIENT_FUNDS,
        BrokerErrorType.UNSUPPORTED_ORDER,
        BrokerErrorType.MARKET_CLOSED,
        BrokerErrorType.DUPLICATE_ORDER,
    }
    return error_type in pre_submission_types


def is_post_submission_ambiguous(error_type: BrokerErrorType) -> bool:
    """
    Returns True if the error introduces post-submission ambiguity (e.g. timeout after socket write).
    Yields BrokerOrderStatus.UNKNOWN requiring mandatory reconciliation (Invariants E6, E9, E14, E25, E37).
    """
    post_ambiguous_types = {
        BrokerErrorType.TIMEOUT,
        BrokerErrorType.CONNECTION_ERROR,
        BrokerErrorType.UNKNOWN_BROKER_ERROR,
    }
    return error_type in post_ambiguous_types


def classify_error_to_status(error: BrokerError) -> BrokerOrderStatus:
    """
    Maps a normalized BrokerError to a target BrokerOrderStatus.
    Guarantees pre-submission errors -> REJECTED; post-submission timeouts -> UNKNOWN.
    """
    if is_pre_submission_error(error.error_type):
        return BrokerOrderStatus.REJECTED
    elif is_post_submission_ambiguous(error.error_type):
        return BrokerOrderStatus.UNKNOWN
    else:
        return BrokerOrderStatus.REJECTED if error.is_pre_submission else BrokerOrderStatus.UNKNOWN
