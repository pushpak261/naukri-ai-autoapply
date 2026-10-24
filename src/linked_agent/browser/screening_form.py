"""Read and fill only the controls belonging to the active Easy Apply form."""

import asyncio
import re


FORM_SCOPE = r"""
const visible = el => !!el?.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
const modal = [...document.querySelectorAll('dialog, [role="dialog"], .jobs-easy-apply-modal')].filter(visible).at(-1);
"""

EXTRACT = (
    r"""() => {
"""
    + FORM_SCOPE
    + r"""
if (!modal) return [];
const controls = [...modal.querySelectorAll('input, select, textarea, [role="radio"], [role="checkbox"]')];
const path = el => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const parts = [];
    for (let node = el; node && node !== document.body; node = node.parentElement) {
        const siblings = [...node.parentElement.children].filter(s => s.tagName === node.tagName);
        parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')');
    }
    return 'body > ' + parts.join(' > ');
};
const text = el => (el?.innerText || el?.textContent || '').trim().replace(/\s+/g, ' ');
const ownLabel = el => [...(el.labels || [])].map(text).join(' ') || text(el.closest('label')) || el.getAttribute('aria-label') || '';
const groupOf = el => el.closest('fieldset, [role="radiogroup"], .fb-dash-form-element, .jobs-easy-apply-form-section__grouping, [componentkey^="easyApplyFieldFocus_"]') || el.parentElement;
const optionText = el => ownLabel(el) || text(el) || el.value || '';
const seen = new Set(), result = [];
for (const input of controls) {
    if (seen.has(input) || input.disabled || input.type === 'hidden' || ['button', 'submit', 'reset'].includes(input.type)) continue;
    const group = groupOf(input);
    if (!(visible(input) || (['radio', 'checkbox', 'file'].includes(input.type) && visible(group)))) continue;
    const type = input.type || input.getAttribute('role');
    const choice = ['radio', 'checkbox'].includes(type);
    const members = choice ? controls.filter(el => (el.type || el.getAttribute('role')) === type && !el.disabled &&
        (input.name ? el.name === input.name : groupOf(el) === group)) : [input];
    members.forEach(el => seen.add(el));
    let label = ownLabel(input);
    if (choice) {
        const heading = group.querySelector('legend, [data-test-form-element-label], .fb-dash-form-element__label, :scope > p');
        const firstLabel = [...group.querySelectorAll('label, .t-14')].find(el => !el.querySelector('input') && !el.htmlFor);
        label = text(heading) || text(firstLabel) || (members.length === 1 ? label : '');
    } else if (!label) {
        label = text(group.querySelector('legend, label, .fb-dash-form-element__label, .t-14, :scope > p'));
    }
    label ||= input.placeholder || input.name || (type === 'file' ? 'Resume upload' : 'Unlabelled required field');
    if (/^(de)?select resume|^remove resume|^follow /i.test(label)) continue;
    const fieldType = choice ? type : type === 'file' ? 'file' : input.tagName === 'SELECT' ? 'dropdown' : 'text';
    let value = input.value || '';
    let options = [];
    if (choice) {
        options = members.map(el => ({text: optionText(el), value: el.value || optionText(el), selector: path(el), checked: el.checked || el.getAttribute('aria-checked') === 'true'}));
        value = options.filter(o => o.checked).map(o => o.value).join(', ');
    } else if (input.tagName === 'SELECT') {
        options = [...input.options].filter(o => !o.disabled && !/^(select|choose|please select)( |$)/i.test(text(o))).map(o => ({text: text(o), value: o.value}));
        const selected = input.selectedOptions[0];
        value = selected && options.some(o => o.value === selected.value) ? text(selected) : '';
    } else if (type === 'file') {
        value = input.files?.[0]?.name || '';
    }
    result.push({question: label, field_type: fieldType, input_type: type || 'text', input_id: input.id || '', selector: path(input),
        group_selector: path(group), options: options.map(o => o.text), option_controls: options, current_value: value,
        is_required: members.some(el => el.required || el.getAttribute('aria-required') === 'true') || group.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label)});
}
return result;
}"""
)


async def extract(page):
    return await page.evaluate(EXTRACT)


def normalized(value):
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def matching_option(answer, options):
    """Only accept an unambiguous label or value; never guess by word overlap."""
    target = normalized(answer)
    matches = [o for o in options if target in (normalized(o["text"]), normalized(o["value"]))]
    if not matches:
        matches = [o for o in options if normalized(o["text"]).startswith(target + " (")]
    return matches[0] if target and len(matches) == 1 else None


async def _choice_label(page, locator):
    identifier = await locator.get_attribute("id")
    if identifier:
        for candidate in await page.locator("label[for]").all():
            if await candidate.get_attribute("for") == identifier:
                return candidate
    return page.locator("label").filter(has=locator)


async def _set_native_choice(page, locator, checked):
    if await locator.is_checked() != checked:
        if await locator.is_visible():
            await locator.set_checked(checked)
        else:
            label = await _choice_label(page, locator)
            if await label.count() != 1 or not await label.is_visible():
                return False
            await label.click()
    return not await locator.count() or await locator.is_checked() == checked


async def _set_choice(page, option, checked):
    locator = page.locator(option["selector"])
    if await locator.evaluate("el => el.tagName === 'INPUT'"):
        return await _set_native_choice(page, locator, checked)
    current = await locator.get_attribute("aria-checked") == "true"
    if current != checked:
        await locator.click()
    if not await locator.count():
        return True
    return await locator.get_attribute("aria-checked") == str(checked).lower()


async def _fill_choices(page, field, answer):
    options = field["option_controls"]
    if field["field_type"] == "radio":
        selected = matching_option(answer, options)
        return bool(selected) and await _set_choice(page, selected, True)
    if len(options) == 1 and normalized(answer) in ("yes", "true", "no", "false"):
        return await _set_choice(page, options[0], normalized(answer) in ("yes", "true"))
    answers = [part.strip() for part in re.split(r"[,;|\n]", str(answer)) if part.strip()]
    selected = [matching_option(part, options) for part in answers]
    if not selected or any(option is None for option in selected):
        return False
    wanted = {option["selector"] for option in selected}
    for option in options:
        if not await _set_choice(page, option, option["selector"] in wanted):
            return False
    return True


async def _fill_typeahead(page, locator, answer):
    await locator.fill(str(answer))
    for _ in range(8):
        controls = await locator.get_attribute("aria-controls") or await locator.get_attribute(
            "aria-owns"
        )
        candidates = page.locator('[role="option"]')
        matches = []
        for option in await candidates.all():
            if controls and not await option.evaluate(
                '(el, ids) => ids.includes(el.closest("[role=listbox]")?.id)', controls.split()
            ):
                continue
            label = normalized(await option.inner_text())
            label = re.sub(
                r"^" + re.escape(normalized(answer)) + r"\s+city(?=,|$)", normalized(answer), label
            )
            if await option.is_visible() and (
                label == normalized(answer) or label.startswith(normalized(answer) + ",")
            ):
                matches.append((label, option))
        if matches and len({label for label, _ in matches}) == 1:
            await matches[0][1].click()
            return True
        await asyncio.sleep(0.25)
    return False


async def _current_field(page, question):
    fields = await extract(page)
    matches = [
        f
        for f in fields
        if normalized(f["question"]) == normalized(question.get("question", ""))
        and f["field_type"] == question.get("field_type", "text")
        and (not question.get("selector") or f["selector"] == question["selector"])
    ]
    return matches[0] if len(matches) == 1 else None


async def _fill_text(page, locator, answer):
    if (
        await locator.get_attribute("role") == "combobox"
        or await locator.get_attribute("aria-autocomplete") == "list"
    ):
        return await _fill_typeahead(page, locator, answer)
    await locator.fill(str(answer))
    if not await locator.count():
        return True
    await locator.dispatch_event("blur")
    return await locator.input_value() == str(answer) and await locator.evaluate(
        "el => el.checkValidity()"
    )


async def fill(page, question, answer):
    field = await _current_field(page, question)
    if not field or not str(answer).strip():
        return False
    locator = page.locator(field["selector"])
    if field["field_type"] in ("radio", "checkbox"):
        return await _fill_choices(page, field, answer)
    if field["field_type"] == "dropdown":
        option = matching_option(answer, field["option_controls"])
        if not option:
            return False
        await locator.select_option(value=option["value"])
        return await locator.input_value() == option["value"]
    return field["field_type"] == "text" and await _fill_text(page, locator, answer)


async def action(page, kind):
    """Click one explicit, enabled step action only after native validation."""
    return await page.evaluate(
        r"""kind => {
    """
        + FORM_SCOPE
        + r"""
    if (!modal) return false;
    const fields = [...modal.querySelectorAll('input, select, textarea')];
    if (fields.some(el => visible(el) && !el.disabled && el.willValidate && !el.checkValidity())) return false;
    if ([...modal.querySelectorAll('[aria-invalid="true"]')].some(visible)) return false;
    const patterns = {next: /^(next|continue)(\b|$)/i, review: /^review(\b|$)/i, submit: /^(submit|send application)(\b|$)/i};
    const button = [...modal.querySelectorAll('button')].find(b => visible(b) && !b.disabled &&
        !b.closest('[aria-disabled="true"]') && patterns[kind].test((b.innerText || b.getAttribute('aria-label') || '').trim()));
    if (!button) return false;
    button.click();
    return true;
    }""",
        kind,
    )
