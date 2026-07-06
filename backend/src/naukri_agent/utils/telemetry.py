"""
Telemetry and Metrics tracking for the Naukri Agent.
"""

import json
import os
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
                with open(self.metrics_file, encoding="utf-8") as f:
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
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(self.metrics, f, indent=2)
            logger.info("Metrics successfully tracked.")
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

        # GitHub Actions Summary
        if "GITHUB_STEP_SUMMARY" in os.environ:
            try:
                summary_path = os.environ["GITHUB_STEP_SUMMARY"]
                with open(summary_path, "a", encoding="utf-8") as f:
                    f.write("### 📊 Naukri Agent Run Summary\n\n")
                    f.write("| Metric | Value |\n")
                    f.write("|--------|-------|\n")
                    f.write(f"| Jobs Applied | {self.metrics['jobs_applied']} |\n")
                    f.write(f"| Jobs Failed | {self.metrics['jobs_failed']} |\n")
                    f.write(f"| Total API Calls | {self.metrics['api_calls']} |\n")
                    f.write(f"| Total Runs | {self.metrics['total_runs']} |\n")
                    f.write(f"| Duration | {self.metrics['duration_seconds']:.2f}s |\n\n")
            except Exception as e:
                logger.warning(f"Could not write to GITHUB_STEP_SUMMARY: {e}")
