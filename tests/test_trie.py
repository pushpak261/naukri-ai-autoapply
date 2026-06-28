"""
Tests for Aho-Corasick Multi-Pattern Search Automaton.
"""

from __future__ import annotations

from src.naukri_agent.utils.trie import AhoCorasick


def test_aho_corasick_matching() -> None:
    keywords = ["Python", "FastAPI", "React", "Developer"]
    aho = AhoCorasick(keywords)

    text = "Jane is a Python Developer working with FastAPI."
    matches = aho.search(text)

    assert "Python" in matches
    assert "Developer" in matches
    assert "FastAPI" in matches
    assert "React" not in matches

    # Verify matched positions
    assert matches["Python"] == [10]
    assert matches["Developer"] == [17]
    assert matches["FastAPI"] == [40]
