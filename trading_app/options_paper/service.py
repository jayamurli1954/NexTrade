"""
In-dashboard controller for the options paper lane (OPT-PAPER). Paper only — never places orders.

Runs the same strategies as ``runner.py`` in a background thread inside the dashboard process, reusing
the dashboard's Angel connection (no second login). Shares the single-owner lock with the scheduled
task, so only one of them runs the lane on a given day.
"""

from __future__ import annotations

import csv
import json
import logging
import threading
import time
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from trading_app.options_paper.ledger import DEFAULT_DIR
from trading_app.options_paper.lock import LaneLock

log = logging.getLogger("options_paper.service")

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "options_paper.json"
EDITABLE_KEYS = {"enabled"}  # the dashboard only toggles strategies on/off; edit JSON for parameters
AUTO_START_AT = dtime(9, 0)      # dashboard starts the lane itself from this time on weekdays...
AUTO_START_UNTIL = dtime(14, 30)  # ...until this time (later starts would skip every strategy anyway)


class OptionsPaperService:
    def __init__(self, config_path: Path = CONFIG_PATH, log_dir: Path = DEFAULT_DIR,
                 connect: Optional[Callable] = None, quote_source_factory: Optional[Callable] = None):
        self.config_path = Path(config_path)
        self.log_dir = Path(log_dir)
        self._connect = connect                  # -> (smart_api, chain); default uses dashboard connection
        self._qs_factory = quote_source_factory  # smart_api -> QuoteSource
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = LaneLock("dashboard", path=self.log_dir / "runner.lock")
        self._strategies: List[Any] = []
        self._last_quotes: Dict[str, Any] = {}
        self._error: Optional[str] = None
        self._started_at: Optional[str] = None
        self._mx = threading.Lock()
        self._started_day: Optional[date] = None   # set by any successful start; auto-start never repeats a day
        self._auto_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ config
    def load_config(self) -> Dict[str, Any]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def auto_start_enabled(self) -> bool:
        try:
            return bool(self.load_config().get("auto_start", False))
        except (OSError, ValueError):
            return False

    def set_auto_start(self, on: bool) -> Dict[str, Any]:
        cfg = self.load_config()
        cfg["auto_start"] = bool(on)
        self._save_config(cfg)
        return cfg

    def _save_config(self, cfg: Dict[str, Any]) -> None:
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.config_path)

    def set_enabled(self, name: str, enabled: bool) -> Dict[str, Any]:
        cfg = self.load_config()
        hit = False
        for s in cfg.get("strategies", []):
            if s.get("name") == name:
                s["enabled"] = bool(enabled)
                hit = True
        if not hit:
            raise KeyError(f"No strategy named {name!r}")
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.config_path)
        return cfg

    # ------------------------------------------------------------------ control
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> Dict[str, Any]:
        with self._mx:
            if self.running:
                return {"success": False, "message": "Already running in this dashboard."}
            if date.today().weekday() >= 5:
                return {"success": False, "message": "Weekend — markets closed."}
            if not self._lock.acquire():
                return {"success": False,
                        "message": f"Options paper lane is already running elsewhere ({self._lock.current()}). "
                                   "Wait for it to finish or stop it there."}
            self._stop.clear()
            self._error = None
            self._started_at = datetime.now().isoformat(timespec="seconds")
            self._started_day = date.today()
            self._thread = threading.Thread(target=self._run, name="options-paper-lane", daemon=True)
            self._thread.start()
            return {"success": True, "message": "Options paper lane started (paper only, no orders)."}

    # ------------------------------------------------------------------ auto-start
    def auto_start_tick(self, now: datetime) -> Optional[Dict[str, Any]]:
        """One check of the daily auto-start rule; returns start() result if it fired."""
        if not self.auto_start_enabled() or now.weekday() >= 5:
            return None
        if not (AUTO_START_AT <= now.time() < AUTO_START_UNTIL):
            return None
        if self.running or self._started_day == now.date() or self._lock.current() is not None:
            return None  # already ran / user stopped it today / another owner holds the lane
        res = self.start()
        log.info("Options paper auto-start: %s", res.get("message"))
        return res

    def start_auto_scheduler(self, check_every: float = 30.0, clock=datetime.now, sleep=time.sleep) -> None:
        """Background thread: the dashboard starts the lane itself each weekday morning (one Angel login)."""
        if self._auto_thread is not None and self._auto_thread.is_alive():
            return

        def loop():
            while True:
                try:
                    self.auto_start_tick(clock())
                except Exception:
                    log.exception("Options paper auto-start check failed")
                sleep(check_every)

        self._auto_thread = threading.Thread(target=loop, name="options-paper-autostart", daemon=True)
        self._auto_thread.start()

    def stop(self) -> Dict[str, Any]:
        if not self.running:
            return {"success": False, "message": "Not running."}
        self._stop.set()
        return {"success": True, "message": "Stopping — open paper legs will be squared off at current quotes."}

    def _default_connect(self):
        from ui_new.connection_manager import get_connection_manager
        from trading_app.options_paper.instruments import OptionChainIndex

        cm = get_connection_manager()
        if not cm.is_connected or not cm.smart_api:
            if not cm.connect_broker():
                raise RuntimeError(f"Angel login failed: {getattr(cm, 'last_connection_error', None)}")
        cm.ensure_tokens_loaded()
        return cm.smart_api, OptionChainIndex.from_token_map(cm.token_map)

    def _run(self) -> None:
        from trading_app.options_paper.quotes import AngelQuoteSource
        from trading_app.options_paper.runner import build_model_pricer, build_strategies, run_strategies

        try:
            cfg = self.load_config()
            specs = [s for s in cfg.get("strategies", []) if s.get("enabled", True)]
            poll = float(cfg.get("poll_seconds", 5.0))
            smart_api, chain = (self._connect or self._default_connect)()
            today = date.today()
            strategies = build_strategies(specs, chain, today, build_model_pricer(), log_dir=self.log_dir)
            with self._mx:
                self._strategies = strategies
            if not strategies:
                self._error = "No enabled strategies could be loaded (check config / scrip master)."
                return
            qs = (self._qs_factory or AngelQuoteSource)(smart_api)

            def on_cycle(quotes):
                self._lock.heartbeat()
                with self._mx:
                    self._last_quotes = dict(quotes or {})

            run_strategies(strategies, qs, today, poll, sleep=lambda sec: self._stop.wait(sec),
                           should_stop=self._stop.is_set, on_cycle=on_cycle)
        except Exception as exc:  # surface in the UI rather than killing the dashboard
            log.exception("Options paper lane failed")
            self._error = str(exc)
        finally:
            self._lock.release()

    # ------------------------------------------------------------------ status
    def status(self) -> Dict[str, Any]:
        with self._mx:
            strategies = list(self._strategies)
            quotes = dict(self._last_quotes)
        cfg = {}
        try:
            cfg = self.load_config()
        except (OSError, ValueError) as exc:
            self._error = self._error or f"config: {exc}"
        live = [self._strategy_status(s, quotes) for s in strategies]
        other_owner = None
        if not self.running:
            cur = self._lock.current()
            if cur:
                other_owner = cur
        return {
            "running": self.running,
            "started_at": self._started_at,
            "error": self._error,
            "running_elsewhere": other_owner,
            "mode": "PAPER_NO_ORDERS",
            "auto_start": bool(cfg.get("auto_start", False)),
            "auto_start_window": f"{AUTO_START_AT:%H:%M}-{AUTO_START_UNTIL:%H:%M} weekdays",
            "config": [{k: s.get(k) for k in ("name", "type", "enabled", "symbol", "entry", "exit", "sl_pct",
                                               "expiry_day_only", "target_premium", "hedge_premium")}
                       for s in cfg.get("strategies", [])],
            "strategies": live,
            "today_events": self.today_events(limit=60),
            "summary": self.summary_rows(limit=30),
        }

    @staticmethod
    def _strategy_status(s, quotes) -> Dict[str, Any]:
        legs = []
        for lg in s.s.legs:
            q = quotes.get(lg.token)
            mark = lg.exit if not lg.open else (q.ltp if q else None)
            legs.append({"symbol": lg.symbol, "side": "SHORT" if lg.side < 0 else "LONG", "entry": lg.entry,
                         "stop": lg.stop, "ltp": q.ltp if q else None, "exit": lg.exit, "why": lg.exit_reason,
                         "pnl_points": None if mark is None or not lg.entry else round((mark - lg.entry) * lg.side, 2)})
        mtm = None
        try:
            mtm = s._mtm(quotes) if s.s.legs else None
        except Exception:
            pass
        return {"name": s.name, "phase": s.s.phase, "reason": s.s.exit_reason, "expiry": s.s.expiry,
                "atm": s.s.atm, "mtm": None if mtm is None else round(mtm, 2), "legs": legs}

    def today_events(self, limit: int = 60) -> List[Dict[str, Any]]:
        out = []
        for path in sorted(self.log_dir.glob(f"{date.today().isoformat()}_*_events.jsonl")):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
            except OSError:
                continue
        out.sort(key=lambda e: e.get("ts", ""))
        return out[-limit:]

    def summary_rows(self, limit: int = 30) -> List[Dict[str, Any]]:
        path = self.log_dir / "summary.csv"
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return rows[-limit:][::-1]


_SERVICE: Optional[OptionsPaperService] = None


def get_service() -> OptionsPaperService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = OptionsPaperService()
    return _SERVICE


_HTML_PATH = Path(__file__).with_name("options_paper.html")


def render_options_html() -> str:
    return _HTML_PATH.read_text(encoding="utf-8")
