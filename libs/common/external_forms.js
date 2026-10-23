// Visible employer controls only; never expose scripts or account credentials.
export default function inspectExternalForm() {
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const text = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
    const label = (el, legend = true) => {
        const explicit = [
            ...(el.labels ? [...el.labels].map(text) : []), el.getAttribute('aria-label'),
            ...(el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => text(document.getElementById(id))),
            legend ? el.closest('fieldset')?.querySelector('legend')?.textContent : ''
        ].filter(Boolean).join(' | ');
        return (explicit || el.getAttribute('placeholder') || el.name || '').slice(0, 500);
    };
    function ignored(el) {
        const type = (el.type || '').toLowerCase();
        if (el.disabled || el.readOnly || el.closest('nav, header, footer, [role="search"]')) return true;
        if (['hidden', 'submit', 'button', 'reset', 'search'].includes(type)) return true;
        const uploadLabel = type === 'file' && el.labels && [...el.labels].some(visible);
        if (!visible(el) && !uploadLabel) return true;
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
        if (el.tagName === 'SELECT') return 'dropdown';
        if (el.getAttribute('role') === 'combobox') return 'combobox';
        return (el.type || 'text').toLowerCase();
    }
    function fieldValue(el, members) {
        if (el.type === 'checkbox') return el.checked ? 'Yes' : '';
        if (el.type === 'radio') return members.find(x => x.checked)?.value || '';
        if (el.type === 'file') return String(el.files?.length || '');
        return el.value || '';
    }
    function metadata(el, members, id) {
        members.forEach(x => {x.dataset.applyosField = id;});
        const form = el.form || el.closest('form');
        let question = label(el);
        if (el.type === 'radio') question = text(el.closest('fieldset')?.querySelector('legend')) || question;
        return {id, selector:`[data-applyos-field="${id}"]`, question, type:fieldKind(el),
            required:members.some(x => x.required || x.getAttribute('aria-required') === 'true') || label(el).includes('*'),
            options:optionsFor(el, members), multiple:!!el.multiple, action:form?.action || location.href,
            signature:[el.tagName, el.type, el.name, label(el)].join(':'),
            invalid:el.getAttribute('aria-invalid') === 'true' || (!!el.willValidate && !el.validity.valid),
            value:fieldValue(el, members)};
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
        return [...document.querySelectorAll('button, input[type="submit"], a, [role="button"]')]
            .filter(el => visible(el) && !el.disabled && !el.closest('nav, header, footer'))
            .map((el, i) => {
                el.dataset.applyosButton = String(i);
                return {id:String(i), text:text(el) || el.value || el.getAttribute('aria-label') || '',
                    href:el.getAttribute('href') || '', formAction:el.formAction || el.form?.action || location.href};
            });
    }
    function confirmed() {
        return [...document.querySelectorAll('h1,h2,h3,[role="status"],[role="alert"],p')].filter(visible).some(el => {
            if (el.closest('article, [class*="description"], [class*="recommend"]')) return false;
            const value = text(el);
            return value.length < 400 && /^(?:thank you for (?:applying|your application)|your application (?:has been |was )?(?:successfully )?(?:submitted|received)|application (?:successfully )?(?:submitted|received))[.!\s]/i.test(value + ' ');
        });
    }
    const body = document.body?.innerText || '';
    const blocked = [...document.querySelectorAll('input[type="password"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"], [data-sitekey]')].some(visible) || /verify (?:you are|you're) human|access denied|sign in to apply|create an account to apply/i.test(body);
    const agreement = /by (?:clicking|submitting|continuing)[^.!\n]{0,180}\b(?:agree|accept|consent)\b/i.test(body);
    return {fields:collectFields(), buttons:collectButtons(), blocked, confirmation:confirmed(), agreement};
}
