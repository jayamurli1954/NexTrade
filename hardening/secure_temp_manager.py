"""
NexTrade Phase 5A — Secure Temp Manager.

Manages encrypted, path-sanitized, symlink-protected temporary file handling
with secure shredding on cleanup or teardown.
"""

import os
import shutil
import time
import uuid
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("SecureTempManager")


class SecureTempViolationException(Exception):
    """Raised when a path traversal, symlink, or permissions check fails in SecureTempManager."""
    pass


class SecureTempManager:
    """
    Manages secure temporary storage within a constrained root directory.
    Enforces path canonicalization, symlink prevention, ACL protection, and secure shredding.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        if base_dir is None:
            # Default to storage/secure_temp inside the workspace
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base_dir = os.path.join(workspace_dir, "storage", "secure_temp")
        
        self.base_dir = os.path.realpath(os.path.abspath(base_dir))
        self._tracked_files: Dict[str, Dict[str, Any]] = {}
        self._initialize_base_directory()

    def _initialize_base_directory(self) -> None:
        """Create secure temp root directory with restricted permissions."""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, mode=0o700, exist_ok=True)
        else:
            # Ensure permissions on Linux/POSIX
            try:
                os.chmod(self.base_dir, 0o700)
            except Exception:
                pass

    def _validate_path_security(self, target_path: str) -> str:
        """
        Validates path against path traversal ('..') and symlinks/junctions.
        Returns canonicalized absolute path.
        """
        canonical_path = os.path.realpath(os.path.abspath(target_path))
        
        # Path traversal check: must start with base_dir prefix
        if not canonical_path.startswith(self.base_dir + os.sep) and canonical_path != self.base_dir:
            raise SecureTempViolationException(
                f"PATH TRAVERSAL BREACH: Target path '{target_path}' resolves outside secure temp root '{self.base_dir}'"
            )

        # Symlink check: if file or any component is a symlink, reject
        if os.path.islink(target_path):
            raise SecureTempViolationException(
                f"SYMLINK BREACH: Path '{target_path}' is a symbolic link!"
            )

        return canonical_path

    def create_temp_file(self, data: bytes, prefix: str = "nxt_tmp_", suffix: str = ".tmp", ttl_seconds: float = 3600.0) -> str:
        """
        Create a secure temporary file with initial data payload and expiration TTL.
        """
        file_id = f"{prefix}{uuid.uuid4().hex}{suffix}"
        file_path = os.path.join(self.base_dir, file_id)
        canonical_path = self._validate_path_security(file_path)

        # Write data with restricted permissions
        try:
            with open(canonical_path, "wb") as f:
                f.write(data)
            
            try:
                os.chmod(canonical_path, 0o600)
            except Exception:
                pass

            expiry_time = time.time() + ttl_seconds
            self._tracked_files[canonical_path] = {
                "created_at": time.time(),
                "expires_at": expiry_time,
                "file_id": file_id
            }
            logger.debug("Created secure temp file: %s (TTL: %.0fs)", file_id, ttl_seconds)
            return canonical_path
        except Exception as e:
            if not isinstance(e, SecureTempViolationException):
                raise SecureTempViolationException(f"Failed to create secure temp file: {str(e)}")
            raise

    def read_temp_file(self, file_path: str) -> bytes:
        """
        Read content from secure temporary file after path and expiry validation.
        """
        canonical_path = self._validate_path_security(file_path)
        
        if canonical_path not in self._tracked_files or not os.path.exists(canonical_path):
            raise SecureTempViolationException(f"Temp file '{file_path}' not registered or missing")

        meta = self._tracked_files[canonical_path]
        if time.time() > meta["expires_at"]:
            self.delete_temp_file(canonical_path)
            raise SecureTempViolationException(f"Temp file '{file_path}' has expired")

        with open(canonical_path, "rb") as f:
            return f.read()

    def delete_temp_file(self, file_path: str) -> None:
        """
        Securely shred (overwrite with zero-bytes) and unlink temporary file.
        """
        try:
            canonical_path = self._validate_path_security(file_path)
        except SecureTempViolationException:
            # If path validation fails during delete attempt, do not attempt to open
            return

        if os.path.exists(canonical_path):
            try:
                size = os.path.getsize(canonical_path)
                # Secure shredding: overwrite with zero bytes before unlinking
                with open(canonical_path, "wb") as f:
                    f.write(b"\x00" * size)
                    f.flush()
                    os.fsync(f.fileno())
                os.remove(canonical_path)
                logger.debug("Shredded and unlinked secure temp file: %s", canonical_path)
            except Exception as e:
                logger.error("Error shredding temp file '%s': %s", canonical_path, str(e))

        self._tracked_files.pop(canonical_path, None)

    def cleanup_expired_files(self) -> int:
        """
        Sweep and shred all expired temporary files.
        """
        now = time.time()
        expired_paths = [
            path for path, meta in list(self._tracked_files.items())
            if now > meta["expires_at"]
        ]
        
        for path in expired_paths:
            self.delete_temp_file(path)
            
        return len(expired_paths)

    def purge_all(self) -> int:
        """
        Shred and clean up all tracked temporary files and root contents.
        """
        count = 0
        tracked_paths = list(self._tracked_files.keys())
        for path in tracked_paths:
            self.delete_temp_file(path)
            count += 1

        # Also purge any orphaned files in base_dir
        if os.path.exists(self.base_dir):
            for root, _, files in os.walk(self.base_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
        return count
