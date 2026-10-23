# External employer applications

In **Preferences → Application Settings**, enable **Apply on external employer
websites with Gemini** and save. This sets `application.skip_external_apply: false`
for both agents and removes LinkedIn's conflicting Easy Apply-only search setting.
A saved Gemini API key is required. Native matching and screening can continue
with `ai.use_gemini: false`; the external form planner uses Gemini independently.
Changes apply to the next agent run.

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
