"""Restricted numeric priority conditions; never evaluate user-supplied code."""
import operator
import re

OPS = {'>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le, '==': operator.eq, '!=': operator.ne}
TERM = re.compile(r'^(match_score|posted_hours)\s*(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)?)$')


def parse_condition(condition):
    if not isinstance(condition, str):
        raise ValueError('Priority condition must be text')
    terms = [TERM.fullmatch(term.strip()) for term in condition.split(' AND ')]
    if not terms or any(term is None for term in terms):
        raise ValueError('Use numeric match_score/posted_hours comparisons joined by AND')
    return [term.groups() for term in terms]


def posted_hours(value):
    value = str(value or '').lower()
    if 'just now' in value or 'today' in value:
        return 0.0
    match = re.search(r'(\d+)\s*(hour|day|week|month)', value)
    if not match:
        return float('inf')
    return int(match[1]) * {'hour': 1, 'day': 24, 'week': 168, 'month': 720}[match[2]]


def priority(config, score, posted):
    values = {'match_score': score or 0, 'posted_hours': posted_hours(posted)}
    for rule in config.get('priority_rules', []):
        if (rule.get('enabled') and rule.get('action') == 'apply_immediately'
                and all(OPS[op](values[field], float(number)) for field, op, number in parse_condition(rule['condition']))):
            return 1
    return 0
