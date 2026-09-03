"""Angel scrip-master token load: cache, parse, fallback corrections."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ui_new.connection_manager import ConnectionManager


class TestAngelScripTokenLoad(unittest.TestCase):
    def setUp(self):
        self.cm = ConnectionManager.__new__(ConnectionManager)
        self.cm.token_map = {}
        self._tmpdir = tempfile.mkdtemp(prefix="nextrade_scrip_")

    def test_parse_lodha_eq_uses_live_token(self):
        rows = [
            {"token": "3220", "symbol": "LODHA-EQ", "name": "LODHA", "exch_seg": "NSE"},
            {"token": "772", "symbol": "DABUR-EQ", "name": "DABUR", "exch_seg": "NSE"},
        ]
        parsed = ConnectionManager._parse_scrip_master_items(rows)
        self.assertEqual(parsed["NSE:LODHA"], "3220")
        self.assertEqual(parsed["NSE:DABUR"], "772")

    def test_fallback_tokens_use_current_angel_ids(self):
        self.cm._load_fallback_tokens()
        self.assertEqual(self.cm.token_map["NSE:LODHA"], "3220")
        self.assertEqual(self.cm.token_map["NSE:DABUR"], "772")
        self.assertNotEqual(self.cm.token_map["NSE:LODHA"], "25197")
        self.assertNotEqual(self.cm.token_map["NSE:DABUR"], "768")

    def test_load_prefers_fresh_disk_cache(self):
        cache_file = Path(self._tmpdir) / "angel_scrip_token_map.json"
        cache_file.write_text(
            json.dumps({"tokens": {"NSE:LODHA": "3220", "NSE:RELIANCE": "2885"}}),
            encoding="utf-8",
        )
        with patch("ui_new.connection_manager._SCRIP_TOKEN_CACHE_PATH", cache_file):
            with patch.object(self.cm, "_download_scrip_master") as download:
                ok = self.cm.load_symbol_tokens()
                self.assertTrue(ok)
                self.assertEqual(self.cm.token_map["NSE:LODHA"], "3220")
                download.assert_not_called()

    def test_download_failure_uses_stale_cache_before_fallback(self):
        cache_file = Path(self._tmpdir) / "angel_scrip_token_map.json"
        cache_file.write_text(json.dumps({"tokens": {"NSE:LODHA": "3220"}}), encoding="utf-8")
        old = time.time() - (25 * 3600)
        os.utime(cache_file, (old, old))
        with patch("ui_new.connection_manager._SCRIP_TOKEN_CACHE_PATH", cache_file):
            with patch.object(
                self.cm, "_download_scrip_master", side_effect=RuntimeError("timeout")
            ):
                ok = self.cm.load_symbol_tokens()
                self.assertTrue(ok)
                self.assertEqual(self.cm.token_map["NSE:LODHA"], "3220")

    def test_download_and_persist(self):
        cache_file = Path(self._tmpdir) / "angel_scrip_token_map.json"
        rows = [{"token": "3220", "symbol": "LODHA-EQ", "name": "LODHA", "exch_seg": "NSE"}]
        with patch("ui_new.connection_manager._SCRIP_TOKEN_CACHE_PATH", cache_file):
            with patch.object(self.cm, "_download_scrip_master", return_value=rows):
                with patch.object(self.cm, "_load_token_map_from_disk", return_value=(None, None)):
                    ok = self.cm.load_symbol_tokens()
        self.assertTrue(ok)
        self.assertEqual(self.cm.token_map["NSE:LODHA"], "3220")
        self.assertTrue(cache_file.is_file())
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["tokens"]["NSE:LODHA"], "3220")


if __name__ == "__main__":
    unittest.main()
