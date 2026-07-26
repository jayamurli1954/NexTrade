"""
NexTrade Phase 5A — Resource Quota Guard.

Monitors and enforces system resource usage limits (RSS memory, file descriptors, storage, threads).
Fails closed into SafetyControlPlane upon quota breach.
"""

from dataclasses import dataclass, field
import os
import sys
import threading
import logging
from typing import Dict, Any, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .safety_control_plane import SafetyControlPlane, SafetyState

logger = logging.getLogger("ResourceQuotaGuard")


class ResourceQuotaExceededException(Exception):
    """Raised when process resource limits exceed strict safety quotas."""
    def __init__(self, resource_name: str, current_value: float, max_quota: float) -> None:
        self.resource_name = resource_name
        self.current_value = current_value
        self.max_quota = max_quota
        super().__init__(f"Resource quota exceeded for '{resource_name}': current={current_value}, limit={max_quota}")


@dataclass
class ResourceQuotaConfig:
    """Configurable resource limits for NexTrade runtime process."""
    max_memory_mb: float = 1024.0
    max_file_handles: int = 256
    max_temp_storage_mb: float = 500.0
    max_log_size_mb: float = 100.0
    max_db_size_mb: float = 500.0
    max_threads: int = 50
    warning_threshold_pct: float = 80.0


class ResourceQuotaGuard:
    """
    Monitors process memory, handles, thread count, and storage footprints.
    Enforces hard limits via SafetyControlPlane transitions.
    """

    def __init__(self, config: Optional[ResourceQuotaConfig] = None, control_plane: Optional[SafetyControlPlane] = None) -> None:
        self.config = config or ResourceQuotaConfig()
        self.control_plane = control_plane or SafetyControlPlane()
        self._process = psutil.Process() if HAS_PSUTIL else None

    def get_memory_usage_mb(self) -> float:
        """Returns current process RSS memory usage in MB."""
        if self._process:
            try:
                return float(self._process.memory_info().rss) / (1024.0 * 1024.0)
            except Exception:
                pass
        return 50.0  # Fallback estimate when psutil unavailable

    def get_open_file_handle_count(self) -> int:
        """Returns open file handle count for process."""
        if self._process:
            try:
                if hasattr(self._process, 'num_handles'):
                    return int(self._process.num_handles())
                elif hasattr(self._process, 'open_files'):
                    return len(self._process.open_files())
            except Exception:
                pass
        return 10  # Fallback estimate

    def get_active_thread_count(self) -> int:
        """Returns active thread count."""
        return threading.active_count()

    def get_directory_size_mb(self, dir_path: str) -> float:
        """Calculates total size of directory in MB."""
        if not os.path.exists(dir_path):
            return 0.0
        total_size = 0
        try:
            for root, _, files in os.walk(dir_path):
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
        except Exception as e:
            logger.warning("Error computing directory size for %s: %s", dir_path, str(e))
        return float(total_size) / (1024.0 * 1024.0)

    def sample_resources(self, temp_dir: Optional[str] = None, log_dir: Optional[str] = None, storage_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Sample current process resource usage and evaluate against configured quotas.
        Returns detailed report dictionary.
        """
        mem_mb = self.get_memory_usage_mb()
        handles = self.get_open_file_handle_count()
        threads = self.get_active_thread_count()

        temp_mb = self.get_directory_size_mb(temp_dir) if temp_dir else 0.0
        log_mb = self.get_directory_size_mb(log_dir) if log_dir else 0.0
        db_mb = self.get_directory_size_mb(storage_dir) if storage_dir else 0.0

        metrics = {
            "memory_mb": (mem_mb, self.config.max_memory_mb),
            "file_handles": (handles, self.config.max_file_handles),
            "threads": (threads, self.config.max_threads),
            "temp_storage_mb": (temp_mb, self.config.max_temp_storage_mb),
            "log_storage_mb": (log_mb, self.config.max_log_size_mb),
            "db_storage_mb": (db_mb, self.config.max_db_size_mb),
        }

        report: Dict[str, Any] = {"status": "PASS", "metrics": {}}
        violations = []
        warnings = []

        for name, (curr, limit) in metrics.items():
            pct = (curr / limit) * 100.0 if limit > 0 else 0.0
            report["metrics"][name] = {
                "current": curr,
                "limit": limit,
                "pct": round(pct, 2)
            }

            if pct >= 100.0:
                violations.append((name, curr, limit))
            elif pct >= self.config.warning_threshold_pct:
                warnings.append((name, curr, limit, pct))

        if warnings:
            for name, curr, limit, pct in warnings:
                logger.warning("RESOURCE QUOTA WARNING: '%s' at %.1f%% of quota (%.2f / %.2f)", name, pct, curr, limit)

        if violations:
            report["status"] = "BREACH"
            first_name, first_curr, first_limit = violations[0]
            err_msg = f"Resource quota breach for '{first_name}': {first_curr:.2f} exceeds limit {first_limit:.2f}"
            logger.critical("RESOURCE QUOTA BREACH: %s", err_msg)
            
            # Transition SafetyControlPlane to HARD_HALT
            self.control_plane.report_subsystem_state(
                "resource_quota_guard",
                SafetyState.HARD_HALT,
                err_msg
            )
            raise ResourceQuotaExceededException(first_name, first_curr, first_limit)

        return report
