"""Detect a signed-out LinkedIn surface before acting on a job.

LinkedIn can silently drop an automation session mid-run and serve the public
job-search page. That page still renders listings, but every Apply control
behind it is a sign-in prompt, so the agent mistook it for a job without Easy
Apply and skipped the whole remaining queue. Detect the signed-out header
instead and let the caller recover the session before navigating further.
"""

from __future__ import annotations

import asyncio

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


async def confirmed_signed_out(page, *, checks: int = 4, delay: float = 0.75) -> bool:
    """True only when the header still offers sign-in across several samples.

    LinkedIn first paints the public header before React swaps in the
    authenticated navigation, so a single sample taken right after a
    navigation can look signed out on a perfectly healthy session. Every
    false positive costs a full re-login (~90s) and stalls the queue, so
    require consecutive signed-out samples and stop as soon as the header
    shows a signed-in or ambiguous state.
    """
    checks = max(1, checks)
    for index in range(checks):
        if await state(page) != "signed_out":
            return False
        if index + 1 < checks:
            await asyncio.sleep(delay)
    return True
