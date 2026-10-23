# Naukri Target 100

In Command center, select Single → Naukri, enable **Target 100 verified
applications this run**, then Start. The CLI equivalent is
`python -m src.naukri_agent.main run --target 100`.

Target mode is an explicit choice for one run. It supports exactly 100,
requires live submissions and a configured daily cap of at least 100, and
uses Naukri's native Apply forms. It preserves saved credentials, candidate
facts, matching criteria, company policies and duplicate/application claims.
It does not change the saved external-application preference.

Only confirmed `applied` outcomes advance the run counter. Existing
applications, attempted applications, skips, failed answers and uncertain
receipts do not count. Processing stops before another job can be submitted
after the 100th confirmation. Progress appears separately from historical
application totals and is checkpointed privately within the user's workspace.

The browser, login and run log stay with the same run across discovery passes.
Already evaluated jobs are not attempted again, while unprocessed discovered
jobs remain eligible for a later pass. The existing daily cap remains in force;
the run can wait for the repository's UTC daily allowance to reset. Previous
daily submissions do not count toward the new run's target.

Discovery is bounded to three passes, expanding by five pages per search up to
15 pages. Target runs have a six-hour maximum instead of the normal one-hour
supervisor limit. This is not a recurring task. Manual Stop remains available.

An exhausted search, expired runtime, verification challenge, fatal browser
error or uncertain submission can prevent 100 confirmations. Such a run is
marked `target_not_met`, with its actual count and review reason, rather than
completed successfully. Resolve the reported blocker before requesting another
run. The bot does not fabricate screening facts, relax eligibility to reach a
number, bypass CAPTCHA or count unverified submissions.
