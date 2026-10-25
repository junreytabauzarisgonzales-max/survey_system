"""Shared declarative schema and answer validation. No author-supplied code executes."""
import json
import math
import re
import uuid
from datetime import date, datetime, time

TYPES = {'text', 'single', 'multiple', 'number', 'currency', 'date', 'time', 'rating', 'boolean', 'location', 'media'}
STATES = {'answered', 'missing', 'skipped', 'not_sure', 'prefer_not_to_answer'}


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require(test, message, status=400):
    if not test:
        raise Problem(message, status)


def uid(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise Problem('A valid UUID is required')


def text(value, name, maximum=10000, empty=False):
    require(isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= maximum, f'Invalid {name}')
    return value


def questions(schema):
    return [q for section in schema.get('sections', []) for q in section['questions']]


def visible(q, answers):
    rule = q.get('condition')
    if not rule:
        return True
    a = answers.get(rule['question_id'], {'state': 'missing'})
    value = a.get('value') if a.get('state') == 'answered' else None
    op = rule['op']
    target = rule.get('value')
    return {'equals': lambda: value == target,
            'not_equals': lambda: value is not None and value != target,
            'contains': lambda: isinstance(value, list) and target in value,
            'answered': lambda: a.get('state') == 'answered'}[op]()


def validate_schema(schema):
    require(isinstance(schema, dict), 'Schema must be an object')
    require(schema.get('engine_version', 1) == 1, 'Unsupported schema engine version')
    sections = schema.get('sections')
    require(isinstance(sections, list) and 0 < len(sections) <= 100, 'Use 1–100 sections')
    seen = set()
    prior_questions = {}
    section_ids = set()
    for section in sections:
        sid = uid(section.get('id'))
        require(sid not in section_ids, 'Duplicate section ID')
        section_ids.add(sid)
        text(section.get('label'), 'section label', 500)
        require(isinstance(section.get('questions'), list), 'Questions must be a list')
        for q in section['questions']:
            qid = uid(q.get('id'))
            require(qid not in seen, 'Duplicate question ID')
            text(q.get('label'), 'question label', 1000)
            require(q.get('type') in TYPES, 'Unsupported question type')
            for flag in ('required', 'sensitive'):
                require(isinstance(q.get(flag, False), bool), f'{flag} must be boolean')
            for key in ('description', 'help'):
                text(q.get(key, ''), key, empty=True)
            rules = q.get('validation', {})
            require(isinstance(rules, dict) and set(rules) <= {'min', 'max', 'min_length', 'max_length', 'min_selections', 'max_selections'}, 'Unsupported validation rule')
            for key, value in rules.items():
                require(type(value) in (int, float) and math.isfinite(value), 'Validation bounds must be finite numbers')
                if key not in ('min', 'max'):
                    require(type(value) is int and value >= 0, 'Lengths and counts must be nonnegative integers')
            for low, high in [('min', 'max'), ('min_length', 'max_length'), ('min_selections', 'max_selections')]:
                require(low not in rules or high not in rules or rules[low] <= rules[high], 'Invalid validation range')
            if q['type'] in ('single', 'multiple'):
                choices = q.get('choices')
                require(isinstance(choices, list) and 0 < len(choices) <= 1000, 'Choices are required')
                codes = set()
                for choice in choices:
                    code = choice.get('code')
                    require(isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', code), 'Choice codes must be stable ASCII identifiers')
                    require(code not in codes, 'Duplicate choice code')
                    codes.add(code)
                    text(choice.get('label'), 'choice label', 500)
            rule = q.get('condition')
            if rule:
                require(isinstance(rule, dict) and rule.get('question_id') in seen, 'Conditions must reference an earlier question')
                require(rule.get('op') in ('equals', 'not_equals', 'contains', 'answered'), 'Unsupported conditional operator')
                require(type(rule.get('value')) in (str, int, float, bool, type(None)), 'Condition value must be scalar')
                source = prior_questions[rule['question_id']]
                if rule['op'] == 'contains':
                    require(source['type'] == 'multiple' and rule.get('value') in {c['code'] for c in source['choices']}, 'Contains must reference a valid multiple-choice code')
                elif rule['op'] != 'answered':
                    require(source['type'] not in ('multiple', 'media', 'location'), 'Use contains for multiple-choice conditions')
                    validate_value(source, rule.get('value'))
            seen.add(qid)
            prior_questions[qid] = q
            if 'default' in q:
                validate_value(q, q['default'])
    require(len(seen) <= 2000, 'Maximum 2000 questions per form')
    return schema


def validate_value(q, value):
    kind = q['type']
    rules = q.get('validation', {})
    if kind == 'text':
        text(value, q['label'], 100000, empty=True)
        require(len(value) >= rules.get('min_length', 0) and len(value) <= rules.get('max_length', 100000), f"Invalid length: {q['label']}")
    elif kind in ('number', 'currency', 'rating'):
        require(type(value) in (float, int) and math.isfinite(value), f"Numeric value required: {q['label']}")
        require(value >= rules.get('min', -float('inf')) and value <= rules.get('max', float('inf')), f"Out of range: {q['label']}")
    elif kind in ('single', 'multiple'):
        codes = {c['code'] for c in q['choices']}
        if kind == 'single':
            require(isinstance(value, str) and value in codes, 'Unknown choice code')
        else:
            require(isinstance(value, list) and all(isinstance(v, str) and v in codes for v in value), 'Unknown multiple-choice code')
            require(len(set(value)) == len(value), 'Duplicate choice')
            require(rules.get('min_selections', 0) <= len(value) <= rules.get('max_selections', 1000), 'Invalid selection count')
    elif kind == 'boolean':
        require(isinstance(value, bool), 'Boolean required')
    elif kind in ('date', 'time'):
        try:
            require(isinstance(value, str), 'ISO date/time required')
            (date if kind == 'date' else time).fromisoformat(value)
        except ValueError:
            raise Problem('ISO date/time required')
    elif kind == 'location':
        require(isinstance(value, dict) and set(value) == {'latitude', 'longitude'}, 'Coordinates required')
        require(all(type(v) in (int, float) and math.isfinite(v) for v in value.values()), 'Coordinates must be numeric')
        require(-90 <= value['latitude'] <= 90 and -180 <= value['longitude'] <= 180, 'Invalid coordinates')
    elif kind == 'media':
        require(isinstance(value, list) and len(value) <= 20, 'Attachment reference list required')
        for v in value:
            uid(v)


def validate_answers(schema, answers, complete=False, location_consent=False):
    require(isinstance(answers, dict), 'Answers must be an object')
    qs = questions(schema)
    require(set(answers) <= {q['id'] for q in qs}, 'Unknown question ID')
    effective = {}
    for q in qs:
        a = answers.get(q['id'], {'state': 'missing'})
        require(isinstance(a, dict) and set(a) <= {'state', 'value'} and a.get('state') in STATES, 'Invalid answer state')
        shown = visible(q, effective)
        if not shown:
            require(a['state'] in ('missing', 'skipped'), 'Hidden questions cannot have recorded values')
        if a['state'] == 'answered':
            validate_value(q, a.get('value'))
            require(q['type'] != 'location' or location_consent, 'Explicit location consent is required')
        else:
            require('value' not in a, 'Non-answered states must not carry a value')
        if complete and shown and q.get('required'):
            require(a['state'] in ('answered', 'not_sure', 'prefer_not_to_answer'), f"Required: {q['label']}")
            if a['state'] == 'answered' and q['type'] in ('text', 'multiple', 'media'):
                require(bool(a['value'].strip()) if q['type'] == 'text' else bool(a['value']), f"Required: {q['label']}")
        effective[q['id']] = a if shown else {'state': 'skipped'}
    return effective


def validate_config(config):
    require(isinstance(config, dict) and set(config) <= {'objectives', 'locations', 'categories', 'consent', 'fields', 'retention_days'}, 'Invalid project configuration keys')
    for key in ('objectives', 'consent'):
        text(config.get(key, ''), key, empty=True)
    for key in ('locations', 'categories'):
        values = config.get(key, [])
        require(isinstance(values, list) and len(values) <= 1000, f'Invalid {key}')
        codes = set()
        for item in values:
            code = text(item.get('id'), f'{key} ID', 80)
            require(code not in codes, 'Duplicate configuration ID')
            codes.add(code)
            text(item.get('label'), f'{key} label', 500)
    if config.get('fields'):
        validate_schema(config['fields'])
    require(type(config.get('retention_days', 3650)) is int and 1 <= config.get('retention_days', 3650) <= 36500, 'Retention must be 1–36500 days')
    return config
