"""
NexTrade Phase 6F — Multi-Account Portfolio Manager & Isolation Governance.

Enforces strict multi-account isolation across registered production accounts (ACC_PROD_MULTI_01..03),
zero cross-account leakage, per-account capital ($1,000) & daily loss ($100) envelopes,
portfolio aggregate exposure ceiling ($3,000 max), atomic dual-scope reservation accounting (6F-P5A),
account-level & portfolio-level position reconciliation, account failure isolation (6F-P10),
hierarchical kill-switch governance (account-scoped vs master portfolio kill), and multi-tenant audit logging.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from observability.tamper_evident_logger import TamperEvidentLogger

logger = logging.getLogger("MultiAccountPortfolioManager")


class CrossAccountLeakageException(Exception):
    """Raised when an order intent or position access attempts cross-account leakage or boundary contamination."""
    pass


class PortfolioCeilingExceededException(Exception):
    """Raised when an allocation or reservation attempt exceeds per-account ($1,000) or portfolio ($3,000) ceilings."""
    pass


class AccountHaltedException(Exception):
    """Raised when an operation is attempted on an isolated or halted account."""
    pass


class AccountState(Enum):
    HEALTHY = "HEALTHY"
    RECONCILIATION_LOCK = "RECONCILIATION_LOCK"
    ISOLATED_HALT = "ISOLATED_HALT"
    EMERGENCY_KILLED = "EMERGENCY_KILLED"


@dataclass
class AccountProfile:
    account_id: str
    broker_id: str
    account_type: str
    capital_ceiling: float = 1000.00      # $1,000 max allocation per account
    daily_loss_limit: float = 100.00      # $100 max daily loss per account
    max_position_notional: float = 250.00 # $250 max per position
    max_open_positions: int = 4
    allowed_capabilities: Set[str] = field(default_factory=lambda: {"LIMIT", "MARKET", "INTRADAY"})
    session_epoch: int = 1
    state: AccountState = AccountState.HEALTHY
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_total: float = 0.0


@dataclass
class PortfolioReservation:
    reservation_id: str
    account_id: str
    order_intent_id: str
    symbol: str
    reserved_notional: float
    created_at: float = field(default_factory=time.time)


class MultiAccountPortfolioManager:
    """
    Manager governing multi-account execution, zero cross-account leakage, per-account risk envelopes,
    dual-scope atomic reservation accounting, account failure isolation, and hierarchical kill switch.
    """

    PORTFOLIO_AGGREGATE_CEILING = 3000.00  # $3,000 max total portfolio exposure across all accounts
    PORTFOLIO_MARGIN_UTILIZATION_CEILING_PCT = 30.0  # 30% max aggregate margin utilization

    REGISTERED_ACCOUNTS = {
        "ACC_PROD_MULTI_01": AccountProfile("ACC_PROD_MULTI_01", "IBKR", "INDIVIDUAL_MARGIN"),
        "ACC_PROD_MULTI_02": AccountProfile("ACC_PROD_MULTI_02", "IBKR", "INDIVIDUAL_MARGIN"),
        "ACC_PROD_MULTI_03": AccountProfile("ACC_PROD_MULTI_03", "IBKR", "INDIVIDUAL_MARGIN"),
    }

    def __init__(
        self,
        control_plane: Optional[SafetyControlPlane] = None,
        logger_audit: Optional[TamperEvidentLogger] = None
    ) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.audit_logger = logger_audit or TamperEvidentLogger(log_filepath="logs/tamper_evident_portfolio.log")
        
        self.accounts: Dict[str, AccountProfile] = {
            acc_id: AccountProfile(
                account_id=acc_id,
                broker_id=prof.broker_id,
                account_type=prof.account_type,
                capital_ceiling=prof.capital_ceiling,
                daily_loss_limit=prof.daily_loss_limit,
                allowed_capabilities=set(prof.allowed_capabilities)
            ) for acc_id, prof in self.REGISTERED_ACCOUNTS.items()
        }

        self._open_positions: Dict[str, Dict[str, Dict[str, Any]]] = {acc_id: {} for acc_id in self.accounts}
        self._active_reservations: Dict[str, PortfolioReservation] = {}
        self.portfolio_master_halted: bool = False

    def verify_account_registration(self, account_id: str) -> AccountProfile:
        """Verify account is registered in multi-account profile registry (6F-P1)."""
        if not account_id or account_id not in self.accounts:
            msg = f"MULTI-ACCOUNT VIOLATION: Account ID '{account_id}' is not registered in multi-account profile registry"
            logger.critical(msg)
            self.control_plane.report_subsystem_state("multi_account_portfolio", SafetyState.HARD_HALT, msg)
            raise CrossAccountLeakageException(msg)
        return self.accounts[account_id]

    def verify_zero_cross_account_leakage(self, source_account_id: str, target_account_id: str) -> bool:
        """
        Enforce strict zero cross-account leakage guard (6F-P2).
        Any attempt by source_account to read/modify target_account state raises CrossAccountLeakageException.
        """
        self.verify_account_registration(source_account_id)
        self.verify_account_registration(target_account_id)

        if source_account_id != target_account_id:
            msg = f"CROSS-ACCOUNT LEAKAGE ATTEMPT: Source account '{source_account_id}' attempted cross-boundary access to target account '{target_account_id}'"
            logger.critical(msg)
            self.accounts[source_account_id].state = AccountState.ISOLATED_HALT
            self.control_plane.report_subsystem_state("multi_account_portfolio", SafetyState.HARD_HALT, msg)
            raise CrossAccountLeakageException(msg)

        return True

    def calculate_account_exposure(self, account_id: str, projected_notional: float = 0.0) -> float:
        """Calculate per-account total exposure: Open Positions + Pending Reservations + Projected Notional."""
        acc = self.verify_account_registration(account_id)
        open_notional = sum(p.get("notional", p.get("quantity", 0) * p.get("price", 0)) for p in self._open_positions[account_id].values())
        reserved_notional = sum(r.reserved_notional for r in self._active_reservations.values() if r.account_id == account_id)
        return open_notional + reserved_notional + projected_notional

    def calculate_portfolio_aggregate_exposure(self, projected_notional: float = 0.0) -> float:
        """Calculate portfolio-wide aggregate exposure across all active registered accounts (6F-P4)."""
        total_open = sum(
            sum(p.get("notional", p.get("quantity", 0) * p.get("price", 0)) for p in acc_positions.values())
            for acc_positions in self._open_positions.values()
        )
        total_reserved = sum(r.reserved_notional for r in self._active_reservations.values())
        return total_open + total_reserved + projected_notional

    def verify_and_reserve_atomic_exposure(self, account_id: str, order_intent_id: str, symbol: str, notional: float) -> PortfolioReservation:
        """
        Atomic Dual-Scope Reservation Engine (6F-P5 / 6F-P5A).
        Atomically verifies:
        1. Per-account limit: Account Exposure + notional <= $1,000 (6F-P3)
        2. Portfolio limit: Portfolio Aggregate Exposure + notional <= $3,000 (6F-P4)
        """
        acc = self.verify_account_registration(account_id)
        
        # Check if account is healthy
        if acc.state != AccountState.HEALTHY or self.portfolio_master_halted:
            msg = f"ACCOUNT HALTED: Account '{account_id}' is in state '{acc.state.name}' and cannot reserve exposure"
            logger.warning(msg)
            raise AccountHaltedException(msg)

        # 1. Per-account ceiling check ($1,000)
        acc_exp = self.calculate_account_exposure(account_id, notional)
        if acc_exp > acc.capital_ceiling:
            msg = f"ACCOUNT CEILING BREACH: Account '{account_id}' exposure (${acc_exp:.2f}) exceeds per-account limit (${acc.capital_ceiling:.2f})"
            logger.critical(msg)
            acc.state = AccountState.ISOLATED_HALT
            raise PortfolioCeilingExceededException(msg)

        # 2. Portfolio aggregate ceiling check ($3,000)
        port_exp = self.calculate_portfolio_aggregate_exposure(notional)
        if port_exp > self.PORTFOLIO_AGGREGATE_CEILING:
            msg = f"PORTFOLIO CEILING BREACH: Aggregate portfolio exposure (${port_exp:.2f}) exceeds ceiling (${self.PORTFOLIO_AGGREGATE_CEILING:.2f})"
            logger.critical(msg)
            self.control_plane.report_subsystem_state("multi_account_portfolio", SafetyState.HARD_HALT, msg)
            raise PortfolioCeilingExceededException(msg)

        # Atomic reservation (6F-P5A)
        res_id = f"res_port_{uuid.uuid4().hex[:8]}"
        res = PortfolioReservation(
            reservation_id=res_id,
            account_id=account_id,
            order_intent_id=order_intent_id,
            symbol=symbol,
            reserved_notional=notional
        )
        self._active_reservations[order_intent_id] = res

        self.audit_logger.append_audit_event("ATOMIC_PORTFOLIO_RESERVATION_CREATED", {
            "account_id": account_id,
            "reservation_id": res_id,
            "order_intent_id": order_intent_id,
            "reserved_notional": notional,
            "account_total_exposure": acc_exp,
            "portfolio_total_exposure": port_exp
        })

        return res

    def check_per_account_daily_loss_limit(self, account_id: str, unrealized_pnl: float = 0.0, fees: float = 0.0) -> bool:
        """
        Enforce per-account daily loss limit ($100 max loss) and Account Failure Isolation (6F-P10).
        Loss in Account A isolates Account A without contaminating healthy Account B.
        """
        acc = self.verify_account_registration(account_id)
        acc.unrealized_pnl = unrealized_pnl
        acc.fees_total += fees
        total_pnl = acc.realized_pnl + acc.unrealized_pnl - acc.fees_total

        if total_pnl <= -acc.daily_loss_limit:
            msg = f"ACCOUNT DAILY LOSS BREACH: Account '{account_id}' cumulative loss (-${abs(total_pnl):.2f}) reached or exceeded limit (-${acc.daily_loss_limit:.2f})"
            logger.critical(msg)
            
            # Account Failure Isolation (6F-P10): Isolate ONLY target account
            acc.state = AccountState.ISOLATED_HALT
            
            # Clear target account active reservations
            to_remove = [intent_id for intent_id, r in self._active_reservations.items() if r.account_id == account_id]
            for intent_id in to_remove:
                del self._active_reservations[intent_id]

            self.audit_logger.append_audit_event("ACCOUNT_ISOLATED_ON_DAILY_LOSS", {
                "account_id": account_id,
                "cumulative_loss": abs(total_pnl),
                "limit": acc.daily_loss_limit
            })
            return False

        return True

    def reconcile_account_positions(self, account_id: str, broker_positions: Dict[str, Any]) -> bool:
        """
        Per-account dual position reconciliation (6F-P6).
        Mismatch sets target account state to RECONCILIATION_LOCK without halting other healthy accounts.
        """
        acc = self.verify_account_registration(account_id)
        int_positions = self._open_positions[account_id]
        
        mismatches = []
        for symbol, int_pos in int_positions.items():
            brk_pos = broker_positions.get(symbol)
            if not brk_pos or float(int_pos.get("quantity", 0)) != float(brk_pos.get("quantity", 0)):
                mismatches.append(f"Position mismatch for {symbol}")

        if mismatches:
            msg = f"ACCOUNT RECONCILIATION MISMATCH for '{account_id}': {', '.join(mismatches)}"
            logger.critical(msg)
            acc.state = AccountState.RECONCILIATION_LOCK
            return False

        return True

    def reconcile_portfolio_aggregate_positions(self, broker_all_accounts_positions: Dict[str, Dict[str, Any]]) -> bool:
        """
        Portfolio aggregate reconciliation across all active accounts (6F-P7).
        """
        all_passed = True
        for acc_id in self.accounts:
            brk_pos = broker_all_accounts_positions.get(acc_id, {})
            ok = self.reconcile_account_positions(acc_id, brk_pos)
            if not ok:
                all_passed = False
        return all_passed

    def check_portfolio_margin_utilization(self, total_used_margin: float, total_available_margin: float) -> bool:
        """
        Portfolio aggregate margin utilization monitor (30% max) (6F-P12).
        """
        pct = (total_used_margin / total_available_margin) * 100.0 if total_available_margin > 0 else 0.0
        if pct > self.PORTFOLIO_MARGIN_UTILIZATION_CEILING_PCT:
            msg = f"PORTFOLIO MARGIN BREACH: Aggregate margin utilization ({pct:.1f}%) exceeds limit ({self.PORTFOLIO_MARGIN_UTILIZATION_CEILING_PCT}%)"
            logger.warning(msg)
            self.control_plane.report_subsystem_state("multi_account_portfolio", SafetyState.HOLD, msg)
            return False
        return True

    def trigger_account_scoped_kill_switch(self, account_id: str, reason: str) -> Dict[str, Any]:
        """
        Account-scoped kill switch (6F-P9 / 6F-P10).
        Halts and isolates Account A while healthy Accounts B & C remain unaffected.
        """
        acc = self.verify_account_registration(account_id)
        acc.state = AccountState.EMERGENCY_KILLED
        
        # Clear account positions and reservations
        count_positions = len(self._open_positions[account_id])
        self._open_positions[account_id].clear()
        
        to_remove = [intent_id for intent_id, r in self._active_reservations.items() if r.account_id == account_id]
        for intent_id in to_remove:
            del self._active_reservations[intent_id]

        self.audit_logger.append_audit_event("ACCOUNT_SCOPED_KILL_SWITCH_EXECUTED", {
            "account_id": account_id,
            "reason": reason
        })

        return {
            "status": "ACCOUNT_KILLED",
            "account_id": account_id,
            "positions_flattened": count_positions,
            "other_accounts_healthy": [acc_id for acc_id, a in self.accounts.items() if acc_id != account_id and a.state == AccountState.HEALTHY]
        }

    def trigger_portfolio_master_kill_switch(self, reason: str) -> Dict[str, Any]:
        """
        Portfolio Master Kill Switch (6F-P9 / 6F-P13).
        Halts ALL registered accounts and clears all portfolio positions and reservations.
        """
        self.portfolio_master_halted = True
        self.control_plane.report_subsystem_state("multi_account_portfolio", SafetyState.EMERGENCY_KILL, reason)

        flattened_total = 0
        for acc_id, acc in self.accounts.items():
            acc.state = AccountState.EMERGENCY_KILLED
            flattened_total += len(self._open_positions[acc_id])
            self._open_positions[acc_id].clear()

        self._active_reservations.clear()

        self.audit_logger.append_audit_event("PORTFOLIO_MASTER_KILL_SWITCH_EXECUTED", {
            "reason": reason,
            "total_positions_flattened": flattened_total
        })

        return {
            "status": "PORTFOLIO_MASTER_KILL_COMPLETED",
            "reason": reason,
            "total_positions_flattened": flattened_total,
            "all_accounts_killed": True
        }
