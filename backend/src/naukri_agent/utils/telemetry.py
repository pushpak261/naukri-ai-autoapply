"""
Telemetry and Metrics tracking for the Naukri Agent.
"""

import json
import time
from pathlib import Path
from typing import Any

from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


class MetricsTracker:
    def __init__(self, log_dir: str):
        self.metrics_file = Path(log_dir) / "metrics.json"
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self.start_time = time.perf_counter()
        self.metrics: dict[str, Any] = {
            "total_runs": 0,
            "jobs_applied": 0,
            "jobs_failed": 0,
            "api_calls": 0,
            "duration_seconds": 0.0,
        }
        self._load()

    def _load(self):
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file) as f:
                    data = json.load(f)
                    for k in self.metrics:
                        if k in data:
                            self.metrics[k] = data[k]
            except Exception as e:
                logger.warning(f"Could not load metrics: {e}")

    def record_run(self, applied: int, failed: int, api_calls: int = 0):
        self.metrics["total_runs"] += 1
        self.metrics["jobs_applied"] += applied
        self.metrics["jobs_failed"] += failed
        self.metrics["api_calls"] += api_calls
        self.metrics["duration_seconds"] += time.perf_counter() - self.start_time
        self._save()

    def _save(self):
        try:
            with open(self.metrics_file, "w") as f:
                json.dump(self.metrics, f, indent=2)
            logger.info("Metrics successfully tracked.")
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
