"""
Application-wide constants for the LinkedIn Agent.

Contains URLs, timeouts, and resilient selectors (preferring XPath with
text matching over volatile CSS classes) specific to LinkedIn.
"""

# =============================================================================
# LinkedIn URLs
# =============================================================================
LINKEDIN_BASE_URL = "https://www.linkedin.com"
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/"
LINKEDIN_JOBS_SEARCH_URL = "https://www.linkedin.com/jobs/search/"

# Search URL template with query parameters
LINKEDIN_SEARCH_TEMPLATE = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords={keywords}"
    "&location={location}"
    "&f_TPR={freshness}"
    "&f_E={experience}"
    "&sortBy={sort_by}"
    "&start={start}"
    "&f_WT={work_type}"
    "&f_AL=true"  # Easy Apply filter — only show jobs with Easy Apply
)


# =============================================================================
# Timeouts (in milliseconds for Playwright)
# =============================================================================
DEFAULT_TIMEOUT = 30_000
NAVIGATION_TIMEOUT = 45_000
LOGIN_TIMEOUT = 120_000
ELEMENT_TIMEOUT = 30_000
APPLY_TIMEOUT = 20_000
LINKEDIN_RATE_LIMIT_DELAY = 2_000  # 2s between page loads — faster pagination


# =============================================================================
# Retry Configuration
# =============================================================================
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2


# =============================================================================
# Browser Configuration
# =============================================================================
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_LOCALE = "en-US"
DEFAULT_TIMEZONE = "America/New_York"


# =============================================================================
# LinkedIn Experience Level Mapping
# =============================================================================
EXPERIENCE_LEVEL_MAP = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}


# =============================================================================
# LinkedIn Job Type Filter Values
# =============================================================================
JOB_TYPE_MAP = {
    "full-time": "F",
    "part-time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "volunteer": "V",
}


# =============================================================================
# LinkedIn Freshness Filter Values (past seconds)
# =============================================================================
FRESHNESS_MAP = {
    "any": "",
    "past_24h": "86400",
    "past_week": "604800",
    "past_month": "2592000",
}


# =============================================================================
# LinkedIn Work Type Filter Values
# =============================================================================
WORK_TYPE_MAP = {
    "on_site": "1",
    "remote": "2",
    "hybrid": "3",
}


# =============================================================================
# Selectors — Using text-based XPath and robust attribute selectors.
# LinkedIn's DOM changes frequently; these are chosen for maximum resilience.
# =============================================================================


class LoginSelectors:
    """Selectors for the LinkedIn login page."""

    # Login form inputs — ordered by reliability (id > name > aria-label > type)
    EMAIL_INPUT = 'input[type="email"]:visible, #username, input[name="session_key"], input[id="username"], input[aria-label*="Email" i], input[aria-label*="username" i], input[placeholder*="Email" i], input[placeholder*="username" i], input[type="text"]'
    PASSWORD_INPUT = 'input[type="password"]:visible, #password, input[name="session_password"], input[id="password"]'
    LOGIN_BUTTON = 'button:has-text("Sign in"):not(:has-text("with")):visible, button:has-text("Log in"):not(:has-text("with")):visible, button[type="submit"]:visible, button[name="submit"]:visible, button[data-litms-control-urn="login-submit"]:visible'

    # 2FA / Verification
    OTP_INPUT = 'input#otp-input, input[name="challengePin"], input[aria-label*="code" i], input[name="pin"]'
    OTP_SUBMIT = 'button[type="submit"], button:has-text("Verify"), button:has-text("Submit")'

    # Login success indicators
    LOGGED_IN_INDICATORS = [
        "img.global-nav__me-photo",
        'img[data-delayed-url*="profile-display"]',
        'img[data-delayed-url*="ghost-profile"]',
        'img[alt*="My profile"]',
        "li.global-nav__me",
        'a[href*="/feed/"]',
        'a[href*="/mynetwork/"]',
        'button[aria-label*="Notifications" i]',
        "div.global-nav__me",
        "#voyager-feed",
        'li-nav-item[href*="feed"]',
    ]

    # Error messages
    LOGIN_ERROR = 'div[role="alert"], div[class*="error"], p[class*="error"], .form__error--link'

    # Not logged in indicators
    NOT_LOGGED_IN_INDICATORS = 'button:has-text("Sign in"), a[href*="/login"], a[href*="/signup"]'


class SearchSelectors:
    """Selectors for the LinkedIn job search results page."""

    # Job listing cards
    JOB_CARD = '.jobs-search-results__list-item, .job-card-container, li.jobs-search-results__list-item, div[data-entity-urn*="jobPosting"]'
    JOB_TITLE = ".job-card-list__title--link, h3.base-card__full-link, h3 a, .job-card-container__link, span.artdeco-entity-lockup__title a"
    JOB_COMPANY = ".job-card-container__primary-description, .job-card-container__company-name, .artdeco-entity-lockup__subtitle, .base-search-card__subtitle"
    JOB_LOCATION = ".job-card-container__metadata-item, .job-card-container__bullet, .artdeco-entity-lockup__caption, .base-search-card__metadata span:first-child"
    JOB_LINK = '.job-card-list__title--link, h3.base-card__full-link, h3 a[href*="/jobs/view/"], .job-card-container__link'
    JOB_POSTED_DATE = ".job-card-container__listed-date, .job-card-container__footer-item, time"
    JOB_DESCRIPTION_SNIPPET = ".job-card-container__description, .artdeco-entity-lockup__snippet"

    # LinkedIn-specific: Easy Apply badge (text-based only, no .jobs-apply-button class)
    EASY_APPLY_BADGE = (
        'span:has-text("Easy Apply"), button[aria-label*="Easy Apply" i]'
    )

    # Pagination
    NEXT_PAGE = 'button[aria-label="View next page"], button:has-text("Next"), li.artdeco-pagination__indicator--number:last-child a'
    PAGE_NUMBERS = ".artdeco-pagination__indicator--number a"

    # No results
    NO_RESULTS = (
        '.jobs-search-results__no-results, .jobs-search-no-results, .jobs-search-two-pane__no-results, '
        'div:has-text("No results found"), div:has-text("No matching jobs found"), '
        'div:has-text("No matching jobs"), div:has-text("No jobs found"), '
        'div:has-text("things aren\'t loading")'
    )

    # Filter controls
    SEARCH_INPUT = 'input[aria-label*="Search" i], input[placeholder*="Search" i]'
    LOCATION_INPUT = 'input[aria-label*="City" i], input[aria-label*="Location" i], input[placeholder*="City" i], input[placeholder*="Location" i]'


class JobDetailSelectors:
    """Selectors for individual job detail pages on LinkedIn."""

    JOB_TITLE = "h1.job-details-jobs-unified-top-card__job-title, h1.top-card-layout__title, h1.job-title, .job-details-jobs-unified-top-card__job-title span"
    COMPANY_NAME = ".job-details-jobs-unified-top-card__company-name a, .top-card-layout__second-line a, .job-details-jobs-unified-top-card__company-name"
    JOB_DESCRIPTION = '.jobs-description__content, .jobs-box__html-content, .description__text, .show-more-less-html__markup, div[class*="description"]'
    KEY_SKILLS = ".job-details-jobs-unified-top-card__job-insight span, .job-insight__text"
    EXPERIENCE_DETAIL = ".job-details-jobs-unified-top-card__job-insight--primary span:first-child"
    SALARY_DETAIL = '.job-details-jobs-unified-top-card__job-insight span:has-text("₹"), .salary, span:has-text("/yr")'
    LOCATION_DETAIL = ".job-details-jobs-unified-top-card__primary-description span, .top-card-layout__headline span"

    # Apply buttons — LinkedIn often shows "Apply" (without "Easy") that opens
    # the same Easy Apply modal. Match both to avoid missing the modal flow.
    APPLY_BUTTON = (
        'button:has-text("Easy Apply"), button[aria-label*="Easy Apply" i], '
        'button:has-text("Apply"):not(:has-text("Easy")), '
        'button[aria-label*="Apply" i]:not([aria-label*="Easy Apply" i]):not([aria-label*="Applied" i])'
    )
    ALREADY_APPLIED = (
        'button:text-is("Applied"), span:text-is("Applied"), '
        'button[aria-label*="Applied" i]:not([aria-label*="Easy Apply" i]):not([aria-label*="Apply on" i])'
    )
    EXTERNAL_APPLY = (
        'button:has-text("Apply on"), '
        'a:has-text("Apply on"), '
        'a[aria-label*="Apply on company" i], '
        'a:has-text("Apply"):not(:has-text("Easy")):not(:has-text("Apply on")), '
        'button[aria-label*="Apply on" i]'
    )
    SAVE_BUTTON = 'button[aria-label*="Save" i], button:has-text("Save")'

    # Easy Apply modal selectors
    EASY_APPLY_MODAL = 'div.jobs-easy-apply-modal, div[role="dialog"], div.artdeco-modal'
    EASY_APPLY_FORM = 'form.jobs-easy-apply-modal, form[aria-label*="Apply" i]'
    MULTI_STEP_FORM = ".jobs-easy-apply-modal"

    # Screening question selectors within Easy Apply modal
    QUESTION_LABEL = ".jobs-easy-apply-modal label, .jobs-easy-apply-modal .t-14"
    TEXT_INPUT = 'input[type="text"]:not([type="hidden"]), input[type="number"], textarea'
    DROPDOWN = 'select, div[role="listbox"], div[role="combobox"]'
    RADIO_BUTTON = 'input[type="radio"], div[role="radio"]'
    CHECKBOX = 'input[type="checkbox"], div[role="checkbox"]'

    # Easy Apply navigation buttons within modal
    SUBMIT_BUTTON = 'button[aria-label*="Submit" i], button:has-text("Submit application")'
    NEXT_BUTTON = (
        'button[aria-label*="Continue" i], button[aria-label*="Next" i], button:has-text("Next")'
    )
    REVIEW_BUTTON = 'button[aria-label*="Review" i], button:has-text("Review")'
    CANCEL_BUTTON = (
        'button[aria-label*="Dismiss" i], button[aria-label*="Cancel" i], button:has-text("Cancel")'
    )

    # Success indicators
    APPLICATION_SUCCESS = 'div:has-text("Application sent"), div:has-text("Your application was sent"), span:has-text("application was sent")'

    # Resume upload
    RESUME_UPLOAD = 'input[type="file"]'

    # Post-application follow-up
    FOLLOW_COMPANY_CHECKBOX = (
        'input#follow-company-checkbox, label:has-text("Follow") input[type="checkbox"]'
    )

    # Popup / dialog
    POPUP_CLOSE = (
        'button[aria-label="Dismiss" i], button[aria-label="Close" i], button:has-text("Close")'
    )
    OVERLAY_DISMISS = 'button.artdeco-modal__dismiss, button[aria-label="Dismiss" i]'


# =============================================================================
# Application Status Constants
# =============================================================================
class ApplicationStatus:
    """Enum-like constants for application status tracking."""

    APPLIED = "applied"
    SKIPPED_LOW_SCORE = "skipped_low_score"
    SKIPPED_EXCLUDED = "skipped_excluded"
    SKIPPED_ALREADY_APPLIED = "skipped_already_applied"
    SKIPPED_EXTERNAL = "skipped_external"
    SKIPPED_SCREENING = "skipped_screening"
    SKIPPED_DRY_RUN = "skipped_dry_run"
    SKIPPED_EASY_APPLY_UNAVAILABLE = "skipped_easy_apply_unavailable"
    UNCERTAIN = "uncertain"
    FAILED = "failed"
    ERROR = "error"


# =============================================================================
# LinkedIn-specific constants
# =============================================================================
LINKEDIN_MIN_DELAY_BETWEEN_ACTIONS = 2.0  # Seconds — LinkedIn is strict but 2s is safe
LINKEDIN_MAX_DELAY_BETWEEN_ACTIONS = 5.0
LINKEDIN_MIN_DELAY_BETWEEN_APPLIES = 90.0  # Seconds between applications (1.5 min)
LINKEDIN_MAX_DELAY_BETWEEN_APPLIES = 300.0  # 5 min max between applies
LINKEDIN_DAILY_APPLY_CAP = 100  # LinkedIn limits Easy Apply to ~200/day recommended
LINKEDIN_SESSION_COOKIE_NAME = "li_at"
LINKEDIN_CSRF_COOKIE_NAME = "JSESSIONID"
