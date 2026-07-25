# governance/secret_sanitizer.py
"""
Security & Secret Sanitizer for NexTrade (Sub-Phase 4N).
Sanitizes user-facing UI outputs, notifications, and safety centre logs to ensure zero HMAC keys,
credentials, tokens, or internal addresses leak to operator screens (Invariant 4N-P3).
"""
import re
from typing import Dict, Any, List


class SecretSanitizer:
    """
    Regex-based sanitizer stripping sensitive cryptographic keys and token strings.
    """

    # Patterns matching HMAC signatures, tokens, secrets, memory addresses
    PATTERNS = [
        (re.compile(r"hmac[_\-\w]*\s*[:=]\s*['\"]?([a-fA-F0-9]{32,64})['\"]?", re.IGNORECASE), "hmac_signature: [REDACTED_HMAC_KEY]"),
        (re.compile(r"token[_\-\w]*\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{12,64})['\"]?", re.IGNORECASE), "token_id: [REDACTED_TOKEN]"),
        (re.compile(r"secret[_\-\w]*\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE), "secret: [REDACTED_SECRET]"),
        (re.compile(r"0x[0-9a-fA-F]{8,16}"), "[REDACTED_ADDRESS]")
    ]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """
        Strips secrets and signatures from text strings (Invariant 4N-P3).
        """
        sanitized = text
        for pattern, replacement in cls.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitizes dictionary keys and string values.
        """
        clean_dict = {}
        for k, v in data.items():
            if any(term in k.lower() for term in ["hmac", "secret", "token", "password"]):
                clean_dict[k] = "[REDACTED_SENSITIVE_FIELD]"
            elif isinstance(v, str):
                clean_dict[k] = cls.sanitize_text(v)
            elif isinstance(v, dict):
                clean_dict[k] = cls.sanitize_dict(v)
            else:
                clean_dict[k] = v
        return clean_dict
