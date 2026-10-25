import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:agal_research/store.dart';
import 'package:agal_research/exports.dart';

void main(){
  late Store store;late Directory temp;
  setUp(() async {
    sqfliteFfiInit();temp=await Directory.systemTemp.createTemp('agal-offline-');
    final db=await databaseFactoryFfi.openDatabase(inMemoryDatabasePath);
    await db.execute('CREATE TABLE projects(owner TEXT,id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
    await db.execute('CREATE TABLE versions(owner TEXT,id TEXT,project_id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
    await db.execute('CREATE TABLE interviews(owner TEXT,id TEXT,project_id TEXT,version_id TEXT,status TEXT,dirty INTEGER,payload TEXT,PRIMARY KEY(owner,id))');
    await db.execute('CREATE TABLE corrections(owner TEXT,id TEXT,interview_id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
    await db.execute('CREATE TABLE audits(owner TEXT,id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
    store=Store(db,'researcher');
    await store.cache([{'id':'project','access':{'role':'researcher','identifiable':false}}],[{'id':'version','project_id':'project','number':1,'schema':{'sections':[{'id':'section','label':'Custom section','questions':[{'id':'story','label':'A custom question','type':'text'},{'id':'choices','label':'Multiple','type':'multiple','choices':[{'code':'a','label':'Choice A'},{'code':'b','label':'Choice B'}]},{'id':'secret','label':'Private','type':'text','sensitive':true}]}]}}]);
  });
  tearDown(() async {await store.db.close();await temp.delete(recursive:true);});
  test('offline completion, immutability, UTF-8 export and privacy require no client',() async {
    final record=<String,dynamic>{'id':'interview','project_id':'project','version_id':'version','status':'draft','answers':{'story':{'state':'answered','value':'Kumusta, "ñ"\n🌿'},'choices':{'state':'answered','value':['a','b']},'secret':{'state':'answered','value':'Do not export'}},'created_at':utcNow(),'updated_at':utcNow()};
    await store.save(record);
    expect((await store.interviews()).single['status'],'draft');
    await store.save({...record,'status':'completed'});
    await expectLater(store.save({...record,'status':'draft'}),throwsStateError);
    final manifest=await LocalExport(store).generate(temp.path);
    final csv=await File(manifest['path']).readAsString(encoding:utf8);
    expect(manifest['interview_count'],1);expect(csv,contains('"Kumusta, ""ñ""\n🌿"'));
    expect(csv,contains('__a'));expect(csv,contains('__b'));expect(csv,isNot(contains('Do not export')));
    await expectLater(LocalExport(store).generate(temp.path,identifiers:true),throwsStateError);
    expect((await store.read('audits')).single['kind'],'local_csv');
  });
  test('cached revoked grants hide records from local export',() async {
    await store.save({'id':'interview','project_id':'project','version_id':'version','status':'completed','answers':{},'created_at':utcNow()});
    await store.cache([],[]);
    expect(await store.authorizedInterviews(),isEmpty);
    final manifest=await LocalExport(store).generate(temp.path);
    expect(manifest['interview_count'],0);
  });
}
