"""Tests for per-run settings overrides."""

from src.naukri_agent.config.settings import ApplicationSettings, Settings


def test_copy_for_run_applies_overrides_without_mutating_source():
    base = Settings(application=ApplicationSettings(daily_cap=25, match_score_threshold=70))

    run_settings = base.copy_for_run(cap=10, threshold=55)

    assert run_settings.application.daily_cap == 10
    assert run_settings.application.match_score_threshold == 55
    assert run_settings.run_cap_resets_daily is True
    assert base.application.daily_cap == 25
    assert base.application.match_score_threshold == 70
    assert base.run_cap_resets_daily is False


def test_copy_for_run_threshold_only_does_not_reset_daily_cap_scope():
    base = Settings(application=ApplicationSettings(daily_cap=25, match_score_threshold=70))

    run_settings = base.copy_for_run(threshold=40)

    assert run_settings.application.match_score_threshold == 40
    assert run_settings.application.daily_cap == 25
    assert run_settings.run_cap_resets_daily is False


def test_copy_for_run_applies_experience_overrides_without_mutating_source():
    base = Settings()

    run_settings = base.copy_for_run(experience_min=1, experience_max=3)

    assert run_settings.search.experience_min == 1
    assert run_settings.search.experience_max == 3
    assert base.search.experience_min == 0
    assert base.search.experience_max == 5


def test_copy_for_run_preserves_strict_policy_mode_default():
    base = Settings()
    assert base.application.strict_policy_mode is False

    run_settings = base.copy_for_run(experience_min=1)
    assert run_settings.application.strict_policy_mode is False
