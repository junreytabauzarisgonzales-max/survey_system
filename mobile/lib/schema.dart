import 'dart:convert';

typedef Json = Map<String, dynamic>;
List<Json> questions(Json schema) => (schema['sections'] as List)
    .expand((s) => s['questions'] as List).map((q) => Map<String,dynamic>.from(q)).toList();

bool visible(Json q, Json answers) {
  final r = q['condition'];
  if (r == null) return true;
  final a = answers[r['question_id']] ?? {'state':'missing'};
  final v = a['state'] == 'answered' ? a['value'] : null;
  switch (r['op']) {
    case 'answered': return a['state'] == 'answered';
    case 'equals': return v == r['value'];
    case 'not_equals': return v != null && v != r['value'];
    case 'contains': return v is List && v.contains(r['value']);
    default: return false;
  }
}

Json normalize(Json schema, Json answers) {
  final result = <String,dynamic>{};
  for (final q in questions(schema)) {
    result[q['id']] = visible(q, result)
      ? (answers[q['id']] ?? {'state':'missing'}) : {'state':'skipped'};
  }
  return result;
}

Json defaults(Json schema) => normalize(schema,{for(final q in questions(schema)) if(q.containsKey('default')) q['id']:{'state':'answered','value':q['default']}});

String? validateAnswer(Json q, Json a) {
  if (a['state'] != 'answered') {
    return q['required'] == true && !['not_sure','prefer_not_to_answer'].contains(a['state']) ? 'This question is required.' : null;
  }
  final v = a['value'], r = q['validation'] ?? {};
  final type = q['type'];
  if(q['required']==true&&((type=='text'&&(v is! String||v.trim().isEmpty))||(['multiple','media'].contains(type)&&(v is! List||v.isEmpty))))return 'This question is required.';
  if (['number','currency','rating'].contains(type)) {
    if (v is! num || !v.isFinite) return 'Enter a valid number.';
    if ((r['min'] != null && v < r['min']) || (r['max'] != null && v > r['max'])) return 'Outside allowed range.';
  }
  if (type == 'text') {
    if(v is! String) return 'Text required.';
    if(v.runes.length < (r['min_length'] ?? 0) || v.runes.length > (r['max_length'] ?? 100000)) return 'Check text length.';
  }
  if(type == 'single' && !(q['choices'] as List).any((c) => c['code']==v)) return 'Select a choice.';
  if(type == 'multiple') {
    if(v is! List || v.any((code) => !(q['choices'] as List).any((c) => c['code']==code))) return 'Invalid choice.';
    if(v.length < (r['min_selections'] ?? 0) || v.length > (r['max_selections'] ?? 1000)) return 'Check selection count.';
  }
  if(type == 'boolean' && v is! bool) return 'Choose yes or no.';
  if(type == 'date' && (v is! String || DateTime.tryParse(v)==null)) return 'Enter an ISO date.';
  if(type == 'time' && (v is! String || !RegExp(r'^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$').hasMatch(v))) return 'Enter HH:mm.';
  if(type == 'location') {
    if(v is! Map || v['latitude'] is! num || v['longitude'] is! num || (v['latitude'] as num).abs()>90 || (v['longitude'] as num).abs()>180) return 'Valid coordinates required.';
  }
  if(type == 'media' && v is! List) return 'Select an attachment.';
  return null;
}

String? validateInterview(Json schema, Json answers, bool consent, bool locationConsent, bool privateAccess) {
  if(!consent) return 'Informed consent is required.';
  final effective = normalize(schema, answers);
  for(final q in questions(schema)) {
    if(!visible(q,effective)) continue;
    final a = Map<String,dynamic>.from(effective[q['id']]);
    if(q['sensitive']==true && !privateAccess && a['state']=='answered') return 'Protected-data access required.';
    if(q['type']=='location' && a['state']=='answered' && !locationConsent) return 'Explicit location consent required.';
    final message = validateAnswer(q,a);
    if(message!=null) return '${q['label']}: $message';
  }
  return null;
}

String safeCell(dynamic value) {
  if(value==null) return '';
  if(value is num) return value.toString();
  if(value is bool) return value ? '1':'0';
  var text = value is Map || value is List ? jsonEncode(value) : value.toString();
  if(RegExp(r'^[\s\x00-\x1f\ufeff]*[=+@-]').hasMatch(text) || text.startsWith('\t') || text.startsWith('\r') || text.startsWith('\n')) text="'$text";
  return text;
}
String csvLine(List<dynamic> cells, [String delimiter=',']) => cells.map((value) {
  final text=safeCell(value);
  return text.contains(delimiter)||text.contains('"')||text.contains('\n')||text.contains('\r') ? '"${text.replaceAll('"','""')}"':text;
}).join(delimiter)+'\r\n';
