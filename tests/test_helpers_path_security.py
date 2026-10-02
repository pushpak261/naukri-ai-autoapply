"""Tests for untrusted-path containment and the shared helper utilities.

``uploaded_file_path`` arrives from the dashboard API and is later opened by the
agent and the resume parser, so these tests pin down the traversal defences.
"""

import asyncio

import pytest

from src.naukri_agent.utils.helpers import (
    NaukriURLUtility,
    PathSecurityUtility,
    RetryUtility,
    TextUtility,
    build_search_url,
    extract_naukri_job_id,
    resolve_path_within,
    truncate_text,
)


@pytest.fixture
def resumes_dir(tmp_path):
    """A resumes directory containing one real file and one subdirectory."""
    root = tmp_path / "data" / "resumes"
    root.mkdir(parents=True)
    (root / "resume_2026.pdf").write_bytes(b"%PDF-1.4")
    (root / "nested").mkdir()
    (root / "nested" / "deep.pdf").write_bytes(b"%PDF-1.4")
    return root


class TestResolveWithin:
    def test_accepts_file_directly_inside_root(self, resumes_dir):
        resolved = resolve_path_within(resumes_dir / "resume_2026.pdf", resumes_dir)

        assert resolved is not None
        assert resolved.name == "resume_2026.pdf"

    def test_accepts_nested_file_inside_root(self, resumes_dir):
        resolved = resolve_path_within(resumes_dir / "nested" / "deep.pdf", resumes_dir)

        assert resolved is not None
        assert resolved.name == "deep.pdf"

    def test_accepts_a_non_existing_file_inside_root(self, resumes_dir):
        resolved = resolve_path_within(resumes_dir / "not-yet-uploaded.pdf", resumes_dir)

        assert resolved is not None
        assert resolved.name == "not-yet-uploaded.pdf"

    def test_accepts_the_root_itself(self, resumes_dir):
        assert resolve_path_within(resumes_dir, resumes_dir) is not None

    def test_accepts_a_relative_path_that_stays_inside(self, resumes_dir):
        resolved = resolve_path_within(
            str(resumes_dir / "nested" / ".." / "resume_2026.pdf"), resumes_dir
        )

        assert resolved is not None

    def test_accepts_string_input(self, resumes_dir):
        assert resolve_path_within(str(resumes_dir / "resume_2026.pdf"), resumes_dir) is not None

    def test_accepts_any_of_several_roots(self, resumes_dir, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        target = other / "resume.pdf"
        target.write_bytes(b"%PDF-1.4")

        assert resolve_path_within(target, [resumes_dir, other]) is not None
        assert resolve_path_within(target, resumes_dir) is None

    # --- rejections -------------------------------------------------------

    def test_rejects_dot_dot_escape(self, resumes_dir):
        assert resolve_path_within(resumes_dir / ".." / ".." / "etc" / "passwd", resumes_dir) is None

    def test_rejects_unrelated_absolute_path(self, resumes_dir, tmp_path):
        outside = tmp_path / "secret.txt"
        outside.write_text("s3cret", encoding="utf-8")

        assert resolve_path_within(outside, resumes_dir) is None

    def test_rejects_sibling_directory_with_shared_prefix(self, tmp_path):
        """``/data/resumes_evil`` must not be accepted for root ``/data/resumes``."""
        root = tmp_path / "data" / "resumes"
        root.mkdir(parents=True)
        evil = tmp_path / "data" / "resumes_evil"
        evil.mkdir()
        target = evil / "passwd"
        target.write_text("x", encoding="utf-8")

        assert resolve_path_within(target, root) is None

    def test_rejects_symlink_pointing_outside(self, resumes_dir, tmp_path):
        outside = tmp_path / "secret.txt"
        outside.write_text("s3cret", encoding="utf-8")
        link = resumes_dir / "innocent.pdf"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not permitted on this platform")

        assert resolve_path_within(link, resumes_dir) is None

    def test_rejects_none(self, resumes_dir):
        assert resolve_path_within(None, resumes_dir) is None

    @pytest.mark.parametrize("value", ["", "   ", "\t\n"])
    def test_rejects_blank_strings(self, resumes_dir, value):
        assert resolve_path_within(value, resumes_dir) is None

    def test_rejects_when_no_roots_are_configured(self):
        assert resolve_path_within("/tmp/whatever.pdf", []) is None

    def test_rejects_null_byte_path(self, resumes_dir):
        assert resolve_path_within(str(resumes_dir) + "\x00.pdf", resumes_dir) is None


class TestIsWithin:
    def test_true_for_inside(self, resumes_dir):
        assert PathSecurityUtility.is_within(resumes_dir / "resume_2026.pdf", resumes_dir) is True

    def test_false_for_outside(self, resumes_dir, tmp_path):
        assert PathSecurityUtility.is_within(tmp_path / "other.pdf", resumes_dir) is False


class TestAsyncRetry:
    async def test_returns_result_without_retrying_on_success(self):
        calls = []

        @RetryUtility.async_retry(delay_seconds=0)
        async def ok():
            calls.append(1)
            return "value"

        assert await ok() == "value"
        assert len(calls) == 1

    async def test_retries_then_succeeds(self):
        calls = []

        @RetryUtility.async_retry(max_attempts=3, delay_seconds=0)
        async def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("transient")
            return "recovered"

        assert await flaky() == "recovered"
        assert len(calls) == 3

    async def test_raises_after_exhausting_attempts(self):
        calls = []

        @RetryUtility.async_retry(max_attempts=2, delay_seconds=0)
        async def always_fails():
            calls.append(1)
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            await always_fails()
        assert len(calls) == 2

    async def test_quota_errors_are_not_retried(self):
        calls = []

        class QuotaError(Exception):
            is_daily_quota = True

        @RetryUtility.async_retry(max_attempts=3, delay_seconds=0)
        async def quota():
            calls.append(1)
            raise QuotaError("out of quota")

        with pytest.raises(QuotaError):
            await quota()
        assert len(calls) == 1

    async def test_backoff_delays_grow(self, monkeypatch):
        slept = []
        real_sleep = asyncio.sleep

        async def fake_sleep(seconds):
            slept.append(seconds)
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        calls = []

        @RetryUtility.async_retry(max_attempts=3, delay_seconds=1.0, backoff_factor=3.0)
        async def flaky():
            calls.append(1)
            raise ValueError("x")

        with pytest.raises(ValueError):
            await flaky()

        assert slept == [1.0, 3.0]


class TestBuildSearchUrlCoercion:
    def test_non_numeric_inputs_fall_back_to_defaults(self):
        url = build_search_url(
            "python",
            "pune",
            experience_min="not-a-number",
            experience_max="also-bad",
            salary_min=None,
            freshness="bad",
            page="bad",
        )

        # experience=0 is the default minimum; page falls back to 1.
        assert "experience=0" in url
        assert "pageNo=1" not in url

    def test_experience_max_is_bumped_above_min(self):
        url = build_search_url("java", experience_min=10, experience_max=10)

        assert "experience=10" in url
        assert "experiencemax=11" in url

    def test_experience_max_left_alone_when_above_fifty(self):
        url = build_search_url("java", experience_min=10, experience_max=50)

        assert "experience=10" in url
        assert "experiencemax" not in url

    def test_page_is_bounded_to_one_hundred(self):
        url = NaukriURLUtility.build_search_url("go", page=9999)

        assert "go-jobs-100" in url

    def test_page_below_one_is_clamped(self):
        url = NaukriURLUtility.build_search_url("go", page=0)

        assert "go-jobs?" in url or url.endswith("go-jobs") or "pageNo" not in url

    def test_empty_keywords_produces_jobs_path(self):
        url = build_search_url("", location="")

        assert "/jobs?" in url

    def test_special_characters_are_slugified(self):
        url = build_search_url("C++ / C# Developer")

        assert "c-plus-plus" in url
        assert "c-sharp" in url
        assert "C%2B%2B" in url  # the raw query keeps the original keywords

    def test_framework_names_become_slugs(self):
        url = build_search_url("React.js developer")

        assert "react-js" in url

    def test_salary_and_freshness_are_included(self):
        url = build_search_url("go", salary_min=20, freshness=3)

        assert "salary=20" in url
        assert "jobAge=3" in url

    def test_sort_by_date_uses_d_suffix(self):
        url = build_search_url("go", sort_by="date")

        assert "sort=d" in url


class TestExtractJobId:
    def test_extracts_numeric_id_from_canonical_url(self):
        assert extract_naukri_job_id("https://www.naukri.com/dev-jobs-12345678") == "12345678"

    def test_extracts_jid_query_parameter(self):
        assert extract_naukri_job_id("https://www.naukri.com/search?jid=99887766") == "99887766"

    def test_falls_back_to_a_stable_hash(self):
        first = extract_naukri_job_id("https://www.naukri.com/unusual/path")
        second = extract_naukri_job_id("https://www.naukri.com/unusual/path")

        assert first == second
        assert len(first) == 16

    def test_hash_fallback_is_hex_and_url_specific(self):
        sentinel = extract_naukri_job_id("")
        other = extract_naukri_job_id("https://www.naukri.com/another")

        assert int(sentinel, 16) >= 0
        assert len(sentinel) == 16
        assert sentinel != other

    def test_ignores_non_numeric_url_segment(self):
        assert extract_naukri_job_id("https://www.naukri.com/dev-jobs") not in ("dev", "")


class TestTruncateText:
    def test_short_text_untouched(self):
        assert truncate_text("short") == "short"

    def test_none_stays_none(self):
        assert truncate_text(None) is None

    def test_long_text_is_truncated(self):
        result = truncate_text("word " * 2000, max_length=100)

        assert result is not None
        assert len(result) <= 104
        assert result.endswith("...")

    def test_truncation_prefers_a_word_boundary(self):
        result = truncate_text("alpha beta gamma delta epsilon zeta eta theta", max_length=20)

        assert result is not None
        assert result.endswith("...")
        assert not result[:-3].endswith(" ")
