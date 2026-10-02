"""Tests for the human-like jitter helpers and the log-message sanitizer."""

import pytest

from src.naukri_agent.utils.humanize import (
    jitter_chance,
    jitter_choice,
    jitter_int,
    jitter_uniform,
)
from src.naukri_agent.utils.logger import sanitize_log_message


class TestJitterUniform:
    def test_stays_within_bounds(self):
        for _ in range(200):
            value = jitter_uniform(0.5, 1.5)
            assert 0.5 <= value < 1.5

    def test_degenerate_range_returns_low(self):
        assert jitter_uniform(2.0, 2.0) == 2.0
        assert jitter_uniform(2.0, 1.0) == 2.0

    def test_negative_range_is_supported(self):
        for _ in range(50):
            assert -1.0 <= jitter_uniform(-1.0, 0.0) < 0.0

    def test_produces_a_spread_of_values(self):
        values = {jitter_uniform(0.0, 100.0) for _ in range(50)}
        assert len(values) > 40


class TestJitterInt:
    def test_stays_within_inclusive_bounds(self):
        for _ in range(200):
            value = jitter_int(50, 150)
            assert 50 <= value <= 150

    def test_single_value_range(self):
        assert jitter_int(7, 7) == 7
        assert jitter_int(7, 3) == 7

    def test_hits_both_endpoints(self):
        values = {jitter_int(0, 2) for _ in range(300)}
        assert values == {0, 1, 2}

    def test_single_option_range_always_returns_it(self):
        assert jitter_int(0, 0) == 0


class TestJitterChance:
    def test_probability_zero_is_never_true(self):
        assert all(jitter_chance(0.0) is False for _ in range(100))

    def test_probability_one_is_always_true(self):
        assert all(jitter_chance(1.0) is True for _ in range(100))

    def test_partial_probability_is_mixed(self):
        results = [jitter_chance(0.5) for _ in range(400)]
        assert any(results)
        assert not all(results)

    def test_beyond_bounds_is_clamped(self):
        assert jitter_chance(-1.0) is False
        assert jitter_chance(5.0) is True


class TestJitterChoice:
    def test_always_selects_a_member(self):
        options = ["down", "up"]
        for _ in range(200):
            assert jitter_choice(options) in options

    def test_selects_across_all_members(self):
        options = ["a", "b", "c"]
        assert {jitter_choice(options) for _ in range(200)} == set(options)

    def test_empty_options_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            jitter_choice([])


class TestSanitizeLogMessage:
    def test_strips_newlines_so_forged_log_lines_are_impossible(self):
        sanitized = sanitize_log_message("line1\nFAKE | ERROR | forged entry")

        assert "\n" not in sanitized
        assert sanitized == "line1 FAKE | ERROR | forged entry"

    def test_strips_carriage_returns_and_null_bytes(self):
        sanitized = sanitize_log_message("a\r\nb\x00c")

        assert "\r" not in sanitized
        assert "\n" not in sanitized
        assert "\x00" not in sanitized

    def test_strips_other_control_characters(self):
        sanitized = sanitize_log_message("tab\there\x07bell\x1b[31mred")

        assert "\x07" not in sanitized
        assert "\x1b" not in sanitized

    def test_leaves_ordinary_text_untouched(self):
        assert sanitize_log_message("Applied to Senior Engineer @ Acme") == (
            "Applied to Senior Engineer @ Acme"
        )

    def test_non_string_input_is_coerced(self):
        assert sanitize_log_message(42) == "42"
        assert sanitize_log_message(None) == "None"

    def test_unicode_is_preserved(self):
        assert sanitize_log_message("café ☕") == "café ☕"
