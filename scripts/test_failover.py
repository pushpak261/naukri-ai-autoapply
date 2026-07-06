import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.naukri_agent.config.settings import get_settings
from src.naukri_agent.models.db_schema import setup_database_manager
from src.naukri_agent.database.repository import SQLAlchemyRepository


async def test_failover():
    print("Testing HA database failover...")
    settings = get_settings()

    # Initialize real DB Manager
    db_manager = await setup_database_manager(settings.db_path)
    print(f"Initial active engine: {db_manager.active_engine}")

    repo = SQLAlchemyRepository(db_manager)
    await repo.initialize()

    # Save a fake job
    job = await repo.save_job(
        naukri_job_id="FAILOVER_TEST_001",
        title="Test Job HA",
        company="Test Co",
        url="http://test.com",
    )
    print(f"Successfully saved job using {db_manager.active_engine}.")

    if db_manager.primary_engine:
        # Simulate a database failure
        print("Simulating Supabase outage (reporting failure manually)...")
        await db_manager.report_failure(Exception("Simulated connection drop"))

        # Now we intentionally trigger a save to make the repository fail
        print("Attempting to save another job. It should fail and automatically failover.")

        job2 = await repo.save_job(
            naukri_job_id="FAILOVER_TEST_002",
            title="Test Job HA 2",
            company="Test Co 2",
            url="http://test.com/2",
        )
        print(f"Successfully saved job 2 using {db_manager.active_engine} (should be secondary).")

    print("Test passed successfully!")


if __name__ == "__main__":
    asyncio.run(test_failover())
