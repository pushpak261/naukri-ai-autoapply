"""
Tests for utility helper functions.
"""

from src.utils.helpers import (
    clean_text,
    truncate_text,
    extract_naukri_job_id,
    build_search_url,
    hash_file,
)


class TestCleanText:
    """Tests for the clean_text function."""

    def test_strips_html_tags(self):
        assert clean_text("<p>Hello <b>World</b></p>") == "Hello World"

    def test_strips_html_entities(self):
        assert clean_text("Hello&nbsp;World") == "Hello World"

    def test_normalizes_whitespace(self):
        assert clean_text("Hello   World   Foo") == "Hello World Foo"

    def test_handles_empty_string(self):
        assert clean_text("") == ""

    def test_handles_none(self):
        assert clean_text(None) == ""

    def test_complex_html(self):
        html = '<div class="desc"><ul><li>Item 1</li><li>Item 2</li></ul></div>'
        result = clean_text(html)
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<" not in result


class TestTruncateText:
    """Tests for the truncate_text function."""

    def test_short_text_unchanged(self):
        assert truncate_text("Hello", 100) == "Hello"

    def test_long_text_truncated(self):
        text = "word " * 1000
        result = truncate_text(text, 100)
        assert len(result) <= 104  # 100 + "..."
        assert result.endswith("...")

    def test_empty_text(self):
        assert truncate_text("", 100) == ""

    def test_none_text(self):
        assert truncate_text(None, 100) is None




class TestExtractNaukriJobId:
    """Tests for Naukri job ID extraction from URLs."""

    def test_numeric_id_in_url(self):
        url = "https://www.naukri.com/job-listings-python-developer-123456789"
        result = extract_naukri_job_id(url)
        assert result == "123456789"

    def test_url_with_query_params(self):
        url = "https://www.naukri.com/job-listings-dev-987654321?src=search"
        result = extract_naukri_job_id(url)
        assert result == "987654321"

    def test_empty_url(self):
        result = extract_naukri_job_id("")
        assert len(result) > 0  # Should return a hash fallback

    def test_url_without_numeric_id(self):
        url = "https://www.naukri.com/some-job-listing"
        result = extract_naukri_job_id(url)
        assert len(result) > 0  # Should return a hash fallback


class TestBuildSearchUrl:
    """Tests for the search URL builder."""

    def test_basic_url(self):
        url = build_search_url("Python Developer")
        assert "python-developer-jobs" in url
        assert "k=Python" in url

    def test_with_location(self):
        url = build_search_url("Python Developer", location="Bangalore")
        assert "l=Bangalore" in url

    def test_with_experience(self):
        url = build_search_url("Developer", experience_min=3, experience_max=5)
        assert "experience=3" in url

    def test_pagination(self):
        url = build_search_url("Developer", page=3)
        assert "pageNo=3" in url

    def test_sort_by_date(self):
        url = build_search_url("Developer", sort_by="date")
        # Naukri's actual query param for "sort by date" is sort=r, not sort=date.
        assert "sort=r" in url

    def test_sort_by_relevance_omits_sort_param(self):
        url = build_search_url("Developer", sort_by="relevance")
        assert "sort=" not in url

    def test_page_1_no_pageno(self):
        url = build_search_url("Developer", page=1)
        assert "pageNo" not in url


class TestHashFile:
    """Tests for the file hashing function."""

    def test_hash_file(self, tmp_path):
        """Test that hashing a file produces consistent results."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hash1 = hash_file(test_file)
        hash2 = hash_file(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_different_files_different_hashes(self, tmp_path):
        """Test that different files produce different hashes."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        assert hash_file(file1) != hash_file(file2)
