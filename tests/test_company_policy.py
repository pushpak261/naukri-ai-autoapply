import json
from types import SimpleNamespace

import pytest

from api.company_policy import CompanyPolicy


def policy(tmp_path, preferred=(), whitelist=(), blacklist=()):
    root = tmp_path / "workspace"
    config = root / "data"
    config.mkdir(parents=True)
    if whitelist or blacklist:
        (config / "autopilot_config.json").write_text(
            json.dumps(
                {
                    "company_whitelist": list(whitelist),
                    "company_blacklist": list(blacklist),
                }
            )
        )
    settings = SimpleNamespace(
        project_root=root,
        data_dir=config / "linkedin",
        search=SimpleNamespace(preferred_companies=list(preferred)),
    )
    return CompanyPolicy(settings, "linkedin")


def test_preferred_companies_match_legal_and_unit_suffixes(tmp_path):
    preferences = policy(
        tmp_path,
        preferred=[
            "JP Morgan",
            "Capgemini",
            "Mastercard",
            "Tata Consultancy Services",
            "IBM",
            "SAP",
        ],
    )
    assert preferences.priority("JPMorgan Chase & Co.") == 1
    assert preferences.priority("Capgemini Technology Services India Limited") == 1
    assert preferences.priority("Mastercard Incorporated") == 1
    assert preferences.priority("Tata Consultancy Services") == 1
    assert preferences.priority("IBM India Pvt Ltd") == 1
    assert preferences.priority("Sapient") == 0
    assert preferences.priority("Talentgigs") == 0


def test_preferred_companies_load_from_the_linkedin_settings(tmp_path):
    from src.linked_agent.config.settings import Settings

    settings = Settings(
        project_root=tmp_path,
        search={"preferred_companies": ["JPMorgan Chase", "Capgemini"]},
    )
    preferences = CompanyPolicy(settings, "linkedin")
    assert preferences.priority("JP Morgan") == 1
    assert preferences.priority("Capgemini Technology Services India Limited") == 1
    assert preferences.priority("Unknown Startup") == 0


def test_saved_whitelist_still_works_with_suffix_variants(tmp_path):
    preferences = policy(tmp_path, whitelist=["Preferred Technologies"])
    assert preferences.priority("preferred") == 1
    assert preferences.priority("Preferred Technologies Pvt. Ltd.") == 1
    assert preferences.priority("Other") == 0


@pytest.mark.asyncio
async def test_blacklisted_names_match_suffix_variants(tmp_path):
    preferences = policy(tmp_path, blacklist=["Blocked Staffing"])
    assert (await preferences.allowed("Blocked Staffing Pvt Ltd", None, "linkedin"))[0] is False
    assert (await preferences.allowed("Allowed Employer", None, "linkedin"))[0] is True
