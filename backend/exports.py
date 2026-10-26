"""Bounded-memory CSV export. Data rows are read one interview at a time."""
import csv
import io
import json
import math
import re
import hashlib
import hmac
import secrets
import statistics
from datetime import datetime, timezone

from .db import connect, encode, is_postgres, new_id, now
from .model import questions, require, uid, validate_value, STATES


def safe_cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (dict, list)):
        value = encode(value)
    value = str(value)
    # Check after whitespace/control characters as spreadsheet applications may ignore them.
    if re.sub(r'^[\s\x00-\x1f\ufeff]*', '', value).startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def csv_line(values, delimiter=','):
    buffer = io.StringIO(newline='')
    csv.writer(buffer, delimiter=delimiter, lineterminator='\r\n').writerow([safe_cell(v) for v in values])
    return buffer.getvalue().encode('utf-8')


class Export:
    def __init__(self, service, actor, options):
        self.service, self.actor, self.options = service, actor, options
        self.project = options.get('project_id')
        self.format = options.get('format', 'wide')
        require(self.format in ('wide', 'long', 'raw', 'analysis'), 'Unknown CSV format')
        self.delimiter = options.get('delimiter', ',')
        require(self.delimiter in (',', ';', '\t'), 'Delimiter must be comma, semicolon, or tab')
        self.exported_at = now()
        self.audit_id = new_id()
        self.anonymize = options.get('anonymize') is True
        self.pseudonym_key = secrets.token_bytes(32)
        with connect(service.path) as c:
            access = service.access(c, actor, self.project)
            self.identifiable = options.get('include_identifiers') is True
            require(not (self.anonymize and self.identifiable), 'De-identified exports cannot include protected identifiers')
            require(not self.identifiable or access['identifiable'], 'Identifiable export permission required', 403)
            self.project_name = access['project']['name']
            self.where = ['i.project_id=?']
            self.args = [self.project]
            if access['role'] == 'researcher':
                self.where.append('i.researcher_id=?')
                self.args.append(actor['id'])
            for key, column in [('form_ids', 'v.form_id'), ('version_ids', 'i.version_id')]:
                values = options.get(key, [])
                require(isinstance(values, list) and len(values) <= 500, f'Invalid {key}')
                if values:
                    self.where.append(column + ' IN (' + ','.join('?' for _ in values) + ')')
                    self.args.extend(values)
            for key, column in [('location', 'i.location'), ('researcher_id', 'i.researcher_id'), ('status', 'i.status'), ('source', 'i.source')]:
                if options.get(key):
                    if key == 'status':
                        require(options[key] in ('draft', 'completed'), 'Invalid status')
                    if key == 'source':
                        require(options[key] in ('researcher', 'public_link'), 'Invalid collection source')
                    self.where.append(column + '=?')
                    self.args.append(options[key])
            for key, op in [('from', '>='), ('to', '<=')]:
                if options.get(key):
                    try:
                        stamp = datetime.fromisoformat(options[key].replace('Z', '+00:00'))
                        require(stamp.tzinfo is not None, 'Date filters require a timezone')
                        normalized = stamp.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                    except (ValueError, TypeError):
                        require(False, 'Invalid ISO 8601 date filter')
                    self.where.append('i.created_at' + op + '?')
                    self.args.append(normalized)
            # Include selected definitions even when there are no matching interviews.
            versions = service.versions(actor, self.project)
            self.definitions = []
            selected = options.get('question_ids', [])
            require(isinstance(selected, list), 'question_ids must be a list')
            for v in versions:
                if options.get('version_ids') and v['id'] not in options['version_ids']:
                    continue
                if options.get('form_ids') and v['form_id'] not in options['form_ids']:
                    continue
                for q in questions(v['schema']):
                    protected = q.get('sensitive') or q['type'] in ('location', 'media')
                    if protected and not self.identifiable:
                        continue
                    if selected and q['id'] not in selected:
                        continue
                    self.definitions.append((v, q))
            # Version-qualified columns make changed labels and choice codes unambiguous.
            metadata = ['project_id', 'interview_id', 'version_id', 'status', 'location', 'created_at', 'updated_at', 'exported_at', 'correction_id', 'source']
            selected_metadata = options.get('metadata_fields', metadata)
            require(isinstance(selected_metadata, list) and set(selected_metadata) <= set(metadata), 'Unknown metadata field')
            mandatory = {'project_id', 'interview_id', 'version_id', 'exported_at', 'source'}
            excluded = {'location', 'created_at', 'updated_at', 'correction_id'} if self.anonymize else set()
            self.metadata_indices = [index for index, field in enumerate(metadata) if (field in mandatory or field in selected_metadata) and field not in excluded]
            self.columns = [metadata[index] for index in self.metadata_indices]
            if self.identifiable:
                self.columns += ['respondent_id', 'researcher_id']
            self.metadata_count = len(self.columns)
            if self.format in ('long', 'raw'):
                self.columns += ['question_id', 'question_label', 'data_type', 'answer_state', 'answer_value']
            else:
                for v, q in self.definitions:
                    prefix = self.prefix(v, q)
                    self.columns.append(prefix + '__state')
                    if q['type'] == 'multiple':
                        self.columns += [prefix + '__' + ch['code'] for ch in q['choices']]
                    else:
                        self.columns.append(prefix)
            filters = options.get('answer_filters', [])
            require(isinstance(filters, list) and len(filters) <= 20, 'Use up to 20 answer filters')
            allowed = {q['id']: q for v in versions for q in questions(v['schema']) if self.identifiable or not (q.get('sensitive') or q['type'] in ('location', 'media'))}
            source = 'i.answers' if options.get('original') else 'COALESCE((SELECT answers FROM corrections WHERE interview_id=i.id ORDER BY rowid DESC LIMIT 1),i.answers)'
            for rule in filters:
                qid = uid(rule.get('question_id'))
                require(qid in allowed, 'Unknown or protected filter question', 403)
                op, value = rule.get('op'), rule.get('value')
                require(op in ('equals', 'contains', 'gt', 'lt', 'state'), 'Unsupported answer filter')
                path = '$."' + qid + '".'
                if is_postgres(service.path):
                    state = f'({source})::jsonb #>> ?::text[]'
                    if op == 'state':
                        require(value in STATES, 'Unknown answer state')
                        self.where.append(f"COALESCE({state}, 'missing')=?")
                        self.args.extend([[qid, 'state'], value])
                        continue
                    require(type(value) in (str, int, float, bool), 'Filter value must be scalar')
                    if op in ('gt', 'lt'):
                        require(allowed[qid]['type'] in ('number', 'currency', 'rating'), 'Numeric comparison requires a numeric question')
                        require(type(value) in (int, float) and math.isfinite(value), 'Numeric filter requires a finite number')
                    self.where.append(f'({state})=?')
                    self.args.extend([[qid, 'state'], 'answered'])
                    extracted = f'({source})::jsonb #> ?::text[]'
                    if op == 'contains':
                        require(allowed[qid]['type'] == 'multiple', 'Contains requires a multiple-choice question')
                        self.where.append(f"EXISTS(SELECT 1 FROM jsonb_array_elements(COALESCE({extracted}, '[]'::jsonb)) AS choices(value) WHERE value=?::jsonb)")
                    else:
                        operator = {'equals': '=', 'gt': '>', 'lt': '<'}[op]
                        self.where.append(f'({extracted}){operator}?::jsonb')
                    self.args.extend([[qid, 'value'], encode(value)])
                    continue
                if op == 'state':
                    require(value in STATES, 'Unknown answer state')
                    self.where.append(f"COALESCE(json_extract({source},?), 'missing')=?")
                    self.args.extend([path + 'state', value])
                    continue
                require(type(value) in (str, int, float, bool), 'Filter value must be scalar')
                if op in ('gt', 'lt'):
                    require(allowed[qid]['type'] in ('number', 'currency', 'rating'), 'Numeric comparison requires a numeric question')
                    require(type(value) in (int, float) and math.isfinite(value), 'Numeric filter requires a finite number')
                self.where.append(f'json_extract({source},?)=?')
                self.args.extend([path + 'state', 'answered'])
                if op == 'contains':
                    require(allowed[qid]['type'] == 'multiple', 'Contains requires a multiple-choice question')
                    self.where.append(f'EXISTS(SELECT 1 FROM json_each(json_extract({source},?)) WHERE value=?)')
                else:
                    operator = {'equals': '=', 'gt': '>', 'lt': '<'}[op]
                    self.where.append(f'json_extract({source},?){operator}?')
                self.args.extend([path + 'value', value])
            self.sql = ' FROM interviews i JOIN versions v ON v.id=i.version_id WHERE ' + ' AND '.join(self.where)
            self.count = c.execute('SELECT COUNT(*)' + self.sql, self.args).fetchone()[0]

    @staticmethod
    def prefix(version, question):
        return 'v_' + version['id'] + '__q_' + question['id']

    def preview(self):
        return {'columns': self.columns, 'record_count': self.count, 'exported_at': self.exported_at,
                'formula_protection': 'Dangerous text is prefixed with an apostrophe; raw answer JSON preserves original values.',
                'missing_encoding': 'A separate __state column distinguishes missing, skipped, not_sure, prefer_not_to_answer, and not_applicable_version.',
                'multiple_choice_encoding': 'One 0/1 column per stable choice code; empty for non-answered states.'}

    def dictionary(self):
        yield csv_line(['column', 'version_id', 'question_id', 'label', 'type', 'choice_code', 'choice_label', 'encoding'], self.delimiter)
        for column in self.columns[:self.metadata_count]:
            yield csv_line([column, '', '', column, 'metadata', '', '', 'ISO 8601 UTC for timestamps; identifiers are UUIDs'], self.delimiter)
        for v, q in self.definitions:
            prefix = self.prefix(v, q)
            yield csv_line([prefix, v['id'], q['id'], q['label'], q['type'], '', '', 'Stable coded values; non-answered values empty; see state'], self.delimiter)
            yield csv_line([prefix + '__state', v['id'], q['id'], q['label'], 'state', '', '', 'answered|missing|skipped|not_sure|prefer_not_to_answer|not_applicable_version'], self.delimiter)
            for choice in q.get('choices', []):
                yield csv_line([prefix + ('__' + choice['code'] if q['type'] == 'multiple' else ''), v['id'], q['id'], q['label'], q['type'], choice['code'], choice['label'], '0/1 indicator' if q['type'] == 'multiple' else 'choice code'], self.delimiter)

    def stream(self):
        # Snapshot keeps record counts and values consistent while other requests write.
        c = connect(self.service.path)
        count = 0
        csv_rows = 0
        finished = False
        with connect(self.service.path) as audit:
            audit_options = {**self.options, 'resolved_version_ids': list(dict.fromkeys(v['id'] for v, _ in self.definitions)), 'columns': self.columns, 'data_types': {q['id']: q['type'] for _, q in self.definitions}}
            audit.execute('INSERT INTO export_audits VALUES(?,?,?,?,?,?,?)', (self.audit_id, self.project, self.actor['id'], encode(audit_options), self.count, self.exported_at, 'started'))
        try:
            c.execute('BEGIN')
            snapshot_count = c.execute('SELECT COUNT(*)' + self.sql, self.args).fetchone()[0]
            self.count = snapshot_count
            # The manifest header is generated from the same snapshot as rows.
            yield csv_line(['export_record_count', snapshot_count, 'exported_at', self.exported_at, 'format', self.format], self.delimiter) if self.options.get('manifest_row') else b''
            yield csv_line(self.columns, self.delimiter)
            definitions = {}
            for v, q in self.definitions:
                definitions.setdefault(v['id'], []).append(q)
            query = 'SELECT i.*' + self.sql + ' ORDER BY i.id'
            rows = c.iterate(query, self.args) if is_postgres(self.service.path) else c.execute(query, self.args)
            for row in rows:
                latest = c.execute('SELECT * FROM corrections WHERE interview_id=? ORDER BY rowid DESC LIMIT 1', (row['id'],)).fetchone()
                answers = json.loads(latest['answers'] if latest and not self.options.get('original') else row['answers'])
                applied = latest if not self.options.get('original') else None
                iid = hmac.new(self.pseudonym_key, row['id'].encode(), hashlib.sha256).hexdigest() if self.anonymize else row['id']
                base = [row['project_id'], iid, row['version_id'], row['status'], row['location'], row['created_at'], applied['created_at'] if applied else row['updated_at'], self.exported_at, applied['id'] if applied else '', row['source']]
                base = [base[index] for index in self.metadata_indices]
                if self.identifiable:
                    base += [row['respondent_id'], row['researcher_id']]
                if self.format in ('long', 'raw'):
                    for q in definitions.get(row['version_id'], []):
                        a = answers.get(q['id'], {'state': 'missing'})
                        value = a.get('value')
                        # Raw always uses JSON: strings, booleans, numbers, arrays and objects retain type.
                        if self.format == 'raw':
                            value = encode(a)
                        csv_rows += 1
                        yield csv_line(base + [q['id'], q['label'], q['type'], a['state'], value], self.delimiter)
                else:
                    values = list(base)
                    for v, q in self.definitions:
                        a = answers.get(q['id'], {'state': 'missing'}) if v['id'] == row['version_id'] else {'state': 'not_applicable_version'}
                        values.append(a['state'])
                        if q['type'] == 'multiple':
                            values.extend([int(ch['code'] in a['value']) if a['state'] == 'answered' else '' for ch in q['choices']])
                        else:
                            values.append(a.get('value', ''))
                    csv_rows += 1
                    yield csv_line(values, self.delimiter)
                count += 1
            finished = True
        finally:
            c.close()
            with connect(self.service.path) as audit:
                audit_options['csv_row_count'] = csv_rows
                audit.execute('UPDATE export_audits SET record_count=?,state=?,options=? WHERE id=?', (count, 'completed' if finished else 'interrupted', encode(audit_options), self.audit_id))


def histogram(values, bins=8):
    """Compact numeric distribution for charts; exact min/max are preserved."""
    low, high = min(values), max(values)
    if low == high:
        return [{'from': low, 'to': high, 'label': f'{low:g}', 'count': len(values)}]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - low) / width), bins - 1)
        counts[index] += 1
    return [{'from': low + index * width, 'to': low + (index + 1) * width,
             'label': f'{low + index * width:g}–{low + (index + 1) * width:g}', 'count': count}
            for index, count in enumerate(counts)]


def analytics(service, actor, project, options):
    """Accumulate per-question statistics and chart-ready distributions."""
    export = Export(service, actor, {**options, 'project_id': project})
    groups = {}
    defs = {}
    for v, q in export.definitions:
        defs.setdefault(v['id'], []).append(q)
    numeric_types = ('number', 'currency', 'rating')
    categorical_types = ('single', 'multiple', 'boolean')
    with connect(service.path) as c:
        c.execute('BEGIN')
        for row in c.execute('SELECT i.*' + export.sql, export.args):
            latest = c.execute('SELECT answers FROM corrections WHERE interview_id=? ORDER BY rowid DESC LIMIT 1', (row['id'],)).fetchone()
            answers = json.loads(latest['answers'] if latest else row['answers'])
            for q in defs.get(row['version_id'], []):
                group = row['location'] if options.get('group_by_location') else 'all'
                key = (row['version_id'], q['id'], group)
                item = groups.setdefault(key, {'version_id': row['version_id'], 'question_id': q['id'], 'label': q['label'], 'type': q['type'], 'group': group, 'total': 0, 'answered': 0, 'states': {}, 'categories': {}, 'sum': 0, 'min': None, 'max': None, 'values': []})
                a = answers.get(q['id'], {'state': 'missing'})
                item['total'] += 1
                item['states'][a['state']] = item['states'].get(a['state'], 0) + 1
                if a['state'] != 'answered':
                    continue
                item['answered'] += 1
                value = a['value']
                if q['type'] in numeric_types:
                    item['sum'] += value
                    item['values'].append(value)
                    item['min'] = value if item['min'] is None else min(item['min'], value)
                    item['max'] = value if item['max'] is None else max(item['max'], value)
                if q['type'] in categorical_types:
                    for code in value if q['type'] == 'multiple' else [str(value).lower()]:
                        item['categories'][code] = item['categories'].get(code, 0) + 1
    for item in groups.values():
        values = item.pop('values')
        numeric = item['type'] in numeric_types and bool(values)
        item['mean'] = (sum(values) / len(values)) if numeric else None
        item['median'] = statistics.median(values) if numeric else None
        item['stdev'] = statistics.pstdev(values) if len(values) > 1 else (0.0 if numeric else None)
        item['histogram'] = histogram(values) if numeric else []
        if numeric:
            item['mode'] = statistics.mode(values)
        elif item['categories']:
            item['mode'] = max(item['categories'].items(), key=lambda pair: (pair[1], pair[0]))[0]
        else:
            item['mode'] = None
        item['percentages'] = {key: n / item['answered'] * 100 for key, n in item['categories'].items()} if item['answered'] else {}
    return list(groups.values())


def analytics_overview(service, actor, project, options):
    """Counts and a daily response timeline using the same authorized filter scope."""
    export = Export(service, actor, {**options, 'project_id': project})
    timeline, sources, statuses, versions = {}, {}, {}, {}
    total = 0
    with connect(service.path) as c:
        c.execute('BEGIN')
        for row in c.execute('SELECT i.*' + export.sql, export.args):
            total += 1
            day = (row['created_at'] or '')[:10]
            timeline[day] = timeline.get(day, 0) + 1
            sources[row['source']] = sources.get(row['source'], 0) + 1
            statuses[row['status']] = statuses.get(row['status'], 0) + 1
            versions[row['version_id']] = versions.get(row['version_id'], 0) + 1
    return {
        'total': total,
        'completed': statuses.get('completed', 0),
        'draft': statuses.get('draft', 0),
        'sources': sources,
        'versions': versions,
        'timeline': [{'date': day, 'count': timeline[day]} for day in sorted(timeline)],
    }
