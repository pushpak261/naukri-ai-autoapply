"""Read a platform receipt only from the selected LinkedIn job's status card."""

import re
from urllib.parse import parse_qs, urlsplit


async def inline_submission_confirmed(page, job_id):
    url = page.url
    if not isinstance(url, str) or not str(job_id).isdigit():
        return False
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("linkedin.com", "www.linkedin.com"):
        return False
    match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)/?$", parsed.path)
    selected = match[1] if match else parse_qs(parsed.query).get("currentJobId", [""])[0]
    if selected != str(job_id):
        return False
    return await page.evaluate(
        r"""() => {
        const root = document.querySelector('main') || document.querySelector('section[aria-label="Primary content"]');
        if (!root) return false;
        const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).opacity !== '0' && !el.closest('[inert],[hidden],[aria-hidden="true"],aside,[componentkey^="JobDetailsSimilarJobs"]');
        const headings = [...root.querySelectorAll('h2,h3,h4')].filter(el=>visible(el) && /^application status$/i.test(el.innerText.trim()));
        return headings.some(heading => {
            for (let card=heading.parentElement; card && card !== root; card=card.parentElement) {
                if ((card.innerText || '').split('\n').some(line=>/^application submitted$/i.test(line.trim()))) return true;
            }
            return false;
        });
    }"""
    )
