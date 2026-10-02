"""Tests for the run metrics tracker."""

import json

from src.naukri_agent.utils.telemetry import MetricsTracker


class TestInitAndLoad:
    def test_creates_metrics_file_parent_and_defaults(self, tmp_path):
        tracker = MetricsTracker(str(tmp_path / "logs"))

        assert tracker.metrics_file.parent.exists()
        assert tracker.metrics == {
            "total_runs": 0,
            "jobs_applied": 0,
            "jobs_failed": 0,
            "api_calls": 0,
            "duration_seconds": 0.0,
        }

    def test_loads_previously_saved_metrics(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "metrics.json").write_text(
            json.dumps({"total_runs": 3, "jobs_applied": 7, "extra": "ignored"}),
            encoding="utf-8",
        )

        tracker = MetricsTracker(str(log_dir))

        assert tracker.metrics["total_runs"] == 3
        assert tracker.metrics["jobs_applied"] == 7
        assert tracker.metrics["jobs_failed"] == 0  # not persisted, keeps the default
        assert "extra" not in tracker.metrics

    def test_corrupt_metrics_file_falls_back_to_defaults(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "metrics.json").write_text("{not json", encoding="utf-8")

        tracker = MetricsTracker(str(log_dir))

        assert tracker.metrics["total_runs"] == 0


class TestRecordRun:
    def test_accumulates_counters_and_persists(self, tmp_path):
        tracker = MetricsTracker(str(tmp_path / "logs"))
        tracker.record_run(applied=2, failed=1, api_calls=10)
        tracker.record_run(applied=3, failed=0, api_calls=5)

        assert tracker.metrics["total_runs"] == 2
        assert tracker.metrics["jobs_applied"] == 5
        assert tracker.metrics["jobs_failed"] == 1
        assert tracker.metrics["api_calls"] == 15
        assert tracker.metrics["duration_seconds"] > 0

        saved = json.loads(tracker.metrics_file.read_text(encoding="utf-8"))
        assert saved["total_runs"] == 2
        assert saved["jobs_applied"] == 5

    def test_metrics_survive_a_restart(self, tmp_path):
        log_dir = tmp_path / "logs"
        MetricsTracker(str(log_dir)).record_run(applied=4, failed=2)

        reloaded = MetricsTracker(str(log_dir))
        assert reloaded.metrics["jobs_applied"] == 4
        assert reloaded.metrics["jobs_failed"] == 2


class TestSaveFailure:
    def test_write_error_is_swallowed(self, tmp_path, monkeypatch):
        tracker = MetricsTracker(str(tmp_path / "logs"))

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("builtins.open", boom)
        # Must not raise.
        tracker._save()


class TestGithubStepSummary:
    def test_writes_summary_when_env_var_present(self, tmp_path, monkeypatch):
        summary = tmp_path / "step_summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        tracker = MetricsTracker(str(tmp_path / "logs"))
        tracker.record_run(applied=3, failed=1, api_calls=9)

        content = summary.read_text(encoding="utf-8")
        assert "Naukri Agent Run Summary" in content
        assert "| Jobs Applied | 3 |" in content
        assert "| Jobs Failed | 1 |" in content
        assert "| Total API Calls | 9 |" in content
        assert "| Total Runs | 1 |" in content

    def test_summary_write_error_is_swallowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "missing" / "s.md"))

        tracker = MetricsTracker(str(tmp_path / "logs"))
        tracker.record_run(applied=1, failed=0)  # must not raise
