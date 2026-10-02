"""Tests for job filters, vector similarity, and the Gemini LLM provider."""

import asyncio
from types import SimpleNamespace

import pytest

from src.naukri_agent.ai import llm_provider as llm_mod
from src.naukri_agent.ai.llm_provider import GeminiProvider, _is_daily_quota_violation
from src.naukri_agent.utils.exceptions import LLMAPIError, LLMQuotaExceededError
from src.naukri_agent.utils.filters import JobFilter
from src.naukri_agent.utils.similarity import VectorSimilarityFilter


def _job(title="Dev", experience="0-2 Yrs", posted_date="2 days ago"):
    return SimpleNamespace(title=title, experience=experience, posted_date=posted_date)


class TestExperienceFilter:
    @pytest.mark.parametrize("max_exp", [2, 5])
    def test_range_within_limit_passes(self, max_exp):
        assert JobFilter(max_exp, 30)._passes_experience_filter("0-2 yrs") is True

    def test_range_starting_too_high_is_rejected(self):
        assert JobFilter(2, 30)._passes_experience_filter("7-9 yrs") is False

    def test_range_ending_far_above_limit_is_rejected(self):
        assert JobFilter(2, 30)._passes_experience_filter("1-6 yrs") is False

    def test_month_abbreviation_is_treated_as_a_date_not_experience(self):
        assert JobFilter(2, 30)._passes_experience_filter("24 Mar") is True
        assert JobFilter(2, 30)._passes_experience_filter("Jan") is True

    def test_single_number_above_limit_is_rejected(self):
        assert JobFilter(3, 30)._passes_experience_filter("8 yrs") is False

    def test_single_number_within_limit_passes(self):
        assert JobFilter(8, 30)._passes_experience_filter("3 yrs") is True

    def test_unparseable_text_passes(self):
        assert JobFilter(2, 30)._passes_experience_filter("Not disclosed") is True

    def test_to_separator_is_parsed(self):
        assert JobFilter(2, 30)._passes_experience_filter("5 to 9 yrs") is False


class TestFreshnessFilter:
    @pytest.mark.parametrize(
        ("text", "days"),
        [
            ("Just now", 0),
            ("Today", 0),
            ("3 hours ago", 0),
            ("45 minutes ago", 0),
            ("Yesterday", 1),
            ("2 months ago", 60),
            ("a month ago", 30),
            ("2 weeks ago", 14),
            ("a week ago", 7),
            ("30+ days ago", 31),
            ("7 days ago", 7),
            ("a day ago", 1),
            ("day ago", 1),
            ("sometime in the past", 999),
        ],
    )
    def test_date_strings_map_to_days(self, text, days):
        assert JobFilter._parse_date_to_days(text) == days

    def test_zero_max_freshness_disables_the_check(self):
        assert JobFilter(5, 0)._passes_freshness_filter("900 days ago") is True

    def test_old_posting_is_rejected(self):
        assert JobFilter(5, 7)._passes_freshness_filter("2 months ago") is False

    def test_recent_posting_passes(self):
        assert JobFilter(5, 7)._passes_freshness_filter("3 days ago") is True


class TestFilterPipeline:
    def test_keeps_only_passing_jobs(self):
        f = JobFilter(max_experience=2, max_freshness_days=7)

        kept = f.filter(
            [
                _job("Keep"),
                _job("TooSenior", experience="9-12 yrs"),
                _job("TooOld", posted_date="2 months ago"),
            ]
        )

        assert [j.title for j in kept] == ["Keep"]

    def test_sorting_by_date_puts_newest_first(self):
        f = JobFilter(max_experience=9, max_freshness_days=365, sort_by="date")

        result = f.filter(
            [_job("Old", posted_date="2 months ago"), _job("New", posted_date="today")]
        )

        assert [j.title for j in result] == ["New", "Old"]

    def test_no_sorting_by_default(self):
        f = JobFilter(max_experience=9, max_freshness_days=365)

        result = f.filter([_job("A"), _job("B")])

        assert [j.title for j in result] == ["A", "B"]

    def test_empty_input_returns_empty_list(self):
        assert JobFilter(5, 7).filter([]) == []


class TestVectorSimilarity:
    def test_identical_text_scores_one(self):
        f = VectorSimilarityFilter(["python developer with fastapi"])

        assert f.get_similarity_score("python developer with fastapi") == pytest.approx(1.0)

    def test_unrelated_text_scores_zero(self):
        f = VectorSimilarityFilter(["python developer"])

        assert f.get_similarity_score("pastry chef baker") == pytest.approx(0.0)

    def test_score_is_bounded(self):
        f = VectorSimilarityFilter(["python fastapi docker kubernetes"])

        score = f.get_similarity_score("python docker deployment")

        assert 0.0 <= score <= 1.0

    def test_empty_resume_yields_zero(self):
        f = VectorSimilarityFilter([""])

        assert f.get_similarity_score("anything at all") == 0.0

    def test_empty_job_text_yields_zero(self):
        f = VectorSimilarityFilter(["python developer"])

        assert f.get_similarity_score("") == 0.0

    def test_technology_aliases_are_normalised(self):
        f = VectorSimilarityFilter(["c# developer"])

        assert f.get_similarity_score("C# developer") == pytest.approx(1.0)
        assert "csharp" in f.resume_tokens
        assert "cpp" not in f.resume_tokens

    def test_cpp_and_fsharp_aliases(self):
        f = VectorSimilarityFilter(["c++ and f#"])

        assert "cpp" in f.resume_tokens
        assert "fsharp" in f.resume_tokens

    def test_idf_falls_back_to_tf_without_corpus_data(self):
        f = VectorSimilarityFilter(["python"])

        assert f._compute_idf("python") == 1.0

    def test_idf_downweights_common_words(self):
        common = VectorSimilarityFilter(["the"], {"the": 1000}, 1000)
        rare = VectorSimilarityFilter(["the"], {"the": 1}, 1000)

        assert common._compute_idf("the") < rare._compute_idf("the")

    def test_punctuation_is_stripped(self):
        f = VectorSimilarityFilter(["python, docker; kubernetes!!"])

        assert set(f.resume_tokens) == {"python", "docker", "kubernetes"}


class TestGeminiProviderApiKeys:
    def test_comma_separated_keys_take_the_first(self):
        assert GeminiProvider("  key-one , key-two ")._api_key == "key-one"

    def test_list_takes_the_first(self):
        assert GeminiProvider(["a", "b"])._api_key == "a"

    def test_empty_list_yields_empty_key(self):
        assert GeminiProvider([])._api_key == ""

    def test_non_string_key_is_passed_through(self):
        sentinel = object()
        assert GeminiProvider(sentinel)._api_key is sentinel

    def test_missing_key_raises_when_client_needed(self):
        with pytest.raises(ValueError, match="No API key"):
            GeminiProvider("")._get_client()

    def test_client_is_cached(self, monkeypatch):
        provider = GeminiProvider("key")

        created = []
        monkeypatch.setattr(llm_mod.genai, "Client", lambda **kw: created.append(kw) or "client")

        assert provider._get_client() == "client"
        assert provider._get_client() == "client"
        assert len(created) == 1

    def test_set_model_switches_model(self):
        provider = GeminiProvider("key")
        provider.set_model("gemini-2.0-flash")

        assert provider._model_name == "gemini-2.0-flash"


def _api_error(code: int, message: str = "err", detail_blocks=None):
    """Build a real genai APIError; ``details``/``message`` are derived from it."""
    error_body = {"message": message, "code": code}
    if detail_blocks is not None:
        error_body["details"] = detail_blocks
    return llm_mod.genai_errors.APIError(code, {"error": error_body})


class TestDailyQuotaDetection:
    def test_detects_daily_quota_id(self):
        error = _api_error(
            429,
            "quota exceeded",
            [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}],
        )

        assert _is_daily_quota_violation(error) is True

    def test_per_minute_quota_is_not_daily(self):
        error = _api_error(
            429,
            "quota exceeded",
            [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProject"}]}],
        )

        assert _is_daily_quota_violation(error) is False

    def test_non_dict_detail_entries_are_skipped(self):
        error = _api_error(429, "quota exceeded", ["junk", 5, None])

        assert _is_daily_quota_violation(error) is False

    def test_missing_details_falls_back_to_string_matching(self):
        assert _is_daily_quota_violation(_api_error(429, "PerDay limit reached")) is True

    def test_missing_details_without_daily_marker(self):
        assert _is_daily_quota_violation(_api_error(429, "try again later")) is False

    def test_non_dict_error_block_does_not_raise(self):
        error = llm_mod.genai_errors.APIError(429, "malformed-response")

        assert _is_daily_quota_violation(error) is False


class TestGenerateContent:
    @pytest.fixture(autouse=True)
    def _no_retry_sleep(self, monkeypatch):
        """``generate_content`` is wrapped in ``async_retry``; skip real backoff."""

        async def instant(_seconds):
            return None

        monkeypatch.setattr(asyncio, "sleep", instant)

    @pytest.fixture
    def provider(self, monkeypatch):
        p = GeminiProvider("key")

        async def no_wait(_tokens):
            return None

        monkeypatch.setattr(p._rate_limiter, "acquire", no_wait)
        return p

    def _stub(self, provider, monkeypatch, outcomes):
        """Feed ``outcomes`` to the fake client, repeating the final entry.

        ``generate_content`` retries on LLMAPIError, so a single-element list
        must keep producing the same error instead of running out of entries.
        """
        calls = []
        remaining = list(outcomes)

        async def generate_content(**kwargs):
            calls.append(kwargs["model"])
            outcome = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(
            provider,
            "_get_client",
            lambda: SimpleNamespace(
                aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
            ),
        )
        return calls

    async def test_returns_text(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [SimpleNamespace(text="  hello  ", candidates=None)])

        assert await provider.generate_content("prompt") == "hello"

    async def test_missing_text_raises_with_finish_reason(self, provider, monkeypatch):
        self._stub(
            provider,
            monkeypatch,
            [SimpleNamespace(text=None, candidates=[SimpleNamespace(finish_reason="SAFETY")])],
        )

        with pytest.raises(LLMAPIError, match="SAFETY"):
            await provider.generate_content("prompt")

    async def test_missing_text_without_candidates(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [SimpleNamespace(text=None, candidates=None)])

        with pytest.raises(LLMAPIError, match="finish_reason=None"):
            await provider.generate_content("prompt")

    async def test_json_fences_are_stripped(self, provider, monkeypatch):
        self._stub(
            provider,
            monkeypatch,
            [SimpleNamespace(text='```json\n{"a": 1}\n```', candidates=None)],
        )

        result = await provider.generate_content("p", response_mime_type="application/json")

        assert result == '{"a": 1}'

    async def test_rate_limit_429_raises_quota_error(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [_api_error(429, "slow down")])

        with pytest.raises(LLMQuotaExceededError):
            await provider.generate_content("prompt")

    async def test_daily_quota_429_is_flagged_as_daily(self, provider, monkeypatch):
        self._stub(
            provider,
            monkeypatch,
            [
                _api_error(
                    429,
                    "exhausted",
                    [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProject"}]}],
                )
            ],
        )

        with pytest.raises(LLMQuotaExceededError) as excinfo:
            await provider.generate_content("prompt")

        assert excinfo.value.is_daily_quota is True

    async def test_per_minute_quota_429_is_not_daily(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [_api_error(429, "slow down")])

        with pytest.raises(LLMQuotaExceededError) as excinfo:
            await provider.generate_content("prompt")

        assert excinfo.value.is_daily_quota is False

    async def test_unavailable_model_falls_back(self, provider, monkeypatch):
        calls = self._stub(
            provider,
            monkeypatch,
            [_api_error(404, "gone"), SimpleNamespace(text="recovered", candidates=None)],
        )

        assert await provider.generate_content("prompt") == "recovered"
        assert len(calls) == 2

    async def test_other_api_errors_raise(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [_api_error(500, "boom")])

        with pytest.raises(LLMAPIError, match="500"):
            await provider.generate_content("prompt")

    async def test_unexpected_error_is_wrapped(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [RuntimeError("weird")])

        with pytest.raises(LLMAPIError, match="Failed to generate content"):
            await provider.generate_content("prompt")

    async def test_all_models_failing_raises(self, provider, monkeypatch):
        self._stub(provider, monkeypatch, [_api_error(404, "gone")])

        with pytest.raises(LLMAPIError, match="across available models"):
            await provider.generate_content("prompt")
