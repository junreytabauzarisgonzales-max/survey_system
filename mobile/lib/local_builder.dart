import 'package:flutter/material.dart';
import 'schema.dart';
import 'store.dart';

class LocalBuilder extends StatefulWidget {
  final Store store;
  const LocalBuilder({super.key,required this.store});
  @override State<LocalBuilder> createState()=>_LocalBuilderState();
}

class _LocalBuilderState extends State<LocalBuilder> {
  final title=TextEditingController();
  final consent=TextEditingController(text:'Participation is voluntary. You may skip questions or stop at any time.');
  final items=<Json>[];
  bool busy=false;
  String error='';
  @override void initState(){super.initState();add();}
  void add()=>items.add({'id':ids.v4(),'label':'','type':'text','required':false,'choiceText':''});
  @override void dispose(){title.dispose();consent.dispose();super.dispose();}

  Future<void> save() async {
    setState((){busy=true;error='';});
    try {
      final questions=items.map((item){
        final q=Map<String,dynamic>.from(item)..remove('choiceText');
        q['label']=(q['label'] as String).trim();
        if(['single','multiple'].contains(q['type'])) {
          final labels=(item['choiceText'] as String).split('\n').map((s)=>s.trim()).where((s)=>s.isNotEmpty).toList();
          q['choices']=[for(var i=0;i<labels.length;i++){'code':'choice_${i+1}','label':labels[i]}];
        }
        return q;
      }).toList();
      await widget.store.createLocalSurvey(title.text,consent.text,questions);
      if(mounted)Navigator.pop(context);
    } catch(e) {if(mounted)setState(()=>error='$e');}
    finally {if(mounted)setState(()=>busy=false);}
  }

  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Create a local survey')),
    body:ListView(padding:const EdgeInsets.all(20),children:[
      const Text('Saved only on this device. Once saved, questions are fixed so existing answers keep their original meaning.'),
      const SizedBox(height:16),
      TextField(controller:title,enabled:!busy,decoration:const InputDecoration(labelText:'Survey title')),
      const SizedBox(height:16),
      TextField(controller:consent,enabled:!busy,maxLines:3,decoration:const InputDecoration(labelText:'Consent statement')),
      for(final q in items)Card(key:ValueKey(q['id']),child:Padding(padding:const EdgeInsets.all(16),child:Column(children:[
        TextFormField(initialValue:q['label'],enabled:!busy,decoration:const InputDecoration(labelText:'Question'),onChanged:(v)=>q['label']=v),
        DropdownButtonFormField<String>(value:q['type'],decoration:const InputDecoration(labelText:'Answer type'),items:const {
          'text':'Text','number':'Number','currency':'Currency','rating':'Rating','single':'Single choice','multiple':'Multiple choice','boolean':'Yes / No','date':'Date','time':'Time','media':'Attachment','location':'Coordinates',
        }.entries.map((e)=>DropdownMenuItem(value:e.key,child:Text(e.value))).toList(),onChanged:busy?null:(v)=>setState(()=>q['type']=v)),
        if(['single','multiple'].contains(q['type']))TextFormField(initialValue:q['choiceText'],enabled:!busy,maxLines:4,decoration:const InputDecoration(labelText:'Choices (one per line)'),onChanged:(v)=>q['choiceText']=v),
        SwitchListTile(title:const Text('Required'),value:q['required']==true,onChanged:busy?null:(v)=>setState(()=>q['required']=v)),
        TextButton(onPressed:busy?null:()=>setState(()=>items.remove(q)),child:const Text('Remove question')),
      ]))),
      OutlinedButton.icon(onPressed:busy?null:()=>setState(add),icon:const Icon(Icons.add),label:const Text('Add question')),
      if(error.isNotEmpty)Text(error,style:const TextStyle(color:Colors.red)),
      FilledButton(onPressed:busy?null:save,child:Text(busy?'Saving…':'Save survey to this device')),
    ]),
  );
}
