"""
Application-wide constants for the Naukri Agent.

Contains URLs, timeouts, and resilient selectors (preferring XPath with
text matching over volatile CSS classes).
"""

# =============================================================================
# Naukri.com URLs
# =============================================================================
NAUKRI_BASE_URL = "https://www.naukri.com"
NAUKRI_LOGIN_URL = "https://www.naukri.com/nlogin/login"
NAUKRI_DASHBOARD_URL = "https://www.naukri.com/mnjuser/homepage"
NAUKRI_SEARCH_URL = "https://www.naukri.com/jobsearch"

# Search URL template — parameters are appended as query params
# Example: https://www.naukri.com/python-developer-jobs-in-bangalore?k=python+developer&l=bangalore&experience=3&nignbevent_src=jobsearchDeskGNB
NAUKRI_SEARCH_TEMPLATE = "https://www.naukri.com/{slug}-jobs"


# =============================================================================
# Timeouts (in milliseconds for Playwright)
# =============================================================================
DEFAULT_TIMEOUT = 30_000  # 30 seconds — general page load
NAVIGATION_TIMEOUT = 45_000  # 45 seconds — page navigation
LOGIN_TIMEOUT = 120_000  # 120 seconds — wait for OTP
ELEMENT_TIMEOUT = 30_000  # 30 seconds — wait for element
APPLY_TIMEOUT = 20_000  # 20 seconds — apply flow


# =============================================================================
# Retry Configuration
# =============================================================================
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Exponential backoff base in seconds


# =============================================================================
# Browser Configuration
# =============================================================================
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_LOCALE = "en-IN"
DEFAULT_TIMEZONE = "Asia/Kolkata"


# =============================================================================
# Selectors — Using text-based XPath for resilience against class name changes.
# These are organized by page/flow.
# =============================================================================


class LoginSelectors:
    """Selectors for the Naukri login page."""

    # Login form inputs — using placeholder/type attributes (more stable)
    EMAIL_INPUT = 'input[placeholder="Enter Email ID / Username"], input[placeholder*="Email ID"], input[placeholder*="Username"]'
    PASSWORD_INPUT = 'input[placeholder="Enter Password"], input[placeholder*="Password"]'
    LOGIN_BUTTON = '//button[contains(text(), "Login")]'

    # Direct OTP login selectors
    USE_OTP_LOGIN_LINK = (
        '//button[contains(text(), "Use OTP to Login")] | //*[contains(text(), "Use OTP to Login")]'
    )
    MOBILE_INPUT = 'input[placeholder*="mobile number" i], input[placeholder*="Mobile Number" i], input[id="mobile-input"]'
    GET_OTP_BUTTON = '//button[contains(text(), "Get OTP")]'

    # OTP flow
    OTP_INPUT = 'input[placeholder*="OTP"]'
    OTP_SUBMIT = (
        '//button[contains(text(), "Submit") or contains(text(), "Verify") or text()="Login"]'
    )

    # Login success indicators
    PROFILE_ICON = '//a[contains(@href, "mnjuser") or contains(@class, "nI-gNb-drawer")]'
    USER_NAME_ELEMENT = '[class*="nI-gNb-sb__main"]'

    # Error messages
    LOGIN_ERROR = '//span[contains(@class, "err") or contains(@class, "error")]'

    # Not logged in indicators
    NOT_LOGGED_IN_INDICATORS = 'a#login_Layer, a:has-text("Login")'


class SearchSelectors:
    """Selectors for the Naukri job search results page."""

    # Job listing cards
    JOB_CARD = '[class*="srp-jobtuple-wrapper"], [class*="jobTuple"], article[class*="job"]'
    JOB_TITLE = 'a[class*="title"]'
    JOB_COMPANY = '[class*="comp-name"], [class*="companyInfo"] a'
    JOB_LOCATION = '[class*="loc-wrap"], [class*="location"]'
    JOB_EXPERIENCE = '[class*="exp-wrap"], [class*="experience"]'
    JOB_SALARY = '[class*="sal-wrap"], [class*="salary"]'
    JOB_DESCRIPTION_SNIPPET = '[class*="job-desc"], [class*="jobDescription"]'
    JOB_LINK = 'a[class*="title"]'
    JOB_POSTED_DATE = '[class*="job-post-day"], [class*="postDate"]'
    JOB_TAGS = '[class*="tag-li"], [class*="skill-tag"]'

    # Pagination
    NEXT_PAGE = '//a[contains(@class, "fright") and contains(text(), "Next")]'
    PAGE_NUMBERS = '[class*="pagination"] a'

    # No results
    NO_RESULTS = '//div[contains(text(), "No matching jobs") or contains(text(), "0 results")]'


class JobDetailSelectors:
    """Selectors for individual job detail pages."""

    JOB_TITLE = '[class*="jd-header-title"], h1'
    COMPANY_NAME = '[class*="jd-header-comp-name"], [class*="company-name"] a'
    JOB_DESCRIPTION = '[class*="job-desc"], [class*="dang-inner-html"]'
    KEY_SKILLS = '[class*="key-skill"] a, [class*="chip-body"]'
    EXPERIENCE_DETAIL = '[class*="exp"] [class*="details"]'
    SALARY_DETAIL = '[class*="sal"] [class*="details"]'
    LOCATION_DETAIL = '[class*="loc"] [class*="details"]'

    # Apply buttons
    APPLY_BUTTON = '//button[contains(text(), "Apply") and not(contains(text(), "Applied"))]'
    ALREADY_APPLIED = (
        '//*[contains(text(), "Already Applied") or contains(text(), "already applied")]'
    )
    EXTERNAL_APPLY = (
        '//*[contains(text(), "Apply on company") or contains(text(), "apply on company")]'
    )

    # Chatbot / overlay
    CHATBOT_CLOSE = '//button[contains(@class, "chatbot-close") or @aria-label="Close"]'
    POPUP_CLOSE = '//button[contains(@class, "close") or @aria-label="Close"]'


class ApplyFlowSelectors:
    """Selectors for the job application submission flow."""

    # Apply confirmation modal / form
    APPLY_FORM = '[class*="apply-modal"], [class*="apply-form"], [class*="chatbot-container"]'

    # Common screening question fields
    QUESTION_CONTAINER = '[class*="question"], [class*="chatbot-msg"]'
    TEXT_INPUT = 'input[type="text"], textarea'
    DROPDOWN = "select"
    RADIO_BUTTON = 'input[type="radio"]'
    CHECKBOX = 'input[type="checkbox"]'

    # Submit / Next buttons in the apply flow
    SUBMIT_BUTTON = '//button[contains(text(), "Submit") or contains(text(), "Apply")]'
    NEXT_BUTTON = '//button[contains(text(), "Next") or contains(text(), "Continue")]'
    SKIP_BUTTON = '//button[contains(text(), "Skip")]'

    # Success indicators
    APPLICATION_SUCCESS = (
        '//*[contains(text(), "applied successfully") or contains(text(), "Application Submitted")]'
    )

    # Resume upload
    RESUME_UPLOAD = 'input[type="file"]'

    # Fallback and inline selectors
    FORM_FALLBACK = 'form[class*="apply"]'
    CHATBOT_MSG_FALLBACK = '[class*="chatbot-msg"]'
    SCREENING_FALLBACK = '[class*="screening"]'
    GENERIC_SUBMIT = '//button[contains(text(), "Submit")]'
    GENERIC_APPLY = '//button[contains(text(), "Apply")]'
    GENERIC_SUBMIT_TYPE = 'button[type="submit"]'
    SUCCESS_SUBMITTED = '//*[contains(text(), "submitted")]'
    SUCCESS_RECEIVED = '//*[contains(text(), "received your application")]'


class ProfileSelectors:
    """Selectors for the Naukri profile page."""

    PROFILE_URL = "https://www.naukri.com/mnjuser/profile"

    # Locate the span containing 'Resume headline' and find the following sibling with class 'edit'
    RESUME_HEADLINE_EDIT_ICON = '//span[contains(text(), "Resume headline")]/following-sibling::span[contains(@class, "edit")]'

    # Save button in the modal (exact text match to avoid hidden 'Save photo' button)
    SAVE_BUTTON = '//button[text()="Save" or normalize-space(text())="Save"]'


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
    SKIPPED_DRY_RUN = "skipped_dry_run"
    FAILED = "failed"
    ERROR = "error"
