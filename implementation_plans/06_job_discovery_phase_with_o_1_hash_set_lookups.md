# Optimize Job Discovery Phase with O(1) Hash Set Lookups

The application already implements an optimal data structure at the database layer (a Python `set` which acts as a Hash Map/Set providing O(1) average time complexity for lookups, completely eliminating the O(N+1) database query problem). 

However, looking at the code architecture, this optimal DB check happens **too late** in the pipeline. Currently, `JobSearcher` scrapes *all* job cards across all search pages into a massive array in memory, and only later does the main `NaukriAgent` loop filter out the already-applied jobs.

To truly reduce the time and space complexity during the "Job Discovery (Search Phase)" as requested, we need to shift this O(1) check left into the searcher itself.

## Proposed Changes

### `src/orchestrator/factory.py`
Pass the repository into the `JobSearcher` when creating it:
#### [MODIFY] factory.py
```python
    def create_job_searcher(self) -> JobSearcher:
        return JobSearcher(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
            settings=self._settings,
            repository=self.get_repository(), # Inject repository for O(1) DB cache
        )
```

### `src/browser/search.py`
Inject the repository and use its O(1) cache (`is_already_applied()`) immediately during the post-processing of `_parse_job_cards()`. This ensures we immediately discard duplicate or already applied jobs, preventing them from being added to the `filtered_jobs` arrays and `all_jobs` master array.

#### [MODIFY] search.py
```python
class JobSearcher:
    def __init__(
        self, engine: IBrowserEngine, interactions: IBrowserInteractions, settings: Settings, repository: IRepository
    ) -> None:
        self._engine = engine
        self._interactions = interactions
        self._settings = settings
        self._repo = repository
...
    async def _parse_job_cards(self) -> list[dict]:
...
            # Post-process using Python helpers
            processed_jobs = []
            for job in raw_jobs:
                if job.get("title") and job.get("url"):
                    job_id = extract_naukri_job_id(job["url"])
                    
                    # --- PRODUCTION OPTIMIZATION (O(1) Hash Set Check) ---
                    # Immediately discard if we've already applied to this job ID.
                    if job_id and self._repo.is_already_applied(job_id):
                        continue

                    job["naukri_job_id"] = job_id
                    job["title"] = clean_text(job["title"])
...
```

### `src/orchestrator/agent.py`
We can leave the existing check in `agent.py` as a fail-safe, but now the queue size will be vastly smaller because the searcher has already pruned the N jobs down using the O(1) cache.

## Verification Plan
### Automated Verification
- Run `pytest` to ensure no dependency injection errors or type breaks occur.
- Run type checker `mypy src/`

### Manual Verification
- Execute `python -m src.main run --dry-run` and monitor the logs. We should see the total number of "unique jobs found" shrink dramatically, as previously applied jobs will be silently dropped before they even reach the orchestrator.
