# External employer applications

In **Preferences → Application Settings**, enable **Apply on external employer
websites with Gemini** and save. This sets `application.skip_external_apply: false`
for both agents and removes LinkedIn's conflicting Easy Apply-only search setting.
A saved Gemini API key is required. Native matching and screening can continue
with `ai.use_gemini: false`; the external form planner uses Gemini independently.
Changes apply to the next agent run.

During a Gemini outage or exhausted quota, `application.external_ai_enabled: false`
keeps company-site applications available from saved facts and confirmed answers
without making Gemini requests. Native `ai.use_gemini: false` selects local
matching and screening. Unknown answers remain in review. Re-enabling **Use
Gemini AI** in Preferences clears LinkedIn's temporary external-AI override.

After a listing passes the existing targeting and match checks, the external
handler opens the employer link in a separate browser context. Platform cookies
and passwords are not copied. Gemini maps visible field labels to an allowlisted
catalog of saved candidate facts. Personal facts must come from this catalog;
Gemini can also explain general technical questions without claiming personal
experience. Arbitrary browser actions are not accepted. Resume uploads use only the selected file within the
account's resume directory. Profile facts and form labels are sent to Gemini;
completed fields and the resume are sent to the employer.

Supported controls include text, email, telephone, numeric and date inputs,
selects, radio groups, supported comboboxes, Zoho skill tags, confirmed checkboxes, and resume
uploads, including hidden file inputs with visible Browse controls. Employer
landing pages can open the form through Apply Now, I'm interested, or Fill
Manually. Optional cookie notices are declined when a clear decline control is
available. The handler re-reads dynamic fields and embedded forms, validates
required values, and advances through bounded Next/Review steps. The application
counts as `applied` only after an explicit employer receipt message. A Submit
without confirmation is `uncertain` and stops the agent for review, preserving
duplicate-submission protection.

Career-page search, job-alert subscription and chat widgets are excluded from
both field collection and application actions. Repeated Apply Now links to the
same destination open one application form. Client-rendered employer forms have
up to 30 seconds to become ready before being reported as unsupported.
Dynamic country and resume-parser updates re-identify each question before
filling it, preserving answers when controls are replaced and replanning when
new fields appear. Navigation progress bars are excluded from Next/Review
actions. Named radio groups and hidden file inputs beside a visible Upload
Resume button are supported. Phone extensions, device types and calling codes
require their own evidence; the full contact number is never reused for them.
Phenom-style repeatable employment and education fieldsets keep every record
separate. Employment month/year controls and education year pickers retain the
precision requested by the employer. Explicit degree categories, locations and
grades come from the resume or confirmed answers; grade percentages retain
their units. Optional local-name and phone-extension controls can stay empty
only after an explicit not-applicable answer. Country-dependent authorization
and sponsorship questions are scoped to their position. A confirmed factual
question about an existing restrictive agreement is distinct from accepting a
new agreement, which still requires direct consent.

Recognized repeatable Education Details and Experience Details sections add
one row per saved resume record (up to ten of each, within the form's 80-control
limit). This includes Zoho's separate first-row and subsequent-row Add controls.
Each institution, degree, explicit major, employer, job title, responsibility
summary and date belongs to its own record. Current-employment and ongoing-study
checkboxes are set before inspecting date controls. An ongoing record has no end
date; optional end controls can remain empty only when its current checkbox is
checked. Required end controls still need valid input. Existing conflicting
history is left for review rather than overwritten.

Date evidence retains its precision: a known month/year fills separate month
and year controls or a month input, but cannot fill a date input requiring a day.
Missing history fields enter Screening answers with the institution or employer
and record identity in the question. A confirmed answer for one qualification
cannot fill a different qualification. Gemini cannot supply missing history.
AI resume parsing preserves stated education start/end dates and majors; older
profiles remain supported. Review missing education dates and streams before
starting applications.

Naukri can mark a job Applied as soon as its employer link is opened. This is
not an employer receipt. Known employer destinations are stored privately per
tenant and platform so a pre-submission screening retry can resume that form.
The normal application ledger continues to block submitted or uncertain jobs.

Every detected non-attachment question must be answered, including optional
questions. Unknown answers appear in **Applications → Screening answers**. Confirm
them once and retry; the tenant-local answer bank reuses exact questions and
preserves their units and employer-specific scope across runs. This is saved
answer memory, not continuous training of Gemini's underlying model. Validated
answers from a changed profile clear obsolete review prompts without becoming
stale confirmed answers. Profile settings include separate city, state and country
of residence; these do not establish citizenship or work authorization.

**Applications → Answer memory** lists remembered answers, their source and reuse
counts. Search, review or correct an answer, or forget its matching variants.
Each question appears once within its job or profile context, even when forms
reorder choices or use different controls. The saved count counts unique
questions; repeated answers to different skills, units or history records remain
separate facts. The latest confirmed correction takes precedence, and reuse
counts include all compatible form variants. Screening review also combines
repeated questions and their affected jobs. One confirmation resolves compatible
formats; a range cannot supply an unknown exact number for a different control.
Corrections take precedence over older answers for that exact question and units.
Corrections and forgetting also invalidate older native AI caches. Confirmation
ordering uses a persisted revision, so rapid edits remain deterministic even
when the system clock gives them the same timestamp.
Both native agents and the external handler consult the same tenant-local bank,
with Gemini enabled or disabled. Unknown native LinkedIn questions also enter
Screening answers. Job-specific motivations and role-fit answers stay scoped to
their job, including separate LinkedIn and Naukri identifiers.

Profile-derived answers and general technical explanations are remembered with
an evidence fingerprint; changing the saved profile invalidates older automatic
answers. Explicit user confirmations remain authoritative until corrected or
forgotten. Other AI suggestions are visible in memory but require confirmation
before the memory bank reuses them. Employer observations record accepted field
values, including committed skill tags, rather than unselected suggestions.
Forgetting a profile-derived answer does not erase its source resume or settings,
so the agent can derive it again. Memory persists in `data/screening_review.db`
inside the user's workspace; back up that workspace to preserve it across deployments.

Known answers are filled even when Gemini is unavailable, and the bot keeps
those values while collecting missing facts. Optional unsupported attachments
remain unfilled. Employer login,
CAPTCHA, agreements/signatures, unsupported widgets, ambiguous forms or different
submission origins require direct completion. The handler does not create ATS
accounts or bypass verification. Employer-specific sites can change or require
additional integrations; universal error-free application is not guaranteed.

`dry_run: true` allows opening and filling the form but prevents clicking Next,
Review or Submit. The normal agent
dry run scores jobs without entering the application flow. Daily caps, matching,
application claims and existing retry guards also apply to external jobs.

Regression tests use locally routed employer HTML and a fake Gemini provider;
`tests/test_external_applications.py` is included in the Chromium CI job. A live
Gemini connection can be checked with synthetic candidate data without sending
an application to an employer.
