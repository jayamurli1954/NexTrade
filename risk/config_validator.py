# risk/config_validator.py
"""
Pure Configuration Safety & Schema Validator for NexTrade.
Enforces strict schema rules, non-negative bounds, range checks, cross-field consistency,
and strict unknown-field rejection for RiskLimits and KillSwitch state configurations.
"""
import math
from typing import Dict, Any, Union, Set
from contracts.risk import RiskLimits


KNOWN_RISK_LIMITS_FIELDS: Set[str] = {
    "min_risk_per_trade_pct",
    "default_risk_per_trade_pct",
    "max_risk_per_trade_pct",
    "max_daily_loss_amount",
    "max_open_positions",
    "max_symbol_exposure_pct",
    "max_sector_exposure_pct",
}

KNOWN_KILL_SWITCH_STATE_FIELDS: Set[str] = {
    "schema_version",
    "global_active",
    "global_reason",
    "active_switches",
    "circuit_breakers",
    "last_updated",
    "audit_history",
}


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""
    pass


class ConfigValidator:
    """
    Pure validation component for NexTrade risk configurations.
    """

    @staticmethod
    def validate_risk_limits(config: Union[RiskLimits, Dict[str, Any]]) -> RiskLimits:
        """
        Validate RiskLimits configuration dictionary or dataclass object.
        Enforces type safety, range bounds, cross-field consistency, and unknown-field rejection.
        """
        if isinstance(config, dict):
            # Strict unknown field check
            unknown_fields = set(config.keys()) - KNOWN_RISK_LIMITS_FIELDS
            if unknown_fields:
                raise ConfigValidationError(
                    f"Unknown field(s) in RiskLimits configuration: {sorted(list(unknown_fields))}"
                )

            try:
                obj = RiskLimits(**config)
            except Exception as e:
                raise ConfigValidationError(f"Invalid RiskLimits parameter initialization: {str(e)}") from e
        elif isinstance(config, RiskLimits):
            obj = config
        else:
            raise ConfigValidationError(f"Expected RiskLimits or dict, got {type(config).__name__}")

        # Range & Bound Checks
        if math.isnan(obj.min_risk_per_trade_pct) or math.isinf(obj.min_risk_per_trade_pct) or obj.min_risk_per_trade_pct <= 0:
            raise ConfigValidationError(f"min_risk_per_trade_pct must be positive float, got {obj.min_risk_per_trade_pct}")

        if math.isnan(obj.default_risk_per_trade_pct) or math.isinf(obj.default_risk_per_trade_pct) or obj.default_risk_per_trade_pct <= 0:
            raise ConfigValidationError(f"default_risk_per_trade_pct must be positive float, got {obj.default_risk_per_trade_pct}")

        if math.isnan(obj.max_risk_per_trade_pct) or math.isinf(obj.max_risk_per_trade_pct) or obj.max_risk_per_trade_pct <= 0:
            raise ConfigValidationError(f"max_risk_per_trade_pct must be positive float, got {obj.max_risk_per_trade_pct}")

        if not (0.0 < obj.min_risk_per_trade_pct <= obj.default_risk_per_trade_pct <= obj.max_risk_per_trade_pct):
            raise ConfigValidationError(
                f"Risk trade bounds violated: min({obj.min_risk_per_trade_pct}) <= default({obj.default_risk_per_trade_pct}) <= max({obj.max_risk_per_trade_pct})"
            )

        if math.isnan(obj.max_daily_loss_amount) or math.isinf(obj.max_daily_loss_amount) or obj.max_daily_loss_amount <= 0:
            raise ConfigValidationError(f"max_daily_loss_amount must be positive float, got {obj.max_daily_loss_amount}")

        if obj.max_open_positions <= 0:
            raise ConfigValidationError(f"max_open_positions must be positive integer, got {obj.max_open_positions}")

        if math.isnan(obj.max_symbol_exposure_pct) or math.isinf(obj.max_symbol_exposure_pct) or obj.max_symbol_exposure_pct <= 0:
            raise ConfigValidationError(f"max_symbol_exposure_pct must be positive float, got {obj.max_symbol_exposure_pct}")

        if math.isnan(obj.max_sector_exposure_pct) or math.isinf(obj.max_sector_exposure_pct) or obj.max_sector_exposure_pct <= 0:
            raise ConfigValidationError(f"max_sector_exposure_pct must be positive float, got {obj.max_sector_exposure_pct}")

        # Cross-field consistency check: Symbol cap cannot exceed Sector cap
        if obj.max_symbol_exposure_pct > obj.max_sector_exposure_pct:
            raise ConfigValidationError(
                f"Cross-field exposure violation: max_symbol_exposure_pct ({obj.max_symbol_exposure_pct}%) > max_sector_exposure_pct ({obj.max_sector_exposure_pct}%)"
            )

        return obj

    @staticmethod
    def validate_kill_switch_state(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate KillSwitchManager persistent state dictionary schema.
        Enforces schema versioning, top-level field validation, and unknown field rejection.
        """
        if not isinstance(state, dict):
            raise ConfigValidationError(f"KillSwitch state must be a dict, got {type(state).__name__}")

        # Strict unknown field check
        unknown_fields = set(state.keys()) - KNOWN_KILL_SWITCH_STATE_FIELDS
        if unknown_fields:
            raise ConfigValidationError(
                f"Unknown field(s) in KillSwitch state schema: {sorted(list(unknown_fields))}"
            )

        schema_ver = state.get("schema_version")
        if schema_ver != 1:
            raise ConfigValidationError(f"Unsupported schema_version: expected 1, got {schema_ver}")

        if not isinstance(state.get("global_active", False), bool):
            raise ConfigValidationError("global_active must be a boolean")

        if not isinstance(state.get("active_switches", {}), dict):
            raise ConfigValidationError("active_switches must be a dict")

        if not isinstance(state.get("circuit_breakers", {}), dict):
            raise ConfigValidationError("circuit_breakers must be a dict")

        return state
