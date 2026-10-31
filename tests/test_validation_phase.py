"""Validation Phase track unit tests (fast, no broker)."""

from __future__ import annotations

import unittest

from research.validation_phase import (
    track_val_c_arass_repeatability,
    track_val_f_known_gaps,
)


class TestValidationPhaseTracks(unittest.TestCase):
    def test_val_c_arass_repeatable(self):
        r = track_val_c_arass_repeatability()
        self.assertTrue(r.ok, msg=r.issues)
        self.assertEqual(r.stats["run1"], r.stats["run2"])

    def test_val_f_known_gaps(self):
        r = track_val_f_known_gaps()
        self.assertTrue(r.ok, msg=r.issues)
        self.assertGreater(r.stats.get("total", 0), 0)


if __name__ == "__main__":
    unittest.main()
