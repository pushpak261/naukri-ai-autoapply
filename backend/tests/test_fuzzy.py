"""
Tests for Levenshtein Distance and Fuzzy matching utilities.
"""

from __future__ import annotations

from src.naukri_agent.utils.fuzzy import fuzzy_similarity_ratio, levenshtein_distance


def test_levenshtein_distance() -> None:
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("flaw", "lawn") == 2
    assert levenshtein_distance("notice period", "notice period?") == 1


def test_fuzzy_similarity_ratio() -> None:
    # Highly similar strings
    assert fuzzy_similarity_ratio("notice period", "notice period?") > 0.90
    assert fuzzy_similarity_ratio("current ctc", "current salary") > 0.50

    # Identical strings
    assert fuzzy_similarity_ratio("python", "python") == 1.0
    # Case insensitivity
    assert fuzzy_similarity_ratio("Python", "python") == 1.0
