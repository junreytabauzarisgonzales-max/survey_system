import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'schema.dart';
import 'store.dart';
import 'exports.dart';
import 'client.dart';

class InterviewPage extends StatefulWidget {
  final Store store;
  final Client client;
  final Json interview,version,project;
  const InterviewPage({super.key,required this.store,required this.client,required this.interview,required this.version,required this.project});
  @override State<InterviewPage> createState()=>_InterviewState();
}
class _InterviewState extends State<InterviewPage> {
  late Json record,answers;
  Json get schema=>Map<String,dynamic>.from(widget.version['schema']);
  bool get completed=>widget.interview['status']=='completed';
  bool get privateAccess=>widget.project['access']['identifiable']==true;
  bool get canEdit=>widget.project['access']['role']!='viewer' && widget.project['archived']!=true;
  Future<void> pending=Future.value();
  String message='Saved locally',reason='';
  bool saving=false,ready=false,showErrors=false;
  Object? saveError;
  List<Json> history=[];
  @override void initState(){super.initState();record=Map.from(widget.interview);answers=Map.from(record['answers']);load();}
  Future<void> load() async {
    final a=await widget.store.currentAnswers(record),h=await widget.store.read('corrections',where:'interview_id=?',args:[record['id']]);
    if(mounted)setState((){answers=a;history=h;ready=true;});
  }
  void change(Json q,dynamic value) {
    setState(()=>answers=normalize(schema,{...answers,q['id']:{'state':'answered','value':value}}));
    autosave();
  }
  void autosave() {
    if(completed||!canEdit)return;
    record={...record,'answers':answers,'updated_at':utcNow(),'synced':false};
    final snapshot=jsonDecode(jsonEncode(record)) as Json;
    setState(()=>message='Saving…');
    pending=pending.then((_)=>widget.store.save(snapshot)).then((_){saveError=null;if(mounted)setState(()=>message='Saved locally');}).catchError((Object e){saveError=e;if(mounted)setState(()=>message='Save failed: $e');});
  }
  Future<void> action(Future<void> Function() fn) async {
    setState(()=>saving=true);
    try{await fn();}catch(e){if(mounted)ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('$e')));}finally{if(mounted)setState(()=>saving=false);}
  }
  Future<void> finish() async {
    await pending;
    if(saveError!=null)throw StateError('Draft save failed. Retry before completing: $saveError');
    setState(()=>showErrors=true);
    final normalized=normalize(schema,answers);
    final error=validateInterview(schema,normalized,record['consent']==true,record['location_consent']==true,privateAccess);
    if(error!=null)throw StateError(error);
    if(completed){
      if(reason.trim().isEmpty)throw StateError('Enter a correction reason.');
      await widget.store.addCorrection(record,normalized,reason);
    }else{
      await widget.store.save({...record,'answers':normalized,'status':'completed','updated_at':utcNow(),'synced':false});
    }
    if(mounted)Navigator.pop(context);
  }
  Future<void> media(Json q) async {
    final selected=await documents.invokeMapMethod<String,dynamic>('pickMedia');
    if(selected==null)return;
    final source=File(selected['path'] as String);
    if(await source.length()>10*1024*1024)throw StateError('Maximum attachment size is 10 MiB.');
    final id=ids.v4(),directory=await getApplicationSupportDirectory();
    final target=await source.copy(p.join(directory.path,'media-$id'));
    await source.delete();
    final metadata={'id':id,'question_id':q['id'],'filename':selected['name'],'mime':selected['mime']};
    await widget.store.db.insert('media',{'owner':widget.store.owner,'id':id,'interview_id':record['id'],'path':target.path,'payload':jsonEncode(metadata),'synced':0});
    change(q,[...(answers[q['id']]?['value'] as List? ?? []),id]);
  }
  Future<void> capture(Json q) async {
    if(record['location_consent']!=true)throw StateError('Location capture requires explicit consent.');
    var permission=await Geolocator.checkPermission();
    if(permission==LocationPermission.denied)permission=await Geolocator.requestPermission();
    if(permission==LocationPermission.denied||permission==LocationPermission.deniedForever)throw StateError('Location permission was not granted.');
    final position=await Geolocator.getCurrentPosition(locationSettings:const LocationSettings(accuracy:LocationAccuracy.medium,timeLimit:Duration(seconds:30)));
    change(q,{'latitude':position.latitude,'longitude':position.longitude});
  }
  Future<void> reconcile() async {
    final confirmed=await showDialog<bool>(context:context,builder:(context)=>AlertDialog(title:const Text('Review server corrections?'),content:const Text('Load the current server correction history. Unsent local proposals will be preserved as superseded history for comparison. The original response remains unchanged.'),actions:[TextButton(onPressed:()=>Navigator.pop(context,false),child:const Text('Cancel')),FilledButton(onPressed:()=>Navigator.pop(context,true),child:const Text('Preserve proposals & refresh'))]));
    if(confirmed==true){await widget.client.reconcile(widget.store,record['id'],supersedePending:true);await load();}
  }
  Widget field(Json q) {
    if(!visible(q,answers))return const SizedBox.shrink();
    final protected=q['sensitive']==true||['media','location'].contains(q['type']);
    if(protected&&!privateAccess)return Card(child:ListTile(title:Text(q['label']),subtitle:const Text('Protected field. Identifiable-data access required.')));
    final a=Map<String,dynamic>.from(answers[q['id']]??{'state':'missing'}),value=a['value'],type=q['type'];
    final enabled=canEdit&&!saving;
    Widget input;
    if(type=='single'||type=='boolean') {
      final choices=type=='boolean'?[{'code':true,'label':'Yes'},{'code':false,'label':'No'}]:q['choices'] as List;
      input=DropdownButtonFormField<dynamic>(value:choices.any((c)=>c['code']==value)?value:null,hint:const Text('Select an answer'),items:choices.map<DropdownMenuItem<dynamic>>((c)=>DropdownMenuItem(value:c['code'],child:Text(c['label']))).toList(),onChanged:enabled?(v)=>change(q,v):null);
    }else if(type=='multiple') {
      input=Column(children:(q['choices'] as List).map<Widget>((c)=>CheckboxListTile(contentPadding:EdgeInsets.zero,title:Text(c['label']),value:(value as List? ?? []).contains(c['code']),onChanged:enabled?(checked){final list=List<dynamic>.from(value??[]);checked==true?list.add(c['code']):list.remove(c['code']);change(q,list);}:null)).toList());
    }else if(type=='location') {
      input=Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(value==null?'No coordinates recorded.':'Latitude ${value['latitude']}, longitude ${value['longitude']}'),TextButton.icon(onPressed:enabled&&record['location_consent']==true?()=>action(()=>capture(q)):null,icon:const Icon(Icons.my_location),label:const Text('Capture location with consent'))]);
    }else if(type=='media') {
      input=Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text('${(value as List? ?? []).length} attachment(s) stored'),TextButton.icon(onPressed:enabled?()=>action(()=>media(q)):null,icon:const Icon(Icons.attach_file),label:const Text('Choose image, recording or PDF'))]);
    }else {
      final numeric=['number','currency','rating'].contains(type);
      input=TextFormField(key:ValueKey('${q['id']}-${a['state']}'),initialValue:value?.toString()??'',enabled:enabled,maxLines:type=='text'?null:1,keyboardType:numeric?const TextInputType.numberWithOptions(decimal:true,signed:true):TextInputType.text,decoration:InputDecoration(hintText:type=='date'?'YYYY-MM-DD':type=='time'?'HH:mm':type=='currency'?'Numeric amount without currency symbol':null,helperText:q['help']),onChanged:(v)=>change(q,numeric?num.tryParse(v):v));
    }
    return Card(margin:const EdgeInsets.symmetric(vertical:8),child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text('${q['label']}${q['required']==true?' *':''}',style:Theme.of(context).textTheme.titleMedium),if(q['description']!=null)Text(q['description']),DropdownButton<String>(isExpanded:true,value:a['state'],items:['answered','missing','skipped','not_sure','prefer_not_to_answer'].map((s)=>DropdownMenuItem(value:s,child:Text(s.replaceAll('_',' ')))).toList(),onChanged:enabled?(state){setState(()=>answers=normalize(schema,{...answers,q['id']:state=='answered'?{'state':state,'value':q['default']??(type=='multiple'?[]:type=='boolean'?false:'')}:{'state':state}}));autosave();}:null),input,if(showErrors&&validateAnswer(q,a)!=null)Text(validateAnswer(q,a)!,style:const TextStyle(color:Colors.red))])));
  }
  @override Widget build(BuildContext context)=>WillPopScope(
    onWillPop:() async {await pending;return saveError==null;},
    child:Scaffold(appBar:AppBar(title:Text(widget.version['schema']['form_name'])),
      body:!ready?const Center(child:CircularProgressIndicator()):ListView(
        padding:const EdgeInsets.all(16),children:[
          Text('Version ${widget.version['number']} · ${record['status']}'),
          Text(message,style:const TextStyle(color:Colors.teal)),
          if(saveError!=null)TextButton(onPressed:autosave,child:const Text('Retry draft save')),
          Card(child:Padding(padding:const EdgeInsets.all(16),child:Text(schema['consent']??'Obtain voluntary informed consent.'))),
          CheckboxListTile(title:const Text('Respondent gave informed consent'),value:record['consent']==true,onChanged:!completed&&canEdit?(v){setState(()=>record['consent']=v==true);autosave();}:null),
          CheckboxListTile(title:const Text('Respondent explicitly consented to coordinates'),value:record['location_consent']==true,onChanged:!completed&&canEdit?(v){setState(()=>record['location_consent']=v==true);autosave();}:null),
          DropdownButtonFormField<String>(value:(widget.project['config']['locations'] as List? ?? []).any((l)=>l['id']==record['location'])?record['location']:null,hint:const Text('Location (optional)'),items:(widget.project['config']['locations'] as List? ?? []).map<DropdownMenuItem<String>>((l)=>DropdownMenuItem(value:l['id'],child:Text(l['label']))).toList(),onChanged:!completed&&canEdit?(v){setState(()=>record['location']=v);autosave();}:null),
          for(final s in schema['sections'])...<Widget>[
            Padding(padding:const EdgeInsets.only(top:24,bottom:8),child:Text(s['label'],style:Theme.of(context).textTheme.headlineSmall)),
            for(final q in s['questions'])field(Map<String,dynamic>.from(q))],
          if(completed)...[
            const Divider(),const Text('Original submission is immutable. Changes are tracked as corrections.'),
            ExpansionTile(title:Text('Correction history (${history.length})'),children:history.map((h)=>ExpansionTile(title:Text(h['reason']),subtitle:Text('${h['created_at']} · ${widget.client.isLocal?'saved on device':h['superseded']==true?'superseded proposal':h['synced']==true?'synced':'pending sync'}'),children:[for(final q in questions(schema))if(privateAccess||!(q['sensitive']==true||['media','location'].contains(q['type'])))ListTile(title:Text(q['label']),subtitle:Text(jsonEncode(h['answers'][q['id']])))] )).toList()),
            if(!widget.client.isLocal)TextButton(onPressed:saving?null:()=>action(reconcile),child:const Text('Review & reconcile server corrections')),
            TextField(decoration:const InputDecoration(labelText:'Reason for correction'),onChanged:(v)=>reason=v)],
          const SizedBox(height:24),
          FilledButton(onPressed:saving||!canEdit?null:()=>action(finish),child:Text(completed?'Save tracked correction':'Complete response')),
          if(!completed)TextButton(onPressed:saving?null:()=>action(() async {await pending;if(saveError!=null)throw StateError('Retry the failed draft save.');if(mounted)Navigator.pop(context);}),child:const Text('Save draft & close')),
          const SizedBox(height:30)])));
}
