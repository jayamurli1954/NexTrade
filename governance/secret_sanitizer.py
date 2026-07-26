# governance/secret_sanitizer.py
"""
Security & Secret Sanitizer for NexTrade (Sub-Phase 4N & Phase 5C).
Sanitizes user-facing UI outputs, notifications, logging streams, subprocess environments,
and safety centre logs to ensure zero secrets, API keys, credentials, tokens, or private keys leak.
"""
import re
import logging
from typing import Dict, Any, List


class SecretSanitizer:
    """
    Regex-based sanitizer stripping sensitive cryptographic keys, API credentials,
    OAuth tokens, private keys, database URLs, and token strings across text and dictionaries.
    """

    # Extended patterns matching HMAC signatures, tokens, secrets, private keys, connection strings
    PATTERNS = [
        (re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE), "[REDACTED_PRIVATE_KEY]"),
        (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,256}", re.IGNORECASE), "Bearer [REDACTED_OAUTH_TOKEN]"),
        (re.compile(r"api[_\-]?key\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,128})['\"]?", re.IGNORECASE), "api_key: [REDACTED_API_KEY]"),
        (re.compile(r"hmac[_\-\w]*\s*[:=]\s*['\"]?([a-fA-F0-9]{32,64})['\"]?", re.IGNORECASE), "hmac_signature: [REDACTED_HMAC_KEY]"),
        (re.compile(r"token[_\-\w]*\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{12,64})['\"]?", re.IGNORECASE), "token_id: [REDACTED_TOKEN]"),
        (re.compile(r"secret[_\-\w]*\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE), "secret: [REDACTED_SECRET]"),
        (re.compile(r"password[_\-\w]*\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE), "password: [REDACTED_PASSWORD]"),
        (re.compile(r"(?:postgres|mysql|mongodb|redis):\/\/[^:\s]+:([^@\s]+)@", re.IGNORECASE), "database://[REDACTED_CREDENTIALS]@"),
        (re.compile(r"0x[0-9a-fA-F]{8,16}"), "[REDACTED_ADDRESS]")
    ]

    SENSITIVE_KEY_TERMS = [
        "hmac", "secret", "token", "password", "api_key", "apikey",
        "private_key", "credential", "auth_token", "jwt", "passphrase"
    ]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """
        Strips secrets and signatures from text strings.
        """
        if not text:
            return text
        sanitized = str(text)
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
            k_str = str(k).lower()
            if any(term in k_str for term in cls.SENSITIVE_KEY_TERMS):
                clean_dict[k] = "[REDACTED_SENSITIVE_FIELD]"
            elif isinstance(v, str):
                clean_dict[k] = cls.sanitize_text(v)
            elif isinstance(v, dict):
                clean_dict[k] = cls.sanitize_dict(v)
            elif isinstance(v, list):
                clean_dict[k] = [
                    cls.sanitize_dict(item) if isinstance(item, dict)
                    else (cls.sanitize_text(item) if isinstance(item, str) else item)
                    for item in v
                ]
            else:
                clean_dict[k] = v
        return clean_dict

    @classmethod
    def sanitize_environment(cls, env: Dict[str, str]) -> Dict[str, str]:
        """
        Sanitizes an environment variable dictionary for subprocess creation.
        Scrubs secret variables while keeping standard operational vars.
        """
        clean_env = {}
        for k, v in env.items():
            if any(term in k.lower() for term in cls.SENSITIVE_KEY_TERMS):
                clean_env[k] = "[REDACTED_ENV_SECRET]"
            else:
                clean_env[k] = cls.sanitize_text(v)
        return clean_env


class SanitizingLoggingFilter(logging.Filter):
    """
    Logging filter that sanitizes all log record messages before formatting.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = SecretSanitizer.sanitize_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = SecretSanitizer.sanitize_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    SecretSanitizer.sanitize_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True
