// Only visible application controls are exposed to the planner, never scripts or credentials.
() => {
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const text = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
    const label = (el, legend = true) => {
        const explicit = [
            ...(el.labels ? [...el.labels].map(text) : []),
            el.getAttribute('aria-label'),
            ...(el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => text(document.getElementById(id))),
            legend ? el.closest('fieldset')?.querySelector('legend')?.textContent : ''
        ].filter(Boolean).join(' | ');
        return (explicit || el.getAttribute('placeholder') || el.name || '').slice(0, 500);
    };
    const fields = [], groups = new Set();
    for (const el of document.querySelectorAll('input, select, textarea, [role="combobox"]')) {
        if (el.disabled || el.readOnly || el.closest('nav, header, footer, [role="search"]')) continue;
        const type = (el.type || el.getAttribute('role') || 'text').toLowerCase();
        if (['hidden', 'submit', 'button', 'reset', 'search'].includes(type)) continue;
        if (!visible(el) && !(type === 'file' && el.labels && [...el.labels].some(visible))) continue;
        if (el.getAttribute('role') === 'combobox' && el.querySelector('input')) continue;
        const id = String(fields.length), selector = `[data-applyos-field="${id}"]`;
        let options = [], members = [el];
        if (type === 'radio') {
            const group = el.name ? [...document.querySelectorAll('input[type="radio"]')].filter(x => x.name === el.name && x.form === el.form && visible(x) && !x.disabled) : [el];
            if (groups.has(group[0])) continue;
            groups.add(group[0]); members = group;
            options = group.map(x => ({text: label(x, false), value: x.value}));
        } else if (el.tagName === 'SELECT') {
            options = [...el.options].filter(x => !x.disabled && x.value && !/^(select|choose)(\b|\s)/i.test(text(x))).map(x => ({text: text(x), value: x.value}));
        } else if (type === 'checkbox') {
            options = [{text: 'Yes', value: 'true'}, {text: 'No', value: 'false'}];
        }
        members.forEach(x => x.setAttribute('data-applyos-field', id));
        const form = el.form || el.closest('form');
        fields.push({id, selector, question: type === 'radio' ? (text(el.closest('fieldset')?.querySelector('legend')) || label(el)) : label(el),
            type: el.tagName === 'SELECT' ? 'dropdown' : el.getAttribute('role') === 'combobox' ? 'combobox' : type,
            required: members.some(x => x.required || x.getAttribute('aria-required') === 'true') || label(el).includes('*'),
            options, multiple: !!el.multiple, action: form?.action || location.href,
            signature: [el.tagName, type, el.name, label(el)].join(':'),
            invalid: el.getAttribute('aria-invalid') === 'true' || (!!el.willValidate && !el.validity.valid),
            value: type === 'checkbox' ? (el.checked ? 'Yes' : '') : type === 'radio' ? (members.find(x => x.checked)?.value || '') : type === 'file' ? String(el.files?.length || '') : (el.value || '')});
    }
    const buttons = [...document.querySelectorAll('button, input[type="submit"], a, [role="button"]')]
        .filter(el => visible(el) && !el.disabled && !el.closest('nav, header, footer'))
        .map((el, i) => {el.setAttribute('data-applyos-button', String(i)); return {id: String(i), text: text(el) || el.value || el.getAttribute('aria-label') || '', href: el.getAttribute('href') || '', formAction: el.formAction || el.form?.action || location.href};});
    const body = document.body?.innerText || '';
    const blocked = [...document.querySelectorAll('input[type="password"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"], [data-sitekey]')].some(visible) || /verify (?:you are|you're) human|access denied|sign in to apply|create an account to apply/i.test(body);
    const confirmation = [...document.querySelectorAll('h1,h2,h3,[role="status"],[role="alert"],p')].filter(visible).some(el => {
        if (el.closest('article, [class*="description"], [class*="recommend"]')) return false;
        const value = text(el);
        return value.length < 400 && /^(?:thank you for (?:applying|your application)|your application (?:has been |was )?(?:successfully )?(?:submitted|received)|application (?:successfully )?(?:submitted|received))[.!\s]/i.test(value + ' ');
    });
    const agreement = /by (?:clicking|submitting|continuing)[^.!\n]{0,180}\b(?:agree|accept|consent)\b/i.test(body);
    return {fields, buttons, blocked, confirmation, agreement};
}
