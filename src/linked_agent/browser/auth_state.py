"""Detect a signed-out LinkedIn surface before acting on a job.

LinkedIn can silently drop an automation session mid-run and serve the public
job-search page. That page still renders listings, but every Apply control
behind it is a sign-in prompt, so the agent mistook it for a job without Easy
Apply and skipped the whole remaining queue. Detect the signed-out header
instead and let the caller recover the session before navigating further.
"""

from __future__ import annotations

SCRIPT = r"""() => {
    const header = document.querySelector('header.global-nav, nav.global-nav, header');
    if (!header) return 'unknown';
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    const labels = [...header.querySelectorAll('a, button')]
        .filter(visible)
        .map(el => ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).trim().toLowerCase())
        .filter(Boolean);
    if (labels.some(label => /^(sign in|join now)$/.test(label))) return 'signed_out';
    if (labels.some(label => label === 'me')) return 'signed_in';
    const text = (header.innerText || '').toLowerCase();
    if (/\bme\b/.test(text) && /\bjobs\b/.test(text)) return 'signed_in';
    return 'unknown';
}"""


async def state(page) -> str:
    """Return 'signed_in', 'signed_out' or 'unknown' without reading account data."""
    try:
        return await page.evaluate(SCRIPT)
    except Exception:
        return "unknown"


async def signed_out(page) -> bool:
    """True only when the global header clearly offers sign-in/join controls."""
    return await state(page) == "signed_out"
