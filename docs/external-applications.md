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
catalog of saved candidate facts; model-generated values and arbitrary browser
actions are not accepted. Resume uploads use only the selected file within the
account's resume directory. Profile facts and form labels are sent to Gemini;
completed fields and the resume are sent to the employer.

Supported controls include text, email, telephone, numeric and date inputs,
selects, radio groups, supported comboboxes, confirmed checkboxes, and resume
uploads. The handler re-reads dynamic fields and embedded forms, validates
required values, and advances through bounded Next/Review steps. The application
counts as `applied` only after an explicit employer receipt message. A Submit
without confirmation is `uncertain` and stops the agent for review, preserving
duplicate-submission protection.

Unknown required facts appear in **Applications → Screening answers**. Confirm
them and retry the job. Optional unknown facts remain unfilled. Employer login,
CAPTCHA, agreements/signatures, unsupported widgets, ambiguous forms or different
submission origins require direct completion. The handler does not create ATS
accounts or bypass verification. Employer-specific sites can change or require
additional integrations; universal error-free application is not guaranteed.

`dry_run: true` prevents advancing or submitting external forms. The normal agent
dry run scores jobs without entering the application flow. Daily caps, matching,
application claims and existing retry guards also apply to external jobs.

Regression tests use locally routed employer HTML and a fake Gemini provider;
`tests/test_external_applications.py` is included in the Chromium CI job. A live
Gemini connection can be checked with synthetic candidate data without sending
an application to an employer.
