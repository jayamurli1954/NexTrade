"""
OIE-001 — Redact Angel One secrets from logs (JWT, API keys, feed tokens).

Installs logging Filters on SmartAPI / logzero / root loggers so exception
tracebacks and request header dumps never leak Authorization / X-PrivateKey.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(Authorization['\"]?\s*[:=]\s*['\"]?Bearer\s+)([A-Za-z0-9_\-\.]+)"), r"\1[REDACTED_JWT]"),
    (re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9_\-\.]{20,})"), r"\1[REDACTED_JWT]"),
    (re.compile(r"(?i)(X-PrivateKey['\"]?\s*[:=]\s*['\"]?)([^'\"\s,\}]+)"), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(api_key['\"]?\s*[:=]\s*['\"]?)([^'\"\s,\}]+)"), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(feed[_-]?token['\"]?\s*[:=]\s*['\"]?)([^'\"\s,\}]+)"), r"\1[REDACTED_FEED_TOKEN]"),
    (re.compile(r"(?i)(jwtToken['\"]?\s*[:=]\s*['\"]?)([^'\"\s,\}]+)"), r"\1[REDACTED_JWT]"),
    (re.compile(r"(?i)(eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})"), "[REDACTED_JWT]"),
]


def redact_secrets(text: str) -> str:
    """Return text with Angel credentials replaced by placeholders."""
    if not text:
        return text
    out = str(text)
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


class AngelSecretRedactionFilter(logging.Filter):
    """Logging filter — mutates record msg/args to strip secrets."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact_secrets(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        redact_secrets(a) if isinstance(a, str) else a for a in record.args
                    )
            # Also scrub already-formatted message path used by some handlers
            if hasattr(record, "message") and isinstance(record.message, str):
                record.message = redact_secrets(record.message)
        except Exception:
            pass
        return True


_INSTALLED = False


def install_angel_secret_redaction(extra_logger_names: Optional[Iterable[str]] = None) -> None:
    """Idempotent: attach redaction filter to SmartAPI-related loggers + root."""
    global _INSTALLED
    if _INSTALLED:
        return
    filt = AngelSecretRedactionFilter()
    names = [
        "",
        "SmartApi",
        "smartConnect",
        "smartWebSocketV2",
        "AngelMarketDataBridge",
        "NexTradeUnifiedWebApp",
        "logzero",
        "logzero_default",
    ]
    if extra_logger_names:
        names.extend(extra_logger_names)
    for name in names:
        lg = logging.getLogger(name)
        # Avoid duplicate filters
        if not any(isinstance(f, AngelSecretRedactionFilter) for f in lg.filters):
            lg.addFilter(filt)
        for h in lg.handlers:
            if not any(isinstance(f, AngelSecretRedactionFilter) for f in h.filters):
                h.addFilter(filt)
    # logzero often uses its own default logger
    try:
        import logzero
        z = logzero.logger
        if not any(isinstance(f, AngelSecretRedactionFilter) for f in z.filters):
            z.addFilter(filt)
        for h in getattr(z, "handlers", []) or []:
            if not any(isinstance(f, AngelSecretRedactionFilter) for f in h.filters):
                h.addFilter(filt)
    except Exception:
        pass
    _INSTALLED = True
