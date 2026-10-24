# LinkedIn applications

The LinkedIn agent searches the saved keywords and locations, keeps experience,
freshness and application filters when resolving a modern location picker, and
prioritizes the shared company preference list before evaluating eligible jobs.
An expired session, verification challenge or rate limit ends discovery for review.
The selected listing URL must identify the job being evaluated.
Its job-description content must also load before evaluation; a browser error
page cannot qualify from the URL alone. Entry, associate and intern searches reject explicitly
senior, lead, architect and vice-president titles even if LinkedIn labels them
as entry level.
Configured employment types are sent on every search and pagination fallback.
Full-time-only searches also reject internship titles locally, even when LinkedIn
returns them outside the selected filter.
Verified location IDs persist across restarts and are checked against the visible
destination label. Modern search cards exclude hidden copies and sidebar job
recommendations, so discovery and card indices refer to the result list.

Native Easy Apply questions use the shared resume, confirmed profile facts and
answer memory with Gemini disabled. Numeric experience questions remain numeric;
minimum-experience Yes/No questions are evaluated separately. Employment and notice
status are shared with the Naukri profile. Unknown required facts are collected for
review rather than invented.

Only the visible dialog is read. Every text, email, telephone, dropdown, radio and
checkbox answer is bound to its actual question and control. Missing options do
not select a different option or another question's field. Conditional questions
are read again after the form changes. Next, Review and Submit require valid
visible fields; an unrelated enabled button is never used as a step action.
Both native HTML dialogs and legacy role-based dialogs use this same flow.
Modern field wrappers supply labels for required city typeaheads; equivalent city
suggestions are accepted only within the control's associated list.
Resume uploads remain restricted to resume fields. One submission attempt is
followed by a platform receipt check; missing confirmation remains uncertain.

External employer applications retain their separate enabled setting and Gemini
key requirement. Employer-specific authentication, missing information or
unsupported steps remain visible in Applications. Native local answers do not
require Gemini.
Apply controls may be buttons or links. Employer links are followed only after
the popup listener is installed; they are not mistaken for a native modal.

Use Command center's Parallel mode to start LinkedIn while an existing Naukri run
continues. Starting both platforms reuses any already-running platform rather than
launching a duplicate. LinkedIn's file log is added even when the shared database
has already configured the root logger.
Parallel mode also provides a Stop button for each platform, using the existing
platform-specific stop endpoint.
Saved listings can also start the normal agent pipeline directly from Job details,
with the same eligibility, duplicate, validation and submission checks.

Application steps wait for usable form content instead of treating a dialog
heading or loading spinner as a completed step. Inert, hidden and transparent
search popovers cannot replace the active application dialog. Native HTML dialogs
also support resume uploads. A form that stalls before Submit is a retryable
failure; only a submission attempt without a receipt is uncertain.

LinkedIn uses Chromium's normal process model so an isolated employer context can
open and close without disconnecting the source browser. Employer failures expose
the exception category without logging personal form values or token-bearing URLs.
Transient network failures retry the same URL four times with bounded delays.
Persistent outages stop the run with a connectivity error instead of rejecting
remaining listings as unsuitable. Matching rejections include their saved reason
in the live output. Disabled email notifications retain the local report without
attempting an email.
LinkedIn's custom "Invalid input" feedback is checked in addition to HTML
validity. When a text control rejects units, known salary and notice facts can
use their numeric representation, preserving annual currency conversion. A
confirmed day/month/year birth date can use the same date as eight digits when
the platform rejects separators. Unknown facts are never replaced by numbers.
LinkedIn question reviews resolve the mirrored dashboard job ID before queueing
a retry. Job details support multiple attempts while retaining any prior applied,
applying or uncertain status as a submission guard.
Receipt checks also accept the selected job's inline Application status card;
another job's status, a recommendation or a closed dialog cannot establish a
submission. Confirmation is allowed up to twenty seconds without clicking Submit
again. `verify-application JOB_ID` inspects the configured LinkedIn session and
saves a private screenshot without submitting or changing any application.
