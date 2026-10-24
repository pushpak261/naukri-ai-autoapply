# LinkedIn applications

The LinkedIn agent searches the saved keywords and locations, keeps experience,
freshness and application filters when resolving a modern location picker, and
prioritizes the shared company preference list before evaluating eligible jobs.
An expired session, verification challenge or rate limit ends discovery for review.
The selected listing URL must identify the job being evaluated.

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

Use Command center's Parallel mode to start LinkedIn while an existing Naukri run
continues. Starting both platforms reuses any already-running platform rather than
launching a duplicate. LinkedIn's file log is added even when the shared database
has already configured the root logger.
