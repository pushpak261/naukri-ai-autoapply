"""Explicit evidence only for browser fallbacks; unknown answers stay blank."""
import re


def evidence_answer(question, settings, candidate=None):
    text = str(question.get('question', '')).casefold()
    profile = settings.profile
    value = ''
    if 'email' in text:
        value = getattr(profile, 'email', '') or getattr(candidate, 'email', '')
    elif any(word in text for word in ('phone', 'mobile', 'contact number')):
        value = getattr(profile, 'phone', '') or getattr(candidate, 'phone', '')
    elif 'first name' in text:
        value = getattr(profile, 'first_name', '')
    elif 'last name' in text or 'surname' in text:
        value = getattr(profile, 'last_name', '')
    elif 'name' in text and not any(word in text for word in ('company', 'employer', 'school', 'college')):
        value = getattr(candidate, 'name', '') or ' '.join(filter(None, (getattr(profile, 'first_name', ''), getattr(profile, 'last_name', ''))))
    elif any(word in text for word in ('current location', 'current city', 'where do you live', 'where are you based')):
        value = profile.current_location
    elif any(word in text for word in ('expected salary', 'expected ctc')):
        value = profile.expected_ctc
    elif any(word in text for word in ('current salary', 'current ctc')):
        value = profile.current_ctc
    elif 'notice period' in text:
        value = profile.notice_period
    elif 'experience' in text and ('total' in text or 'overall' in text) and not re.search(r'\b(?:with|using|in)\s+\w+', text):
        value = profile.total_experience
    value = str(value or '').strip()
    if not value:
        return ''
    options = [str(option.get('text', '') if isinstance(option, dict) else option).strip() for option in question.get('options', [])]
    if options:
        return next((option for option in options if option.casefold() == value.casefold()), '')
    if question.get('type', question.get('field_type')) == 'number' and not re.fullmatch(r'\d+(?:\.\d+)?', value):
        return ''
    return value
