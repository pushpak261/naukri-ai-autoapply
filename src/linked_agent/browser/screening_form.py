"""Read and fill only the controls belonging to the active Easy Apply form."""

import asyncio
import re
from datetime import datetime

from playwright.async_api import TimeoutError as PlaywrightTimeoutError


FORM_SCOPE = r"""
const visible = el => !!el?.getClientRects().length && !el.closest('[inert], [hidden], [aria-hidden="true"]') && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).opacity !== '0';
const modal = [...document.querySelectorAll('dialog, [role="dialog"], .jobs-easy-apply-modal')].filter(visible).at(-1);
const customInvalid = el => (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean).some(id => {
    const hint = document.getElementById(id);
    return hint && visible(hint) && /invalid input|enter a valid (?:answer|number)|enter (?:a )?(?:whole|decimal) number/i.test(hint.innerText || '');
}) || el.getAttribute('aria-invalid') === 'true';
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
const labelText = el => {
    if (!el) return '';
    const copy = el.cloneNode(true);
    for (const child of copy.querySelectorAll('input, select, textarea, button, script, style, [role="listbox"]')) child.remove();
    return text(copy);
};
const ownLabel = el => [...(el.labels || [])].map(labelText).join(' ') || (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => labelText(document.getElementById(id))).filter(Boolean).join(' ') || labelText(el.closest('label')) || el.getAttribute('aria-label') || '';
const groupOf = el => el.closest('[componentkey^="easyApplyFieldFocus_"]') || el.closest('fieldset, [role="radiogroup"], .fb-dash-form-element, .jobs-easy-apply-form-section__grouping') || el.parentElement;
const optionText = (el, question) => {
    const candidates = [ownLabel(el), el.getAttribute('aria-label'), text(el), el.value];
    const option = candidates.find(value => value && value.trim() !== question.trim() && value !== 'on') || '';
    return /^true$/i.test(option) ? 'Yes' : /^false$/i.test(option) ? 'No' : option;
};
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
        options = members.map(el => ({text: optionText(el, label), value: el.value || optionText(el, label), selector: path(el), checked: el.checked || el.getAttribute('aria-checked') === 'true'}));
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
        validation_error: customInvalid(input),
        max_length: input.maxLength > 0 ? input.maxLength : null,
        min_length: input.minLength > 0 ? input.minLength : null,
        is_required: members.some(el => el.required || el.getAttribute('aria-required') === 'true') || group.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label)});
}
return result;
}"""
)


async def extract(page):
    return await page.evaluate(EXTRACT)


async def wait_until_ready(page, timeout_ms: int = 30000):
    """A dialog heading and spinner do not mean the application body has loaded."""
    script = (
        "() => {"
        + FORM_SCOPE
        + r"""
if (!modal || modal.getAttribute('aria-busy') === 'true' || [...modal.querySelectorAll('[aria-busy="true"]')].some(visible)) return false;
const fields = [...modal.querySelectorAll('input, select, textarea, [role="radio"], [role="checkbox"]')];
if (fields.some(el => visible(el) && el.type !== 'hidden' && !['button', 'submit', 'reset'].includes(el.type))) return true;
const actions = [...modal.querySelectorAll('button')];
if (actions.some(el => visible(el) && !el.disabled && /^(?:next(?: step)?|continue|review(?: application)?|submit(?: application)?)$/i.test((el.innerText || el.getAttribute('aria-label') || '').trim()))) return true;
return /application (?:sent|submitted)|successfully applied|thank you for applying/i.test(modal.innerText || '');
}"""
    )
    try:
        await page.wait_for_function(script, timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


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


async def _typeahead_matches(page, locator, answer):
    controls = await locator.get_attribute("aria-controls") or await locator.get_attribute(
        "aria-owns"
    )
    matches = []
    wanted = normalized(answer)
    for option in await page.locator('[role="option"]').all():
        if controls and not await option.evaluate(
            '(el, ids) => ids.includes(el.closest("[role=listbox]")?.id)', controls.split()
        ):
            continue
        label = normalized(await option.inner_text())
        label = re.sub(r"^" + re.escape(wanted) + r"\s+city(?=,|$)", wanted, label)
        if await option.is_visible() and (label == wanted or label.startswith(wanted + ",")):
            matches.append((label, option))
    return matches


async def _fill_typeahead(page, locator, answer):
    await locator.fill(str(answer))
    for _ in range(8):
        matches = await _typeahead_matches(page, locator, answer)
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


def _numeric_equivalent(field, answer):
    """Change representation only after the platform rejects a known scalar value."""
    from libs.common.screening import format_evidence

    question = field.get("question", "")
    if re.search(r"date of birth|\bdob\b", question, re.I):
        try:
            date = datetime.strptime(str(answer), "%d/%m/%Y")
        except ValueError:
            return ""
        return date.strftime("%d%m%Y")
    if re.search(r"\bctc\b|salary|compensation|notice period|experience", question, re.I):
        return format_evidence(answer, {**field, "type": "number", "field_type": "number"})
    return ""


async def _text_accepted(locator, answer):
    return await locator.input_value() == str(answer) and await locator.evaluate(
        r"""el => el.checkValidity() && el.getAttribute('aria-invalid') !== 'true' && !(el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean).some(id => {
            const hint = document.getElementById(id);
            return hint && hint.getClientRects().length && /invalid input|enter a valid (?:answer|number)|enter (?:a )?(?:whole|decimal) number/i.test(hint.innerText || '');
        })"""
    )


async def _fill_text(page, locator, answer, field):
    if (
        await locator.get_attribute("role") == "combobox"
        or await locator.get_attribute("aria-autocomplete") == "list"
    ):
        return await _fill_typeahead(page, locator, answer)
    await locator.fill(str(answer))
    if not await locator.count():
        return True
    await locator.evaluate("el => el.blur()")
    await asyncio.sleep(0.1)
    if await _text_accepted(locator, answer):
        return True
    equivalent = _numeric_equivalent(field, answer)
    if not equivalent or equivalent == str(answer):
        return False
    await locator.fill(equivalent)
    await locator.evaluate("el => el.blur()")
    await asyncio.sleep(0.1)
    return await _text_accepted(locator, equivalent)


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
    return field["field_type"] == "text" and await _fill_text(page, locator, answer, field)


async def action(page, kind):
    """Click one explicit, enabled step action only after native validation."""
    return await page.evaluate(
        r"""kind => {
    """
        + FORM_SCOPE
        + r"""
    if (!modal) return false;
    const fields = [...modal.querySelectorAll('input, select, textarea')];
    if (fields.some(el => visible(el) && !el.disabled && ((el.willValidate && !el.checkValidity()) || customInvalid(el)))) return false;
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


async def validation_state(page):
    """Only labels and validation flags; never include candidate answer values."""
    return await page.evaluate(
        "() => {"
        + FORM_SCOPE
        + r"""
if (!modal) return {modal: false};
const fields = [...modal.querySelectorAll('input, select, textarea')].filter(visible);
return {invalid: fields.filter(el => (el.willValidate && !el.validity.valid) || customInvalid(el)).map(el => ({
    question: el.getAttribute('aria-label') || [...(el.labels || [])].map(x=>x.textContent).join(' ') || el.name || el.type,
    nativeValid: el.validity.valid, ariaInvalid: el.getAttribute('aria-invalid'), customInvalid: customInvalid(el)
})), markers: [...modal.querySelectorAll('[aria-invalid="true"]')].filter(visible).map(el => ({tag: el.tagName, id: el.id})),
buttons: [...modal.querySelectorAll('button')].filter(visible).map(el => ({text: el.innerText || el.getAttribute('aria-label'), disabled: el.disabled}))};
}"""
    )
