import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:agal_research/schema.dart';
import 'package:agal_research/store.dart';
import 'package:agal_research/exports.dart';

void main() {
  late Directory directory;
  late Store store;
  setUp(() async {
    sqfliteFfiInit();
    databaseFactory=databaseFactoryFfi;
    directory=await Directory.systemTemp.createTemp('survey-local-');
    await databaseFactory.setDatabasesPath(directory.path);
    store=await Store.open(Store.localOwner);
  });
  tearDown(() async {await store.db.close();await directory.delete(recursive:true);});

  test('create, complete, correct, reopen and export without a server',() async {
    await store.createLocalSurvey('Local survey','Voluntary participation.',[
      {'id':ids.v4(),'label':'Hours studied','type':'number','required':true},
    ]);
    final version=(await store.versions()).single;
    final question=questions(Map<String,dynamic>.from(version['schema'])).single;
    final answers=<String,dynamic>{question['id']:{'state':'answered','value':3}};
    final record=<String,dynamic>{'id':ids.v4(),'project_id':version['project_id'],'version_id':version['id'],'status':'completed','answers':answers,'consent':true,'created_at':utcNow()};
    await store.save(record);
    await store.addCorrection(record,{question['id']:{'state':'answered','value':4}},'First correction');
    await store.addCorrection(record,{question['id']:{'state':'answered','value':5}},'Second correction');
    await store.db.close();
    store=await Store.open(Store.localOwner);
    expect((await store.currentAnswers((await store.interviews()).single))[question['id']]['value'],5);
    final result=await LocalExport(store).generate(directory.path);
    expect(result['interview_count'],1);
    expect(await File(result['path']).readAsString(),contains(',5\r\n'));
  });

  test('a recovery backup restores local definitions and answers to an empty device',() async {
    await store.createLocalSurvey('Recovery survey','Consent',[
      {'id':ids.v4(),'label':'Notes','type':'text'},
    ]);
    final version=(await store.versions()).single;
    await store.save({'id':ids.v4(),'project_id':version['project_id'],'version_id':version['id'],'status':'draft','answers':{},'created_at':utcNow()});
    final path=await store.createBackup(directory.path);
    expect(jsonDecode(await File(path).readAsString())['projects'],hasLength(1));
    final other=Directory('${directory.path}/other');
    await other.create();
    await store.db.close();
    await databaseFactory.setDatabasesPath(other.path);
    store=await Store.open(Store.localOwner);
    await store.restoreBackup(path,other.path);
    expect(await store.projects(),hasLength(1));
    expect(await store.versions(),hasLength(1));
    expect(await store.authorizedInterviews(drafts:true),hasLength(1));
  });
}
