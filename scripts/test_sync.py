import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.models.db_schema import setup_database_manager
from src.naukri_agent.database.repository import SQLAlchemyRepository
from sqlalchemy import select
from src.naukri_agent.models.db_schema import Job, Application


async def test_sync():
    print("Testing Background Synchronization...")
    settings = get_settings()

    db_manager = await setup_database_manager(settings.db_path)

    # 1. Force the manager into offline mode
    print("Simulating offline mode...")
    await db_manager.report_failure(Exception("Test failure"))

    repo = SQLAlchemyRepository(db_manager)
    await repo.initialize()

    # 2. Write data to SQLite
    print("Saving job and application to SQLite while offline...")
    job = await repo.save_job(
        naukri_job_id="SYNC_TEST_001",
        title="Sync Test Job",
        company="Sync Co",
        url="http://sync.com",
    )

    app = await repo.save_application(job_id=job.id, match_score=99.0, status="applied")
    print(f"Data saved to SQLite. Job ID: {job.id}, App ID: {app.id}")

    # 3. Simulate connection recovery
    print("Simulating internet recovery...")
    # Manually trigger the background sync logic for testing
    # Usually this is triggered periodically inside get_session_factory
    db_manager.active_engine = "primary"
    await db_manager._sync_secondary_to_primary()

    # 4. Verify data is in Supabase
    print("Verifying data in Supabase (Primary)...")
    primary_factory = db_manager.primary_factory
    async with primary_factory() as session:
        result = await session.execute(select(Job).filter(Job.naukri_job_id == "SYNC_TEST_001"))
        p_job = result.scalar_one_or_none()
        if p_job:
            print(f"Found Job in Supabase! New ID: {p_job.id}")
            # Verify Application
            app_result = await session.execute(
                select(Application).filter(Application.job_id == p_job.id)
            )
            p_app = app_result.scalars().first()
            if p_app:
                print(f"Found Application in Supabase! Linked correctly. New ID: {p_app.id}")
            else:
                print("ERROR: Application not found in Supabase.")
        else:
            print("ERROR: Job not synced to Supabase.")

    # 5. Verify SQLite is empty
    print("Verifying SQLite (Secondary) is empty...")
    secondary_factory = db_manager.secondary_factory
    async with secondary_factory() as session:
        job_count = len((await session.execute(select(Job))).scalars().all())
        app_count = len((await session.execute(select(Application))).scalars().all())
        print(f"SQLite remaining jobs: {job_count}, applications: {app_count}")
        if job_count == 0 and app_count == 0:
            print("Cleanup successful.")
        else:
            print("ERROR: SQLite not empty.")


if __name__ == "__main__":
    asyncio.run(test_sync())
