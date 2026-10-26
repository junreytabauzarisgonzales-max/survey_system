import 'dart:convert';
import 'dart:io';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'schema.dart';
import 'store.dart';

class Client {
  static const secure=FlutterSecureStorage();
  String base,token;
  Json user;
  Client(this.base,this.token,this.user);
  bool get isLocal=>user['id']==Store.localOwner;
  static Future<Client> local() async {
    final client=Client('Device storage','',{'id':Store.localOwner,'name':'Local workspace','email':'On this device only'});
    await secure.write(key:'session',value:jsonEncode({'base':client.base,'token':'','user':client.user}));
    return client;
  }
  static Future<Client?> cached() async {
    final value=await secure.read(key:'session');
    if(value==null)return null;
    final data=jsonDecode(value);
    return Client(data['base'],data['token'],Map<String,dynamic>.from(data['user']));
  }
  static Future<Client> login(String base,String email,String password) async {
    base=base.replaceAll(RegExp(r'/+$'),'');
    final uri=Uri.parse(base);
    if(uri.scheme!='https' && !(uri.scheme=='http' && ['10.0.2.2','127.0.0.1','localhost'].contains(uri.host))) throw StateError('Use HTTPS, or a local emulator development URL.');
    final client=Client(base,'',{});
    final result=await client.call('/login',{'email':email,'password':password});
    client.token=result['token'];client.user=Map<String,dynamic>.from(result['user']);
    await secure.write(key:'session',value:jsonEncode({'base':base,'token':client.token,'user':client.user}));
    return client;
  }
  Future<dynamic> call(String path,[Json? body]) async {
    if(isLocal)throw StateError('This workspace stores data only on this device.');
    final headers={'Content-Type':'application/json','Authorization':'Bearer $token'};
    final uri=Uri.parse('$base/api$path');
    final response=await (body==null?http.get(uri,headers:headers):http.post(uri,headers:headers,body:jsonEncode(body))).timeout(const Duration(seconds:40));
    final value=jsonDecode(utf8.decode(response.bodyBytes));
    if(response.statusCode>=400)throw HttpException(value['error']??'Request failed (${response.statusCode})');
    return value;
  }
  Future<void> refresh(Store store) async {
    if(isLocal)return;
    final projects=(await call('/projects') as List).map((p)=>Map<String,dynamic>.from(p)).toList();
    final versions=<Json>[];
    for(final p in projects) {
      versions.addAll((await call('/projects/${p['id']}/versions') as List).map((v)=>Map<String,dynamic>.from(v)));
    }
    await store.cache(projects,versions);
  }

  Future<void> reconcile(Store store,String interview,{bool supersedePending=false}) async {
    final remote=Map<String,dynamic>.from(await call('/interviews/$interview'));
    final histories=await store.read('corrections',where:'interview_id=?',args:[interview]);
    final pending=histories.where((h)=>h['synced']!=true&&h['superseded']!=true).toList();
    if(pending.isNotEmpty&&!supersedePending)throw StateError('A local correction is pending. Review server history explicitly.');
    await store.db.transaction((txn) async {
      if(supersedePending)for(final h in pending) {
        await txn.update('corrections',{'payload':jsonEncode({...h,'superseded':true})},where:'owner=? AND id=?',whereArgs:[store.owner,h['id']]);
      }
      // Reinsert authoritative history in its server sequence; local proposals remain archived.
      for(final server in remote['corrections']) {
        final existing=histories.where((h)=>h['server_id']==server['id']||h['id']==server['id']).toList();
        for(final h in existing)await txn.delete('corrections',where:'owner=? AND id=?',whereArgs:[store.owner,h['id']]);
        final value={...Map<String,dynamic>.from(server),'synced':true,'server_id':server['id']};
        await txn.insert('corrections',{'owner':store.owner,'id':server['id'],'interview_id':interview,'payload':jsonEncode(value)});
      }
    });
    if(supersedePending)await store.audit({'kind':'correction_reconciliation','interview_id':interview,'preserved_local_proposals':pending.length});
  }

  Future<Json> synchronize(Store store) async {
    await refresh(store); // Revalidate authorization before transferring any local records.
    final grants={for(final p in await store.projects())p['id']:p};
    int sent=0;
    final errors=<String>[];
    final dirty=await store.read('interviews',where:'dirty=1');
    for(final interview in dirty) {
      final grant=grants[interview['project_id']];
      if(grant==null||grant['archived']==true||grant['access']['role']=='viewer') {errors.add('${interview['id']}: collection access unavailable');continue;}
      try {
        var outbox=await store.read('outbox',where:'id=?',args:[interview['id']]);
        if(outbox.isEmpty) {
          final event={'event_id':ids.v4(),'id':interview['id'],'version_id':interview['version_id'],'status':interview['status'],'revision':interview['revision'],'answers':interview['answers'],'consent':interview['consent'],'location_consent':interview['location_consent'],'location':interview['location'],'created_at':interview['created_at']};
          await store.db.insert('outbox',{'owner':store.owner,'id':interview['id'],'payload':jsonEncode(event)});
          outbox=[event];
        }
        final result=Map<String,dynamic>.from(await call('/interviews',outbox.single));
        final current=(await store.read('interviews',where:'id=?',args:[interview['id']])).single;
        final changed=jsonEncode(current['answers'])!=jsonEncode(outbox.single['answers'])||current['status']!=outbox.single['status']||current['consent']!=outbox.single['consent']||current['location_consent']!=outbox.single['location_consent']||current['location']!=outbox.single['location'];
        final updated={...current,'revision':result['revision'],'synced':!changed};
        await store.save(updated,synced:!changed);
        await store.db.delete('outbox',where:'owner=? AND id=?',whereArgs:[store.owner,interview['id']]);
        sent++;
      } catch(e) {errors.add('${interview['id']}: $e');}
    }
    // Uploads are separate resources and may follow immutable interview submission.
    final media=await store.db.query('media',where:'owner=? AND synced=0',whereArgs:[store.owner]);
    for(final row in media) {
      try {
        final local=(await store.read('interviews',where:'id=?',args:[row['interview_id']])).single;
        final grant=grants[local['project_id']];
        if(grant==null||grant['access']['identifiable']!=true)continue;
        final metadata=Map<String,dynamic>.from(jsonDecode(row['payload'] as String));
        await call('/interviews/${row['interview_id']}/attachments',{...metadata,'content':base64Encode(await File(row['path'] as String).readAsBytes())});
        await store.db.update('media',{'synced':1},where:'owner=? AND id=?',whereArgs:[store.owner,row['id']]);
      } catch(e) {errors.add('Attachment ${row['id']}: $e');}
    }
    for(final correction in await store.read('corrections')) {
      if(correction['synced']==true||correction['superseded']==true)continue;
      try {
        final local=(await store.read('interviews',where:'id=?',args:[correction['interview_id']])).single;
        if(grants[local['project_id']]==null)continue;
        final result=await call('/interviews/${correction['interview_id']}/corrections',correction);
        final updated={...correction,'synced':true,'server_id':result['id']};
        await store.db.update('corrections',{'payload':jsonEncode(updated)},where:'owner=? AND id=?',whereArgs:[store.owner,correction['id']]);
        sent++;
      } catch(e){errors.add('Correction ${correction['id']}: $e');}
    }
    await store.audit({'kind':'sync','sent':sent,'errors':errors.length});
    return {'sent':sent,'errors':errors};
  }
}
