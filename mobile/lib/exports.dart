import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'schema.dart';
import 'store.dart';

const documents=MethodChannel('org.agal.research/documents');

class LocalExport {
  final Store store;
  LocalExport(this.store);
  Future<Json> generate(String directory,{bool drafts=false,String? versionId,Set<String>? selected,String format='wide',bool identifiers=false,String delimiter=','}) async {
    final records=await store.authorizedInterviews(drafts:drafts,versionId:versionId,selected:selected);
    final grants={for(final pr in await store.projects())pr['id']:pr};
    final versions={for(final v in await store.versions())v['id']:v};
    // Reject a protected export before creating any file.
    if(identifiers && records.any((r)=>grants[r['project_id']]['access']['identifiable']!=true)) throw StateError('Identifiable-data access required for every selected project.');
    final used=records.map((r)=>r['version_id']).toSet();
    final definitions=<Json>[];
    for(final v in versions.values.where((v)=>used.contains(v['id']))) {
      for(final q in questions(Map<String,dynamic>.from(v['schema']))) {
        if(!identifiers && (q['sensitive']==true||['location','media'].contains(q['type'])))continue;
        definitions.add({'version':v,'question':q,'prefix':'v_${v['id']}__q_${q['id']}'});
      }
    }
    final columns=<dynamic>['project_id','interview_id','version_id','status','location','created_at','updated_at','exported_at','correction_id'];
    if(identifiers)columns.addAll(['respondent_id','researcher_id']);
    if(['long','raw'].contains(format))columns.addAll(['question_id','question_label','data_type','answer_state','answer_value']);
    else for(final d in definitions) {
      final q=d['question']; columns.add('${d['prefix']}__state');
      if(q['type']=='multiple') {for(final c in q['choices'])columns.add('${d['prefix']}__${c['code']}');}
      else {columns.add(d['prefix']);}
    }
    final at=utcNow();
    final file=File(p.join(directory,'survey-${DateTime.now().millisecondsSinceEpoch}.csv'));
    final sink=file.openWrite(encoding:utf8);
    int rowCount=0;
    try {
      sink.write(csvLine(columns,delimiter));
      for(final r in records) {
        final answers=await store.currentAnswers(r);
        final corrections=(await store.read('corrections',where:'interview_id=?',args:[r['id']])).where((h)=>h['superseded']!=true).toList();
        final latest=corrections.isEmpty?null:corrections.last;
        final base=<dynamic>[r['project_id'],r['id'],r['version_id'],r['status'],r['location'],r['created_at'],latest?['created_at']??r['updated_at'],at,latest?['server_id']??latest?['id']??''];
        if(identifiers)base.addAll([r['respondent_id'],store.owner]);
        if(['long','raw'].contains(format)) {
          for(final d in definitions.where((d)=>d['version']['id']==r['version_id'])) {
            final q=d['question'],a=answers[q['id']]??{'state':'missing'};
            sink.write(csvLine([...base,q['id'],q['label'],q['type'],a['state'],format=='raw'?jsonEncode(a):a['value']],delimiter));rowCount++;
          }
        } else {
          final values=[...base];
          for(final d in definitions) {
            final q=d['question'];
            final a=d['version']['id']==r['version_id']?(answers[q['id']]??{'state':'missing'}):{'state':'not_applicable_version'};
            values.add(a['state']);
            if(q['type']=='multiple') {for(final c in q['choices'])values.add(a['state']=='answered'?((a['value'] as List).contains(c['code'])?1:0):'');}
            else {values.add(a['value']);}
          }
          sink.write(csvLine(values,delimiter));rowCount++;
        }
        await sink.flush();
      }
    } finally {await sink.close();}
    final dictionary=File('${file.path}.dictionary.csv').openWrite(encoding:utf8);
    dictionary.write(csvLine(['column','version_id','question_id','label','type','choice_code','choice_label','encoding'],delimiter));
    for(final d in definitions) {
      final q=d['question'];
      dictionary.write(csvLine([d['prefix'],d['version']['id'],q['id'],q['label'],q['type'],'','','Stable codes; see __state'],delimiter));
      dictionary.write(csvLine(['${d['prefix']}__state',d['version']['id'],q['id'],q['label'],'state','','','answered|missing|skipped|not_sure|prefer_not_to_answer|not_applicable_version'],delimiter));
      for(final c in q['choices']??[])dictionary.write(csvLine([q['type']=='multiple'?'${d['prefix']}__${c['code']}':d['prefix'],d['version']['id'],q['id'],q['label'],q['type'],c['code'],c['label'],'Coded choice; multiple choice 0/1'],delimiter));
    }
    await dictionary.close();
    final manifest={'interview_count':records.length,'csv_row_count':rowCount,'exported_at':at,'format':format,'local_only':true,'identifiers':identifiers,'missing':'Separate state columns; non-answered values empty','formula_protection':'Dangerous text prefixed with apostrophe; raw JSON preserves original types','attachments':'References only; no embedded media'};
    await File('${file.path}.manifest.json').writeAsString(jsonEncode(manifest),flush:true);
    await store.audit({'kind':'local_csv','count':records.length,'rows':rowCount,'format':format,'identifiers':identifiers});
    return {...manifest,'path':file.path,'dictionary':'${file.path}.dictionary.csv','manifest':'${file.path}.manifest.json'};
  }
}
