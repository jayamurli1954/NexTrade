"""Tests for user-configurable day flatten policy + net charge projection."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from trading_app.paper_day_risk import day_flatten_reason, get_day_risk_limits
from trading_app.paper_day_risk_policy import (
    PaperDayRiskPolicy,
    build_day_limit_projection,
    configure_policy_path,
    load_policy,
    parse_policy_update,
    save_policy,
)


class TestPaperDayRiskPolicy(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._path = os.path.join(self._tmpdir.name, "paper_day_risk_policy.json")
        configure_policy_path(self._path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_defaults(self):
        pol = load_policy()
        self.assertEqual(pol.profit_target_inr, 1500.0)
        self.assertEqual(pol.loss_limit_inr, 2000.0)

    def test_save_and_reload(self):
        pol = PaperDayRiskPolicy(profit_target_inr=1200, loss_limit_inr=800)
        save_policy(pol)
        loaded = load_policy()
        self.assertEqual(loaded.profit_target_inr, 1200.0)
        self.assertEqual(loaded.loss_limit_inr, 800.0)
        self.assertTrue(os.path.exists(self._path))

    def test_parse_accepts_signed_inputs(self):
        merged = parse_policy_update({"profit_target_inr": "+2500", "loss_limit_inr": "-1800"})
        self.assertEqual(merged.profit_target_inr, 2500.0)
        self.assertEqual(merged.loss_limit_inr, 1800.0)

    def test_get_day_risk_limits_reads_policy(self):
        save_policy(PaperDayRiskPolicy(profit_target_inr=900, loss_limit_inr=1100))
        lim = get_day_risk_limits()
        self.assertEqual(lim.profit_target_inr, 900.0)
        self.assertEqual(lim.loss_limit_inr, 1100.0)
        self.assertEqual(day_flatten_reason(900, lim), "DAY_PROFIT_TARGET")

    def test_net_projection_subtracts_charges(self):
        trades = [
            {
                "timestamp": "2026-08-04 10:00:00",
                "entry_price": 100.0,
                "exit_price": 110.0,
                "quantity": 100,
                "pnl": 1000.0,
            }
        ]
        open_pos = [
            {
                "entry_price_raw": 200.0,
                "ltp": 205.0,
                "quantity": 50,
                "status": "OPEN",
            }
        ]
        pol = PaperDayRiskPolicy(profit_target_inr=1500, loss_limit_inr=2000)
        proj = build_day_limit_projection(
            policy=pol,
            trades=trades,
            open_positions=open_pos,
            today="2026-08-04",
        )
        self.assertEqual(proj["profit_target_gross_inr"], 1500.0)
        self.assertEqual(proj["loss_limit_gross_inr"], 2000.0)
        self.assertGreater(proj["est_total_charges_inr"], 0)
        self.assertLess(proj["net_profit_if_target_hit_inr"], 1500.0)
        self.assertLess(proj["net_loss_if_limit_hit_inr"], -2000.0)

    def test_persisted_json_shape(self):
        saved = save_policy(PaperDayRiskPolicy(profit_target_inr=1500, loss_limit_inr=2000))
        with open(self._path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.assertIn("charges", raw)
        self.assertEqual(raw["profit_target_inr"], saved.profit_target_inr)


if __name__ == "__main__":
    unittest.main()
