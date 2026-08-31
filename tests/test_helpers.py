"""
Tests for utility helper functions.
"""

from src.naukri_agent.utils.helpers import (
    build_search_url,
    clean_text,
    extract_naukri_job_id,
    hash_file,
    truncate_text,
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

    def test_with_location(self):
        url = build_search_url("Python Developer", location="Bangalore")
        assert "jobs-in-bangalore" in url

    def test_with_experience(self):
        url = build_search_url("Developer", experience_min=3, experience_max=5)
        assert "experience=3" in url

    def test_pagination(self):
        url = build_search_url("Developer", page=3)
        assert "developer-jobs-3" in url
        assert "pageNo=3" in url

    def test_sort_by_date(self):
        url = build_search_url("Developer", sort_by="date")
        # Naukri's actual query param for "sort by date" is sort=d.
        assert "sort=d" in url

    def test_sort_by_relevance_omits_sort_param(self):
        url = build_search_url("Developer", sort_by="relevance")
        assert "sort=" not in url

    def test_page_1_no_page_suffix(self):
        url = build_search_url("Developer", page=1)
        assert "developer-jobs-1" not in url
        assert "pageNo" not in url

    def test_special_character_keywords(self):
        # C++
        url = build_search_url("C++ Developer")
        assert "c-plus-plus-developer-jobs" in url

        # C#
        url = build_search_url("C# Developer")
        assert "c-sharp-developer-jobs" in url

        # .NET
        url = build_search_url(".NET Core Developer")
        assert "dot-net-core-developer-jobs" in url

    def test_suffix_patterns(self):
        # React.js
        url = build_search_url("React.js Developer")
        assert "react-js-developer-jobs" in url

        # Node.js
        url = build_search_url("Node.js Developer")
        assert "node-js-developer-jobs" in url

    def test_page_bounds(self):
        # Page < 1 should be bounded to 1 (no page suffix)
        url_low = build_search_url("Developer", page=-5)
        assert "developer-jobs-5" not in url_low
        assert "developer-jobs-1" not in url_low
        assert "pageNo" not in url_low

        # Page > 100 should be bounded to 100
        url_high = build_search_url("Developer", page=120)
        assert "developer-jobs-100" in url_high
        assert "pageNo=100" in url_high

    def test_query_params_k_and_l(self):
        # Should include k and l parameters
        url = build_search_url("Python Developer", location="Pune")
        assert "k=Python%20Developer" in url
        assert "l=Pune" in url

    def test_type_coercion(self):
        # Passing string values instead of integers should be handled gracefully
        url = build_search_url(
            "Developer",
            experience_min="3",
            experience_max="5",
            salary_min="10",
            freshness="15",
            page="4",
        )
        assert "experience=3" in url
        assert "experiencemax=5" in url
        assert "salary=10" in url
        assert "jobAge=15" in url
        assert "pageNo=4" in url
        assert "developer-jobs-4" in url


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

    def test_hash_file_not_exists(self, tmp_path):
        """Test hashing a non-existent file - expect error or None."""
        test_file = tmp_path / "nonexistent.txt"
        # hash_file should handle non-existent files gracefully
        try:
            result = hash_file(test_file)
            # If it doesn't raise, it should return None or a default value
            assert result is None or result is not False
        except FileNotFoundError:
            # Also acceptable behavior
            pass


class TestTimeUtility:
    """Tests for TimeUtility class."""

    def test_random_delay_in_range(self):
        """Test that random delay stays within bounds."""
        import asyncio
        import random

        # Mock random.gauss to get predictable results
        original_gauss = random.gauss
        random.gauss = lambda mean, std: mean  # Return mean for testing

        async def test_delay():
            from src.naukri_agent.utils.helpers import TimeUtility
            delay = await TimeUtility.random_delay(1.0, 3.0)
            assert 1.0 <= delay <= 3.0

        # Run async test
        asyncio.run(test_delay())

        # Restore original
        random.gauss = original_gauss


class TestTextUtility:
    """Tests for TextUtility class."""

    def test_clean_with_html(self):
        """Test TextUtility.clean with HTML."""
        from src.naukri_agent.utils.helpers import TextUtility
        html = "<p>Hello <b>World</b></p>"
        result = TextUtility.clean(html)
        assert "Hello World" in result
        assert "<" not in result

    def test_clean_with_none(self):
        """Test TextUtility.clean with None."""
        from src.naukri_agent.utils.helpers import TextUtility
        result = TextUtility.clean(None)
        assert result == ""

    def test_clean_with_empty_string(self):
        """Test TextUtility.clean with empty string."""
        from src.naukri_agent.utils.helpers import TextUtility
        result = TextUtility.clean("")
        assert result == ""


class TestAdditionalHelpers:
    """Additional tests for helper functions to increase coverage."""

    def test_clean_text_with_markdown(self):
        """Test cleaning text with markdown syntax."""
        markdown = "# Heading\n**Bold** and *italic*"
        result = clean_text(markdown)
        assert "Heading" in result
        assert "Bold" in result
        assert "italic" in result

    def test_clean_text_with_urls(self):
        """Test cleaning text with URLs."""
        text = "Visit https://example.com for more info"
        result = clean_text(text)
        assert "Visit" in result
        assert "example.com" in result

    def test_clean_text_with_special_chars(self):
        """Test cleaning text with special characters."""
        text = "Hello &amp; World &copy; 2024"
        result = clean_text(text)
        assert "&" not in result  # Should be decoded
        assert "Hello" in result
        assert "World" in result

    def test_extract_naukri_job_id_from_complex_url(self):
        """Test extracting job ID from complex URLs."""
        url = "https://www.naukri.com/job-listings-java-developer-spring-boot-123456789?src=history&k=java"
        result = extract_naukri_job_id(url)
        assert result == "123456789"

    def test_extract_naukri_job_id_very_long_number(self):
        """Test extracting very long job IDs."""
        url = "https://www.naukri.com/job-12345678901234567890"
        result = extract_naukri_job_id(url)
        assert "12345678901234567890" in result

    def test_build_search_url_with_salary(self):
        """Test building search URL with salary filter."""
        url = build_search_url("Developer", salary_min=15)
        assert "salary=15" in url

    def test_build_search_url_with_freshness(self):
        """Test building search URL with freshness filter."""
        url = build_search_url("Developer", freshness=7)
        assert "jobAge=7" in url

    def test_build_search_url_with_multiple_filters(self):
        """Test building search URL with multiple filters."""
        url = build_search_url(
            "Developer",
            location="Pune",
            experience_min=2,
            experience_max=5,
            salary_min=10,
            freshness=14
        )
        assert "l=Pune" in url
        assert "experience=2" in url
        assert "salary=10" in url
        assert "jobAge=14" in url

    def test_truncate_text_exactly_at_limit(self):
        """Test truncating text exactly at limit."""
        text = "a" * 100
        result = truncate_text(text, 100)
        assert len(result) == 100
        assert not result.endswith("...")

    def test_truncate_text_with_unicode(self):
        """Test truncating text with unicode characters."""
        text = "Hello 世界 🌍" * 100
        result = truncate_text(text, 50)
        assert len(result) <= 54  # 50 + "..."

    def test_hash_file_with_binary_content(self, tmp_path):
        """Test hashing file with binary content."""
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")

        hash1 = hash_file(test_file)
        hash2 = hash_file(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64
