# config/ibkr_config.py
"""
Interactive Brokers (IBKR) Configuration & Physical Security Guard for NexTrade (Sub-Phase 4C).
Defines IBKR connection configuration and enforces physical port isolation to prevent
accidental connection to live IBKR production ports (7462/4001) while live trading is disabled.
"""
from dataclasses import dataclass, field
from typing import Set


KNOWN_LIVE_IBKR_PORTS: Set[int] = {7462, 4001}
KNOWN_PAPER_IBKR_PORTS: Set[int] = {7497, 4002}


@dataclass(frozen=True)
class IBKRConfig:
    """Immutable configuration container for Interactive Brokers connection parameters."""
    host: str = "127.0.0.1"
    port: int = 7497  # Default: TWS Paper port
    client_id: int = 1
    account_id: str = "DU123456"  # Default: IBKR Paper Account format
    is_paper_account: bool = True
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 5.0
    max_reconnect_attempts: int = 3
    reconnect_backoff_seconds: float = 2.0


def validate_sandbox_config(config: IBKRConfig, live_trading_enabled: bool = False) -> None:
    """
    Validates IBKR connection configuration against physical safety bounds.
    Raises PermissionError if a live production port or non-paper account is configured
    while live_trading_enabled is False.
    """
    if not isinstance(config, IBKRConfig):
        raise ValueError(f"Expected IBKRConfig instance, got {type(config).__name__}")

    # Guard 1: Physical Live Port Rejection
    if not live_trading_enabled and config.port in KNOWN_LIVE_IBKR_PORTS:
        raise PermissionError(
            f"SECURITY GUARD VIOLATION: IBKR live port {config.port} requested while "
            f"live_trading_enabled is False. Only paper ports ({KNOWN_PAPER_IBKR_PORTS}) are permitted."
        )

    # Guard 2: Paper Account Designation Rejection
    if not live_trading_enabled and not config.is_paper_account:
        raise PermissionError(
            "SECURITY GUARD VIOLATION: IBKR live account designation requested while "
            "live_trading_enabled is False. is_paper_account must be True."
        )

    # Guard 3: Live Account ID Format Guard (IBKR Live accounts start with 'U', Paper start with 'DU')
    if not live_trading_enabled and config.account_id and not config.account_id.startswith("DU") and not config.account_id.startswith("PAPER"):
        raise PermissionError(
            f"SECURITY GUARD VIOLATION: Account ID '{config.account_id}' appears to be a live account. "
            "Paper accounts must start with 'DU' or 'PAPER' while live_trading_enabled is False."
        )
