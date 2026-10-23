"""External-apply preferences remain explicit and consistent across platforms."""

# ruff: noqa: F811
import pytest
import yaml

from tests.test_dashboard_features import dashboard
from tests.test_dashboard_users import register_client


@pytest.mark.asyncio
async def test_external_apply_needs_key_and_preserves_native_offline_mode(dashboard):
    async with register_client("external-fixture@example.invalid") as user:
        response = await user.put("/api/config", json={"skip_external_apply": False})
        assert response.status_code == 422
        result = await user.put(
            "/api/config",
            json={
                "gemini_api_key": "fixture-only-key",
                "use_gemini": False,
                "skip_external_apply": False,
            },
        )
        assert result.status_code == 200
        config = (await user.get("/api/config")).json()
        assert not config["application"]["skip_external_apply"]
        assert not config["ai"]["use_gemini"]
        assert (
            await user.put("/api/config", json={"skip_external_apply": True})
        ).status_code == 200
        assert (await user.get("/api/config")).json()["application"]["skip_external_apply"]


@pytest.mark.asyncio
async def test_external_apply_removes_conflicting_linkedin_search_override(dashboard):
    from api import identity
    from api.deps import root_state

    async with register_client("external-linked-fixture@example.invalid") as user:
        await user.get("/api/config")  # Account workspace is created lazily.
        record = identity.find_user("external-linked-fixture@example.invalid")
        root = root_state.settings.project_root / "data" / "users" / record["id"]
        path = root / "linkedin_config.yaml"
        path.write_text(
            yaml.safe_dump({"application": {"easy_apply_only": True, "skip_external_apply": True}})
        )
        result = await user.put(
            "/api/config", json={"gemini_api_key": "fixture-only-key", "skip_external_apply": False}
        )
        assert result.status_code == 200
        saved = yaml.safe_load(path.read_text())["application"]
        assert saved["skip_external_apply"] is False
        assert saved["easy_apply_only"] is False
