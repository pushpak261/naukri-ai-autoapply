"""
Tests for the double-apply hardening: pre-claim (begin_application),
finalize_application, and the stuck-apply recovery sweeper.

Uses a temporary on-disk SQLite database, like test_database.py.
"""

import pytest
import pytest_asyncio

from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.models.db_schema import setup_database_manager
from src.naukri_agent.database.repository import SQLAlchemyRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    db_manager = await setup_database_manager(tmp_path / "claim.db")
    repository = SQLAlchemyRepository(db_manager)
    await repository.initialize()
    yield repository
    session_factory = await db_manager.get_session_factory()
    await session_factory.kw["bind"].dispose()


async def _make_job(repo, naukri_job_id="J1"):
    return await repo.save_job(
        naukri_job_id=naukri_job_id,
        title="Java Developer",
        company="Acme",
        url="https://naukri.com/job/1",
    )


@pytest.mark.asyncio
async def test_begin_then_finalize_single_row(repo):
    """A pre-claimed apply must finalize the SAME row (no duplicate)."""
    job = await _make_job(repo)
    app_id = await repo.begin_application(job.id, match_score=100.0)
    # Idempotent claim returns the same id on a second call.
    again = await repo.begin_application(job.id, match_score=100.0)
    assert again == app_id

    await repo.finalize_application(app_id, status=ApplicationStatus.APPLIED)
    # Exactly one application row exists for the job.
    stats = await repo.get_application_stats(days=1)
    assert stats["applied"] == 1
    assert stats["applied"] + stats["skipped"] + stats["failed"] == 1


@pytest.mark.asyncio
async def test_claim_blocks_reapply_within_run(repo):
    """After a claim, is_already_applied must treat the job as handled."""
    job = await _make_job(repo)
    await repo.begin_application(job.id, match_score=100.0)
    assert repo.is_already_applied(job.naukri_job_id) is True


@pytest.mark.asyncio
async def test_recover_stuck_flips_applying_to_failed(repo):
    """A stuck 'applying' row is recovered to 'failed' after the timeout."""
    job = await _make_job(repo)
    app_id = await repo.begin_application(job.id, match_score=100.0)
    # Immediately recover with a 0-minute timeout -> the just-claimed row is stale.
    recovered = await repo.recover_stuck_applications(timeout_minutes=0)
    assert recovered == 1
    # finalize must still be able to update the (now failed) row.
    await repo.finalize_application(app_id, status=ApplicationStatus.APPLIED)
    stats = await repo.get_application_stats(days=1)
    assert stats["applied"] == 1
