"""Bounded, single-run target control; only verified native submissions count."""

import asyncio
import time
from datetime import UTC, datetime, timedelta

from libs.common.run_target import MAX_RUNTIME_SECONDS, TARGET, write_target_progress
from src.naukri_agent.utils.exceptions import SearchAccessError, SearchLoadError
from src.naukri_agent.utils.logger import log_info, log_success, log_warning


async def checkpoint(agent, state="running", reason=""):
    if agent._settings.application.run_target != TARGET:
        return
    await asyncio.to_thread(
        write_target_progress,
        agent._settings.project_root,
        run_id=agent._run_log_id,
        submitted=agent._jobs_applied,
        found=agent._jobs_found,
        state=state,
        reason=reason,
        native_only=True,
    )
    if agent._repo and agent._run_log_id:
        await agent._repo.update_run_log(
            run_log_id=agent._run_log_id,
            jobs_found=agent._jobs_found,
            jobs_applied=agent._jobs_applied,
            jobs_skipped=agent._jobs_skipped,
            jobs_failed=agent._jobs_failed,
            status="running",
        )


def fresh_jobs(agent, jobs):
    if agent._settings.application.run_target != TARGET:
        agent._jobs_found = max(agent._jobs_found, len(jobs))
        return jobs
    for job in jobs:
        agent._target_discovered.add(job.naukri_job_id or job.url)
    agent._jobs_found = len(agent._target_discovered)
    return [job for job in jobs if (job.naukri_job_id or job.url) not in agent._target_processed]


def expired(agent):
    return time.monotonic() >= agent._target_deadline


async def wait(agent, seconds, reason):
    log_info(reason)
    await checkpoint(agent, "waiting", reason)
    for _ in range(max(0, int(seconds))):
        if agent._interrupted or expired(agent):
            return
        await asyncio.sleep(1)


async def _has_daily_allowance(agent):
    today = await agent._repo.get_today_application_count(source="naukri") if agent._repo else 0
    if today < agent._settings.application.daily_cap:
        return True
    now = datetime.now(UTC)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    await wait(
        agent,
        (reset - now).total_seconds() + 1,
        "Daily cap reached; preserving this run and waiting for the daily allowance to reset.",
    )
    return False


async def _search_once(agent, search_pass):
    try:
        await search_pass()
    except SearchAccessError:
        agent._target_stop_reason = "Naukri sign-in or verification requires your attention"
        raise
    except SearchLoadError as error:
        log_warning(f"Search unavailable: {error}")


async def run_search_cycles(agent, search_pass):
    settings = agent._settings
    if settings.application.run_target != TARGET:
        await search_pass()
        return
    if settings.application.dry_run:
        raise ValueError("A submission target requires Dry Run to be disabled")
    settings.application.skip_external_apply = True
    # Spend the bounded discovery budget on matching jobs. Date order can
    # bury relevant roles below unrelated fresh listings on Naukri.
    settings.search.sort_by = "relevance"
    settings.search.max_pages = min(15, settings.search.max_pages)
    agent._target_deadline = time.monotonic() + MAX_RUNTIME_SECONDS
    log_info("Run target: 100 NEW verified native Naukri submissions; skips/failures do not count.")
    log_info(
        "Discovery is bounded to three passes (up to 15 pages per search), within six hours. Existing daily and eligibility limits remain in force."
    )
    await checkpoint(agent)
    passes = 0
    while not agent._interrupted and not expired(agent) and passes < 3:
        if not await _has_daily_allowance(agent):
            continue
        passes += 1
        await _search_once(agent, search_pass)
        if agent._jobs_applied >= TARGET:
            log_success("Run target reached: 100/100 verified submissions.")
            await checkpoint(agent, "target_met", "100 verified submissions reached")
            return
        if agent._run_error or agent._interrupted:
            agent._target_stop_reason = "Review the live output: verification, browser or submission uncertainty blocked this run"
            break
        settings.search.max_pages = min(15, settings.search.max_pages + 5)
        if passes < 3:
            await wait(
                agent,
                300,
                f"{agent._jobs_applied}/100 verified; preparing the next discovery pass.",
            )
    agent._target_stop_reason = (
        agent._target_stop_reason
        or "Target not reached within the available eligible jobs and bounded run limits"
    )
    await checkpoint(agent, "target_not_met", agent._target_stop_reason)
