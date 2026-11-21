"""Stable DOM anchors for LinkedIn's job detail layout.

LinkedIn's logged-in job page ships hashed CSS class names that change with
every frontend build, so the historical ``.jobs-description__content``
selectors silently stop matching. The "About the job" heading is stable text
and reliably precedes the description body.
"""

from __future__ import annotations

# `aboutSection()` climbs from the heading only until the container grows
# beyond the heading itself. Climbing by a fixed length threshold would
# swallow unrelated sections on short listings.
ABOUT_JOB_SECTION = r"""
const norm = t => (t || '').replace(/\s+/g, ' ').trim();
const heading = [...document.querySelectorAll('h1,h2,h3,h4,[role="heading"]')]
    .find(el => norm(el.innerText).toLowerCase() === 'about the job');
const headingLength = heading ? norm(heading.innerText).length : 0;
const aboutSection = () => {
    if (!heading) return '';
    let node = heading.parentElement;
    while (node && norm(node.innerText).length <= headingLength + 5 && node.parentElement) {
        node = node.parentElement;
    }
    return node ? norm(node.innerText) : '';
};
"""

# Returns the description text only; empty string when the listing has not
# rendered. Safe to call on search pages and job detail pages alike.
DESCRIPTION_TEXT = (
    "() => {"
    + ABOUT_JOB_SECTION
    + r"""
const text = aboutSection();
if (text.length > headingLength + 20) return text.replace(/^about the job\s*/i, '');
const legacy = document.querySelector(
    '[componentkey^="JobDetails_AboutTheJob_"], .jobs-description__content, '
    + '.jobs-box__html-content, .description__text, .show-more-less-html__markup'
);
if (legacy) {
    const legacyText = norm(legacy.innerText);
    if (legacyText.length > 20) return legacyText;
}
return '';
}"""
)

# Predicate for Playwright waits: the listing body has rendered.
LOADED_LISTING = (
    "() => {"
    + ABOUT_JOB_SECTION
    + r"""
const text = aboutSection();
if (text.length > headingLength + 20 && heading.getClientRects().length) return true;
return [...document.querySelectorAll(
    '[componentkey^="JobDetails_AboutTheJob_"], .jobs-description__content, '
    + '.jobs-box__html-content, .description__text, .show-more-less-html__markup, '
    + 'div[class*="description__text"], section[aria-label*="description" i], '
    + 'div[class*="jobs-description"]'
)].some(el => el.textContent.trim().length > 20 && (el.getClientRects().length > 0 || el.offsetParent !== null));
}"""
)
