# tests/test_config_validator.py
"""
Unit Test Suite for NexTrade ConfigValidator (Sub-Phase 2H-1).
Verifies strict schema validation, type checks, non-negative bounds, cross-field consistency,
and strict unknown-field rejection for RiskLimits and KillSwitch state configurations.
"""
import unittest
from contracts.risk import RiskLimits
from risk.config_validator import ConfigValidator, ConfigValidationError


class TestConfigValidator(unittest.TestCase):

    def test_valid_risk_limits_dataclass(self):
        limits = RiskLimits(
            min_risk_per_trade_pct=0.25,
            default_risk_per_trade_pct=0.50,
            max_risk_per_trade_pct=1.00,
            max_daily_loss_amount=5000.0,
            max_open_positions=5,
            max_symbol_exposure_pct=20.0,
            max_sector_exposure_pct=40.0
        )
        res = ConfigValidator.validate_risk_limits(limits)
        self.assertEqual(res, limits)

    def test_valid_risk_limits_dict(self):
        cfg = {
            "min_risk_per_trade_pct": 0.25,
            "default_risk_per_trade_pct": 0.50,
            "max_risk_per_trade_pct": 1.00,
            "max_daily_loss_amount": 5000.0,
            "max_open_positions": 5,
            "max_symbol_exposure_pct": 20.0,
            "max_sector_exposure_pct": 40.0
        }
        res = ConfigValidator.validate_risk_limits(cfg)
        self.assertEqual(res.max_symbol_exposure_pct, 20.0)

    def test_unknown_field_rejection_in_risk_limits(self):
        cfg_typo = {
            "min_risk_per_trade_pct": 0.25,
            "default_risk_per_trade_pct": 0.50,
            "max_risk_per_trade_pct": 1.00,
            "max_daily_loss_amount": 5000.0,
            "max_open_positions": 5,
            "max_symbol_exposure_pct": 20.0,
            "max_sector_exposure_pct": 40.0,
            "max_portfolio_rsk": 100.0  # Typo field must raise ConfigValidationError
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            ConfigValidator.validate_risk_limits(cfg_typo)
        self.assertIn("Unknown field(s)", str(ctx.exception))
        self.assertIn("max_portfolio_rsk", str(ctx.exception))

    def test_cross_field_exposure_violation(self):
        # Symbol cap (50%) exceeds Sector cap (40%) -> Must fail
        cfg_bad_exposure = {
            "min_risk_per_trade_pct": 0.25,
            "default_risk_per_trade_pct": 0.50,
            "max_risk_per_trade_pct": 1.00,
            "max_daily_loss_amount": 5000.0,
            "max_open_positions": 5,
            "max_symbol_exposure_pct": 50.0,
            "max_sector_exposure_pct": 40.0
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            ConfigValidator.validate_risk_limits(cfg_bad_exposure)
        self.assertIn("Cross-field exposure violation", str(ctx.exception))

    def test_negative_or_nan_limits(self):
        cfg_neg = {
            "min_risk_per_trade_pct": 0.25,
            "default_risk_per_trade_pct": 0.50,
            "max_risk_per_trade_pct": 1.00,
            "max_daily_loss_amount": -1000.0,  # Invalid
            "max_open_positions": 5,
            "max_symbol_exposure_pct": 20.0,
            "max_sector_exposure_pct": 40.0
        }
        with self.assertRaises(ConfigValidationError):
            ConfigValidator.validate_risk_limits(cfg_neg)

    def test_valid_kill_switch_state(self):
        state = {
            "schema_version": 1,
            "global_active": False,
            "global_reason": None,
            "active_switches": {},
            "circuit_breakers": {},
            "last_updated": "2026-07-24T12:00:00Z",
            "audit_history": []
        }
        res = ConfigValidator.validate_kill_switch_state(state)
        self.assertEqual(res, state)

    def test_unknown_field_rejection_in_kill_switch_state(self):
        state_typo = {
            "schema_version": 1,
            "global_active": False,
            "active_switches": {},
            "circuit_breakers": {},
            "unauthorized_override": True  # Unknown field
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            ConfigValidator.validate_kill_switch_state(state_typo)
        self.assertIn("Unknown field(s)", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
