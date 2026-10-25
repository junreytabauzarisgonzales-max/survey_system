import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';
import 'schema.dart';

const ids = Uuid();
String utcNow()=>DateTime.now().toUtc().toIso8601String();

class Store {
  final Database db;
  final String owner;
  Store(this.db,this.owner);
  static Future<Store> open(String owner) async {
    final db=await openDatabase(p.join(await getDatabasesPath(),'agal.sqlite'),version:1,onCreate:(db,version) async {
      await db.execute('CREATE TABLE projects(owner TEXT,id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
      await db.execute('CREATE TABLE versions(owner TEXT,id TEXT,project_id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
      await db.execute('CREATE TABLE interviews(owner TEXT,id TEXT,project_id TEXT,version_id TEXT,status TEXT,dirty INTEGER,payload TEXT,PRIMARY KEY(owner,id))');
      await db.execute('CREATE TABLE outbox(owner TEXT,id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
      await db.execute('CREATE TABLE corrections(owner TEXT,id TEXT,interview_id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
      await db.execute('CREATE TABLE media(owner TEXT,id TEXT,interview_id TEXT,path TEXT,payload TEXT,synced INTEGER,PRIMARY KEY(owner,id))');
      await db.execute('CREATE TABLE audits(owner TEXT,id TEXT,payload TEXT,PRIMARY KEY(owner,id))');
    });
    return Store(db,owner);
  }
  Future<List<Json>> read(String table,{String? where,List<Object?> args=const []}) async =>
    (await db.query(table,where:'owner=?${where==null?'':' AND $where'}',whereArgs:[owner,...args],orderBy:table=='corrections'?'rowid':null)).map((r)=>Map<String,dynamic>.from(jsonDecode(r['payload'] as String))).toList();
  Future<List<Json>> projects()=>read('projects');
  Future<List<Json>> versions()=>read('versions');
  Future<List<Json>> interviews()=>read('interviews');
  Future<Json> project(String id) async => (await read('projects',where:'id=?',args:[id])).single;
  Future<Json> version(String id) async => (await read('versions',where:'id=?',args:[id])).single;

  Future<void> cache(List<Json> projects,List<Json> versions) async {
    await db.transaction((txn) async {
      // Cached grants are replaced only after a successful online refresh. Offline access uses the last grant.
      await txn.delete('projects',where:'owner=?',whereArgs:[owner]);
      for(final row in projects) {
        await txn.insert('projects',{'owner':owner,'id':row['id'],'payload':jsonEncode(row)},conflictAlgorithm:ConflictAlgorithm.replace);
      }
      for(final row in versions) {
        if((row['schema']['engine_version']??1)!=1)throw StateError('A questionnaire requires a newer renderer. Cached forms are still available offline.');
        final prior=await txn.query('versions',where:'owner=? AND id=?',whereArgs:[owner,row['id']]);
        if(prior.isNotEmpty) {
          final old=jsonDecode(prior.single['payload'] as String);
          if(jsonEncode(old['schema'])!=jsonEncode(row['schema'])) throw StateError('Published schema changed on server');
        }
        await txn.insert('versions',{'owner':owner,'id':row['id'],'project_id':row['project_id'],'payload':jsonEncode(row)},conflictAlgorithm:ConflictAlgorithm.replace);
      }
    });
  }

  Future<void> save(Json interview,{bool synced=false}) async {
    await db.transaction((txn) async {
      final old=await txn.query('interviews',where:'owner=? AND id=?',whereArgs:[owner,interview['id']]);
      if(!synced && old.isNotEmpty && old.single['status']=='completed') throw StateError('Completed interviews use tracked corrections');
      await txn.insert('interviews',{'owner':owner,'id':interview['id'],'project_id':interview['project_id'],'version_id':interview['version_id'],'status':interview['status'],'dirty':synced?0:1,'payload':jsonEncode(interview)},conflictAlgorithm:ConflictAlgorithm.replace);
    });
  }
  Future<void> addCorrection(Json interview,Json answers,String reason) async {
    final history=await read('corrections',where:'interview_id=?',args:[interview['id']]);
    final unsent=history.where((h)=>h['synced']!=true&&h['superseded']!=true);
    if(unsent.isNotEmpty) throw StateError('Synchronize the pending correction first.');
    final correction={'id':ids.v4(),'interview_id':interview['id'],'answers':answers,'reason':reason,'created_at':utcNow(),'base_correction_id':history.isEmpty?null:history.last['server_id'],'synced':false};
    await db.insert('corrections',{'owner':owner,'id':correction['id'],'interview_id':interview['id'],'payload':jsonEncode(correction)});
  }
  Future<Json> currentAnswers(Json interview) async {
    final history=await read('corrections',where:'interview_id=?',args:[interview['id']]);
    final active=history.where((h)=>h['superseded']!=true).toList();
    return Map<String,dynamic>.from(active.isEmpty?interview['answers']:active.last['answers']);
  }
  Future<List<Json>> authorizedInterviews({bool drafts=false,String? versionId,Set<String>? selected}) async {
    final grants={for(final pr in await projects()) pr['id']:pr};
    return (await interviews()).where((i) {
      final pr=grants[i['project_id']];
      return pr!=null && (drafts||i['status']=='completed') && (versionId==null||i['version_id']==versionId) && (selected==null||selected.contains(i['id']));
    }).toList();
  }
  Future<void> audit(Json event) async { await db.insert('audits',{'owner':owner,'id':ids.v4(),'payload':jsonEncode({...event,'at':utcNow()})}); }

  Future<String> createBackup(String directory) async {
    final grants=await projects(), versions=await this.versions();
    final interviews=await authorizedInterviews(drafts:true);
    final allowed=interviews.map((r)=>r['id']).toSet();
    for(final r in interviews) {
      final grant=grants.firstWhere((p)=>p['id']==r['project_id']);
      final schema=versions.firstWhere((v)=>v['id']==r['version_id'])['schema'];
      final sensitive=questions(Map<String,dynamic>.from(schema)).where((q)=>q['sensitive']==true||['media','location'].contains(q['type'])).map((q)=>q['id']).toSet();
      final corrections=await read('corrections',where:'interview_id=?',args:[r['id']]);
      final pending=await read('outbox',where:'id=?',args:[r['id']]);
      if(grant['access']['identifiable']!=true && [r['answers'],...corrections.map((c)=>c['answers']),...pending.map((e)=>e['answers'])].any((a)=>sensitive.any((id)=>a[id]?['state']=='answered'))) throw StateError('Recovery backup would include protected fields after a permission change. Refresh access or use anonymous CSV.');
    }
    // This is an app-format recovery archive, separate from CSV and synchronization.
    final identifiable=interviews.where((r)=>grants.firstWhere((p)=>p['id']==r['project_id'])['access']['identifiable']==true).map((r)=>r['id']).toSet();
    final mediaRows=(await db.query('media',where:'owner=?',whereArgs:[owner])).where((r)=>allowed.contains(r['interview_id'])&&identifiable.contains(r['interview_id'])).toList();
    final data=<String,dynamic>{'format':'agal-local-backup-v1','owner':owner,'created_at':utcNow(),'versions':versions.where((v)=>grants.any((p)=>p['id']==v['project_id'])).toList(),'interviews':interviews,'corrections':(await read('corrections')).where((c)=>allowed.contains(c['interview_id'])).toList(),'outbox':(await read('outbox')).where((e)=>allowed.contains(e['id'])).toList(),'media':[for(final row in mediaRows){...jsonDecode(row['payload'] as String),'interview_id':row['interview_id'],'synced':row['synced']}]};
    data['media_files']=[for(final row in mediaRows) {'id':row['id'],'bytes':base64Encode(await File(row['path'] as String).readAsBytes())}];
    final file=File(p.join(directory,'agal-local-backup.json'));
    await file.writeAsString(jsonEncode(data),flush:true);
    await audit({'kind':'backup','count':interviews.length});
    return file.path;
  }

  Future<void> restoreBackup(String path,String directory) async {
    final file=File(path);
    if(await file.length()>100*1024*1024)throw StateError('Recovery archive exceeds 100 MiB.');
    final data=jsonDecode(await file.readAsString());
    if(data['format']!='agal-local-backup-v1'||data['owner']!=owner)throw StateError('Backup belongs to a different account or format.');
    final grants={for(final pr in await projects())pr['id']:pr};
    final cached={for(final v in await versions())v['id']:v};
    final records=(data['interviews'] as List).map((r)=>Map<String,dynamic>.from(r)).toList();
    for(final r in records) {
      if(grants[r['project_id']]==null||cached[r['version_id']]==null||cached[r['version_id']]['project_id']!=r['project_id'])throw StateError('Download authorized projects and original form versions before restoring.');
      final grant=grants[r['project_id']];
      final schema=Map<String,dynamic>.from(cached[r['version_id']]['schema']);
      if(grant['access']['identifiable']!=true && questions(schema).any((q)=>(q['sensitive']==true||['media','location'].contains(q['type']))&&r['answers'][q['id']]?['state']=='answered'))throw StateError('Protected-data permission required for this backup.');
    }
    final allowed=records.map((r)=>r['id']).toSet();
    final paths=<String,String>{};
    for(final media in data['media_files'] as List? ?? []) {
      final id=media['id'] as String;
      if(!RegExp(r'^[a-f0-9-]{36}$').hasMatch(id))throw StateError('Invalid attachment ID');
      final target=File(p.join(directory,'restored-${ids.v4()}-$id'));
      await target.writeAsBytes(base64Decode(media['bytes']),flush:true);
      paths[id]=target.path;
    }
    await db.transaction((txn) async {
      for(final r in records) {
        final old=await txn.query('interviews',where:'owner=? AND id=?',whereArgs:[owner,r['id']]);
        if(old.isNotEmpty) {
          if(old.single['payload']!=jsonEncode(r))throw StateError('Existing interview ${r['id']} differs. Restore to a separate device or review the conflict.');
        }else {
          await txn.insert('interviews',{'owner':owner,'id':r['id'],'project_id':r['project_id'],'version_id':r['version_id'],'status':r['status'],'dirty':r['synced']==true?0:1,'payload':jsonEncode(r)});
        }
      }
      for(final c in data['corrections'] as List? ?? []) {
        if(!allowed.contains(c['interview_id']))throw StateError('Unknown correction interview');
        await txn.insert('corrections',{'owner':owner,'id':c['id'],'interview_id':c['interview_id'],'payload':jsonEncode(c)},conflictAlgorithm:ConflictAlgorithm.ignore);
      }
      for(final e in data['outbox'] as List? ?? []) {
        if(!allowed.contains(e['id']))throw StateError('Unknown sync interview');
        await txn.insert('outbox',{'owner':owner,'id':e['id'],'payload':jsonEncode(e)},conflictAlgorithm:ConflictAlgorithm.ignore);
      }
      for(final m in data['media'] as List? ?? []) {
        if(!allowed.contains(m['interview_id'])||paths[m['id']]==null)throw StateError('Invalid backup attachment');
        await txn.insert('media',{'owner':owner,'id':m['id'],'interview_id':m['interview_id'],'path':paths[m['id']],'synced':m['synced'],'payload':jsonEncode({'id':m['id'],'question_id':m['question_id'],'filename':m['filename'],'mime':m['mime']})},conflictAlgorithm:ConflictAlgorithm.ignore);
      }
    });
    await audit({'kind':'restore','count':records.length});
  }
}
