"""Preferred-employer board sweeps keep MNC roles in the LinkedIn queue."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.linked_agent.browser.search import (
    LinkedInJobSearcher,
    _board_company_matches,
    _location_in_scope,
)
from src.linked_agent.models.entities import Job


@pytest.mark.parametrize(
    "name,company,expected",
    [
        ("JPMorgan Chase", "JPMorganChase", True),
        ("JPMorgan Chase", "JPMorgan Chase & Co.", True),
        ("Deutsche Bank", "Deutsche Bank", True),
        ("Capgemini", "Capgemini Engineering", True),
        ("Mastercard", "Mastercard", True),
        ("Mastercard", "Moniepoint Group", False),
        ("Citi", "CIBC India", False),
        ("Visa", "VISA Group", True),
        ("BNY", "BNY", True),
        ("BNY", "BNY Mellon", True),
    ],
)
def test_company_board_cards_belong_to_the_requested_employer(name, company, expected):
    assert _board_company_matches(name, company) is expected


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Pune Division, Maharashtra, India", True),
        ("Pune/Pimpri-Chinchwad Area", True),
        ("Mumbai, Maharashtra, India", True),
        ("Navi Mumbai, Maharashtra, India", True),
        ("Bengaluru, Karnataka, India", True),
        ("Bangalore, Karnataka, India", True),
        ("Hyderabad, Telangana, India", False),
        ("Gurugram, Haryana, India", False),
        ("", True),
    ],
)
def test_company_board_jobs_stay_in_the_configured_cities(location, expected):
    assert _location_in_scope(location, ["Pune", "Mumbai", "Bengaluru"]) is expected


@pytest.mark.asyncio
async def test_company_board_sweep_skips_other_employers_and_cities():
    searcher = object.__new__(LinkedInJobSearcher)
    searcher._rate_limited = False
    searcher._settings = SimpleNamespace(
        search=SimpleNamespace(
            company_boards={"JPMorgan Chase": "jpmorgan-chase-co"},
            company_board_pages=1,
            locations=["Pune", "Mumbai", "Bengaluru"],
        )
    )
    searcher._search_page = AsyncMock()
    searcher._search_page.parse_job_cards.return_value = [
        Job(
            "1",
            "Java Developer",
            "JPMorganChase",
            "https://www.linkedin.com/jobs/view/1",
            location="Pune, Maharashtra, India",
        ),
        Job(
            "2",
            "Java Developer",
            "JPMorganChase",
            "https://www.linkedin.com/jobs/view/2",
            location="Hyderabad, Telangana, India",
        ),
        Job(
            "3",
            "Java Developer",
            "Acme Recruiters",
            "https://www.linkedin.com/jobs/view/3",
            location="Pune, Maharashtra, India",
        ),
    ]
    all_jobs = {}
    with patch("src.linked_agent.browser.search.asyncio.sleep", AsyncMock()):
        await searcher._search_company_boards(all_jobs)
    assert list(all_jobs) == ["1"]
    assert all_jobs["1"].search_url == "https://www.linkedin.com/jobs/search/"
    searcher._search_page.navigate_to_search.assert_awaited_once_with(
        "https://www.linkedin.com/jobs/jpmorgan-chase-co-jobs"
    )
