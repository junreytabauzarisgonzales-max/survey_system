import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:agal_research/schema.dart';

void main(){
  test('CSV escaping, UTF-8 and spreadsheet protection',(){
    final row=csvLine(['Kumusta, "ñ"\n🌿','=1+1',-5.5,['a','b']]);
    expect(row,contains('"Kumusta, ""ñ""\n🌿"'));
    expect(row,contains("'=1+1"));
    expect(row,contains(',-5.5,'));
    expect(utf8.decode(utf8.encode(row)),row);
  });
  test('hidden cascade values become skipped',(){
    final schema=<String,dynamic>{'sections':[{'questions':[{'id':'a','type':'boolean'},{'id':'b','type':'text','condition':{'question_id':'a','op':'equals','value':true}},{'id':'c','type':'text','condition':{'question_id':'b','op':'answered'}}]}]};
    final answers=normalize(schema,{'a':{'state':'answered','value':false},'b':{'state':'answered','value':'stale'},'c':{'state':'answered','value':'stale'}});
    expect(answers['b']['state'],'skipped');expect(answers['c']['state'],'skipped');
  });
  test('numeric and missing semantics',(){
    expect(validateAnswer({'type':'number','required':true},{'state':'answered','value':0}),isNull);
    expect(validateAnswer({'type':'number','required':true},{'state':'missing'}),isNotNull);
    expect(validateAnswer({'type':'number','required':true},{'state':'not_sure'}),isNull);
    expect(validateAnswer({'type':'currency'},{'state':'answered','value':'₱10'}),isNotNull);
  });
}
