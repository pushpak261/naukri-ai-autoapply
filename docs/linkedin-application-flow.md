# LinkedIn applications

The LinkedIn agent searches the saved keywords and locations, keeps experience,
freshness and application filters when resolving a modern location picker, and
prioritizes the shared company preference list before evaluating eligible jobs.
An expired session, verification challenge or rate limit ends discovery for review.
The selected listing URL must identify the job being evaluated.
Its job-description content must also load before evaluation; a browser error
page cannot qualify from the URL alone. Entry/intern searches reject explicitly
senior, lead, architect and vice-president titles even if LinkedIn labels them
as entry level.
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
