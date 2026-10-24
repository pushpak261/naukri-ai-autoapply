"""Recognize native and employer Apply controls in the selected listing."""

SCRIPT = r"""({kind, click}) => {
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const root = document.querySelector('section[aria-label="Primary content"], .jobs-search__job-details, .job-details, [class*="scaffold-layout__detail"]') || document.querySelector('main') || document;
    const candidates = [...root.querySelectorAll('button, a[href], [role="button"]')].filter(el => {
        if (!visible(el) || el.disabled || el.closest('[aria-disabled="true"], aside, [role="complementary"], [componentkey^="JobDetailsSimilarJobsSlot_"], [componentkey^="job-card-component-ref-"]')) return false;
        const text = (el.innerText || '').trim(), label = el.getAttribute('aria-label') || '';
        return /^(easy apply|apply)(?:$|\s+(?:to|on)\b)/i.test(text) || /^(easy apply|apply)(?:$|\s+(?:to|on)\b)/i.test(label);
    });
    const external = el => {
        const label = (el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '');
        const href = el.getAttribute('href');
        if (/apply on\b/i.test(label)) return true;
        if (!href || href.startsWith('#')) return false;
        const url = new URL(href, location.href);
        return !['linkedin.com', 'www.linkedin.com'].includes(url.hostname) || url.pathname.startsWith('/safety/go');
    };
    const selected = candidates.find(el => kind === 'any' || (kind === 'external' ? external(el) : !external(el)));
    if (!selected) return false;
    if (click) selected.click();
    return true;
}"""


async def available(page, kind="any"):
    return await page.evaluate(SCRIPT, {"kind": kind, "click": False})


async def click(page, kind="any"):
    return await page.evaluate(SCRIPT, {"kind": kind, "click": True})
