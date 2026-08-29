"""
External-block detection for the Naukri agent.

Naukri actively fights automation: it can throw a CAPTCHA, demand an OTP,
rate-limit, or IP-ban the bot. These are *external* failures we cannot
prevent, but we can detect them from error text and react gracefully instead
of silently retrying forever (which makes the ban worse) or crashing.

When a block is detected the agent pauses and notifies an operator. The
``agent_blocked`` metric lets monitoring alert on it.
"""

from __future__ import annotations

_BLOCK_PATTERNS: dict[str, tuple[str, ...]] = {
    "captcha": (
        "captcha",
        "verify you are human",
        "i'm not a robot",
        "i am not a robot",
        "unusual traffic",
        "please verify",
    ),
    "otp": (
        "otp",
        "one-time password",
        "one time password",
        "enter the code sent",
        "verification code",
    ),
    "ip_ban": (
        "ip has been blocked",
        "ip address has been blocked",
        "access denied",
        "too many requests",
        "rate limit",
        "temporarily blocked",
        "try again later",
        "blocked from accessing",
    ),
}


def classify_block(text: str | None) -> str | None:
    """Return a block category (``captcha``/``otp``/``ip_ban``) or ``None``."""
    if not text:
        return None
    lowered = text.lower()
    for category, patterns in _BLOCK_PATTERNS.items():
        if any(p in lowered for p in patterns):
            return category
    return None
