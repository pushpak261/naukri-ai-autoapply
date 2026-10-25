// Visible employer controls only; never expose scripts or account credentials.
export default function inspectExternalForm() {
    // Conditional fields and cloned rows must not retain reused locator IDs.
    for (const name of ['field', 'skills', 'button', 'history', 'history-row', 'history-owner', 'history-add']) {
        const attribute = `data-applyos-${name}`;
        for (const el of document.querySelectorAll(`[${attribute}]`)) el.removeAttribute(attribute);
    }
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const text = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
    const labelText = el => {
        if (!el) return '';
        const copy = el.cloneNode(true);
        for (const child of copy.querySelectorAll('input,select,textarea,button,script,style,[role="combobox"],[role="listbox"]')) child.remove();
        return text(copy);
    };
    const historyRows = '.innerElem, [data-history-row], .education-entry, .experience-entry, fieldset[id^="experienceData["], fieldset[id^="educationData["]';
    const historyRow = el => !el.id?.match(/^(?:experienceData|educationData)\[/) || /^(?:experienceData|educationData)\[\d+\]$/.test(el.id);
    function historyKind(el) {
        const name = (el.getAttribute('data-l') || el.querySelector(':scope > legend')?.textContent || '').replace(/[\s:]+$/g, '');
        if (/^(?:education(?:al)?|academic)(?: details| history)?$/i.test(name.trim())) return 'education';
        if (/^(?:experience|employment|work experience|work history)(?: details| history)?$/i.test(name.trim())) return 'experience';
        return '';
    }
    function historyAdd(el, section) {
        if (!visible(el) || el.disabled) return false;
        if (!section.contains(el) && (!section.id || el.getAttribute('data-sectionid') !== section.id)) return false;
        const action = text(el).toLowerCase().replace(/^\+\s*/, '');
        if (!/^add(?: another)?(?: |$)/.test(action)) return false;
        const subject = action.replace(/^add(?: another)?\s*/, '');
        return ['', 'education', 'educational details', 'education details', 'education history',
            'experience', 'experience details', 'employment', 'employment history', 'work experience', 'work history'].includes(subject);
    }
    function collectHistory() {
        return [...document.querySelectorAll('div[data-l], fieldset')].filter(el => historyKind(el) && visible(el) && el.querySelector(historyRows)).map((section, i) => {
            const id = String(i);
            section.dataset.applyosHistory = id;
            const rows = [...document.querySelectorAll(historyRows)].filter(row => historyRow(row) && visible(row) && (section.contains(row) || (section.id && row.classList.contains(section.id))));
            rows.forEach((row, index) => { row.dataset.applyosHistoryRow = String(index); row.dataset.applyosHistoryOwner = id; });
            const add = [...document.querySelectorAll('a,button,[role="button"]')].find(el => historyAdd(el, section));
            if (add) add.dataset.applyosHistoryAdd = id;
            return {id, kind:historyKind(section), count:rows.length, addSelector:add ? `[data-applyos-history-add="${id}"]` : ''};
        });
    }
    const historySections = collectHistory();
    function historyFor(el) {
        const row = el.closest('[data-applyos-history-row]');
        const section = historySections.find(s => s.id === row?.dataset.applyosHistoryOwner);
        if (!section) return null;
        const raw = label(el, false);
        return {section:section.id, kind:section.kind, index:Number(row.dataset.applyosHistoryRow),
            label:raw, datePart:historyDatePart(el, raw),
            current:el.type === 'checkbox' && /currently|\bcurrent\b|\bpursuing\b/.test(raw.toLowerCase())};
    }
    function historyDatePart(el, raw) {
        const key = [raw, el.name, el.id, el.className].join(' ').toLowerCase();
        let endpoint = '';
        if (/(?:\bfrom\b|\bstart\b|_from_|_start_)/.test(key)) endpoint = 'start';
        else if (/(?:\bto\b|\bend\b|_to_|_end_)/.test(key)) endpoint = 'end';
        if (!endpoint) return '';
        if (['month', 'date'].includes(el.type)) return `${endpoint}_date`;
        if (/^experienceData\[\d+\]\.fromTo\.(?:start|end)Date$/.test(el.id) && el.closest('.react-datepicker-wrapper')) return `${endpoint}_month_year`;
        if (/^educationData\[\d+\]\.fromTo\.(?:start|end)Date$/.test(el.id) && el.closest('.react-datepicker-wrapper')) return `${endpoint}_year`;
        let component = 'date';
        if (/month/.test(key)) component = 'month';
        else if (/year/.test(key)) component = 'year';
        return `${endpoint}_${component}`;
    }
    function uploadControl(el) {
        if (el.type !== 'file') return null;
        const linked = [...(el.labels || []), el.closest('a, [role="button"]')].find(x => x && visible(x));
        if (linked) return linked;
        const parent = el.parentElement;
        if (!parent || parent.querySelectorAll('input[type="file"]').length !== 1) return null;
        const controls = [...parent.querySelectorAll('button, [role="button"]')].filter(x => visible(x) && /^(?:upload|browse|choose|attach)(?: (?:a|your|my))? (?:resume|cv|curriculum vitae)$/i.test(text(x)));
        return controls.length === 1 ? controls[0] : null;
    }
    function groupLabel(el) {
        const group = el.closest('[role="radiogroup"], fieldset');
        if (!group) return '';
        return group.getAttribute('aria-label') ||
            (group.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => labelText(document.getElementById(id))).filter(Boolean).join(' ') ||
            text(group.querySelector(':scope > legend'));
    }
    const label = (el, legend = true) => {
        const explicit = [
            ...(el.labels ? [...el.labels].map(labelText) : []), el.getAttribute('aria-label'),
            ...(el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(id => !id.endsWith('-live-region')).map(id => labelText(document.getElementById(id))),
            el.type === 'file' ? el.getAttribute('data-l') || uploadControl(el)?.getAttribute('aria-label') || text(uploadControl(el)) : ''
        ].filter(Boolean);
        const unique = [...new Map(explicit.map(value => [value.replace(/[\s*]+$/g, '').toLowerCase(), value])).values()];
        return (unique.join(' | ') || (legend ? groupLabel(el) : '') || el.getAttribute('placeholder') || el.name || '').slice(0, 1000);
    };
    function unrelatedControl(el) {
        // Career pages also contain search, subscriptions and chat. These are
        // never application fields, and their Submit buttons must not be used.
        if (el.closest('nav, header, footer, [role="search"], [role="navigation"], [role="tablist"], .navigation-summary[role="toolbar"], .phs-global-search-area, .phs-subscribe-jobs-area, #PhenomChatbotWidgetWindow')) return true;
        const unrelatedName = /^(?:(?:global|job|site) search|search (?:for )?jobs|job alerts?|job notifications?|get notified for similar jobs|chat(?:bot)?|virtual assistant)$/i;
        for (let scope = el.parentElement; scope && !scope.matches('body, main, html'); scope = scope.parentElement) {
            const name = scope.getAttribute('aria-label') || '';
            if (unrelatedName.test(name.trim())) return true;
        }
        return false;
    }
    function ignored(el) {
        const type = (el.type || '').toLowerCase();
        if (el.disabled || el.readOnly || unrelatedControl(el)) return true;
        if (['hidden', 'submit', 'button', 'reset', 'search'].includes(type)) return true;
        if (/^(?:save (?:this )?job|bookmark (?:this )?job)(?:\b|\s)/i.test(label(el, false))) return true;
        if (!visible(el) && !uploadControl(el)) return true;
        return el.getAttribute('role') === 'combobox' && !!el.querySelector('input');
    }
    function membersFor(el) {
        if (el.type !== 'radio' || !el.name) return [el];
        return [...document.querySelectorAll('input[type="radio"]')].filter(x => x.name === el.name && x.form === el.form && visible(x) && !x.disabled);
    }
    function optionsFor(el, members) {
        if (el.type === 'radio') return members.map(x => ({text: label(x, false), value: x.value}));
        if (el.tagName === 'SELECT') return [...el.options].filter(x => !x.disabled && x.value && !/^(select|choose)(\b|\s)/i.test(text(x))).map(x => ({text: text(x), value: x.value}));
        if (el.type === 'checkbox') return [{text:'Yes',value:'true'}, {text:'No',value:'false'}];
        return [];
    }
    function fieldKind(el) {
        if (el.matches('skills-tag input.skillset-input')) return 'skill_tags';
        if (el.tagName === 'SELECT') return 'dropdown';
        if (el.getAttribute('role') === 'combobox') return 'combobox';
        return (el.type || 'text').toLowerCase();
    }
    function fieldValue(el, members) {
        if (fieldKind(el) === 'skill_tags') return [...el.closest('skills-tag').querySelectorAll('.skl-selected-skill span[id^="skill-index-"]')].map(text).join(', ');
        if (el.type === 'checkbox') return el.checked ? 'Yes' : '';
        if (el.type === 'radio') return members.find(x => x.checked)?.value || '';
        if (el.type === 'file') return String(el.files?.length || '');
        return el.value || '';
    }
    function metadata(el, members, id) {
        members.forEach(x => {x.dataset.applyosField = id;});
        const form = el.form || el.closest('form');
        let question = label(el);
        let selector = `[data-applyos-field="${id}"]`;
        // Frameworks can replace inputs after resume parsing or country changes.
        // A unique DOM identity survives those replacements; numeric tags do not.
        if (el.type !== 'radio' && el.id && document.querySelectorAll(`#${CSS.escape(el.id)}`).length === 1) selector = `#${CSS.escape(el.id)}`;
        if (fieldKind(el) === 'skill_tags') {
            el.closest('skills-tag').dataset.applyosSkills = id;
            selector = `[data-applyos-skills="${id}"] input.skillset-input`;
        }
        if (el.type === 'radio') question = groupLabel(el) || question;
        return {id, selector, question, type:fieldKind(el),
            max_length:el.maxLength > 0 ? el.maxLength : null, min_length:el.minLength > 0 ? el.minLength : null,
            required:members.some(x => x.required || x.getAttribute('aria-required') === 'true') || label(el).includes('*') || uploadControl(el)?.getAttribute('aria-required') === 'true',
            options:optionsFor(el, members), multiple:!!el.multiple, action:form?.action || location.href,
            signature:[el.tagName, el.type, el.name, label(el)].join(':'),
            invalid:el.getAttribute('aria-invalid') === 'true' || (!!el.willValidate && !el.validity.valid),
            value:fieldValue(el, members), history:historyFor(el)};
    }
    function collectFields() {
        const fields = [], groups = new Set();
        for (const el of document.querySelectorAll('input, select, textarea, [role="combobox"]')) {
            if (ignored(el)) continue;
            const members = membersFor(el);
            if (groups.has(members[0])) continue;
            groups.add(members[0]);
            fields.push(metadata(el, members, String(fields.length)));
        }
        return fields;
    }
    function collectButtons() {
        return [...document.querySelectorAll('button, input[type="submit"], input[type="button"], a, [role="button"]')]
            .filter(el => visible(el) && !el.disabled && !unrelatedControl(el))
            .map((el, i) => {
                el.dataset.applyosButton = String(i);
                let formAction = el.form?.action || location.href;
                if (el.hasAttribute('formaction')) formAction = el.formAction;
                return {id:String(i), text:text(el) || el.value || el.getAttribute('aria-label') || '',
                    href:el.getAttribute('href') || '', formAction,
                    opensForm:!el.form && !el.closest('form') && !(el.tagName === 'INPUT' && el.type === 'submit'),
                    cookieDismiss:cookieDismiss(el)};
            });
    }
    function cookieDismiss(el) {
        if (el.form || el.closest('form') || !/^(?:decline non-essential|reject (?:all|optional)(?: cookies)?|only necessary cookies)$/i.test(text(el))) return false;
        let parent = el.parentElement;
        for (let depth = 0; parent && depth < 4; depth++, parent = parent.parentElement) {
            const notice = text(parent);
            if (notice.length < 3000 && /\bcookies?\b/i.test(notice)) return true;
        }
        return false;
    }
    function confirmed() {
        return [...document.querySelectorAll('h1,h2,h3,[role="status"],[role="alert"],p,#thanksmessage')].filter(visible).some(el => {
            if (el.closest('article, [class*="description"], [class*="recommend"]')) return false;
            const value = text(el);
            if (el.id === 'thanksmessage' && value.length < 2500 && /\bwe have (?:successfully )?received your application\b/i.test(value)) return true;
            return value.length < 1200 && /^(?:thank you for (?:applying|your application|submitting (?:your )?application)|we have (?:successfully )?received your application|your application (?:has been |was )?(?:successfully )?(?:submitted|received)|application (?:successfully )?(?:submitted|received))[.!\s]/i.test(value + ' ');
        });
    }
    const body = document.body?.innerText || '';
    const blocked = [...document.querySelectorAll('input[type="password"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"], [data-sitekey]')].some(visible) || /verify (?:you are|you're) human|access denied|sign in to apply|create an account to apply/i.test(body);
    const agreement = /by (?:clicking|submitting|continuing)[^.!\n]{0,180}\b(?:agree|accept|consent)\b/i.test(body);
    return {fields:collectFields(), historySections, buttons:collectButtons(), blocked, confirmation:confirmed(), agreement};
}
