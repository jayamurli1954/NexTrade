"""
Single-owner lock for the options paper lane, so the dashboard and the scheduled task never run it twice
(two runs would mean two Angel logins and duplicate paper ledgers).

The owner refreshes the lock file on every poll (heartbeat). A lock not refreshed for ``STALE_SEC``
is treated as abandoned (crashed process, closed laptop) and can be taken over.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from trading_app.options_paper.ledger import DEFAULT_DIR

LOCK_PATH = DEFAULT_DIR / "runner.lock"
STALE_SEC = 120.0


class LaneLock:
    def __init__(self, owner: str, path: Path = LOCK_PATH, stale_sec: float = STALE_SEC):
        self.owner = owner
        self.path = Path(path)
        self.stale_sec = stale_sec
        self.held = False

    def current(self) -> Optional[dict]:
        """Live lock info, or None if free/stale."""
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - float(info.get("heartbeat", 0)) > self.stale_sec:
            return None
        return info

    def acquire(self) -> bool:
        cur = self.current()
        if cur is not None and not (cur.get("pid") == os.getpid() and cur.get("owner") == self.owner):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write(started=time.time())
        self.held = True
        return True

    def heartbeat(self) -> None:
        if self.held:
            self._write()

    def release(self) -> None:
        if self.held:
            cur = self.current()
            if cur is None or (cur.get("pid") == os.getpid() and cur.get("owner") == self.owner):
                try:
                    self.path.unlink()
                except OSError:
                    pass
            self.held = False

    def _write(self, started: Optional[float] = None) -> None:
        try:
            prev = json.loads(self.path.read_text(encoding="utf-8")) if started is None else {}
        except (OSError, ValueError):
            prev = {}
        info = {"owner": self.owner, "pid": os.getpid(), "started": started or prev.get("started", time.time()),
                "heartbeat": time.time()}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(info), encoding="utf-8")
        tmp.replace(self.path)
