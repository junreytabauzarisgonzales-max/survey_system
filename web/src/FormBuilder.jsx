import React, {useState} from 'react';
import {allQuestions, blankSchema, conditionValue, types, uuid} from './core';
import {DynamicForm} from './Renderer';
import {QuestionImporter} from './QuestionImporter';

export function FormBuilder({schema, onChange}) {
  const [preview,setPreview]=useState(false), [answers,setAnswers]=useState({}), [importing,setImporting]=useState(false);
  const edit = fn => { const copy=structuredClone(schema); fn(copy); onChange(copy); };
  const move = (list,index,delta) => { if(index+delta>=0 && index+delta<list.length) [list[index],list[index+delta]]=[list[index+delta],list[index]]; };
  const newQuestion = () => ({id:uuid(),label:'New question',type:'text',required:false,sensitive:false});
  if (!schema) return <button onClick={()=>onChange(blankSchema())}>Configure fields</button>;
  return <div className="builder"><div className="toolbar"><span className="badge">Question builder</span><button className="primary" onClick={()=>setImporting(true)}>Paste questions</button><button onClick={()=>setPreview(!preview)}>{preview?'Edit questions':'Preview form'}</button></div>
    {preview ? <DynamicForm schema={schema} answers={answers} onChange={setAnswers} locationConsent={true}/> : <>
      {schema.sections.map((section,si)=><section className="section-editor" key={section.id}>
        <div className="toolbar"><label className="grow">Section title<input value={section.label} onChange={e=>edit(s=>s.sections[si].label=e.target.value)}/></label>
          <button aria-label="Move section up" onClick={()=>edit(s=>move(s.sections,si,-1))}>↑</button><button aria-label="Move section down" onClick={()=>edit(s=>move(s.sections,si,1))}>↓</button>
          <button className="danger" onClick={()=>edit(s=>s.sections.splice(si,1))}>Remove section</button></div>
        {section.questions.map((q,qi)=>{
          const previous=allQuestions(schema).slice(0,allQuestions(schema).findIndex(x=>x.id===q.id));
          const change=(key,value)=>edit(s=>{s.sections[si].questions[qi][key]=value;});
          return <article className="question-editor" key={q.id}>
            <div className="toolbar"><span className="question-number">{qi+1}</span><strong className="grow">{q.label}</strong><button onClick={()=>edit(s=>move(s.sections[si].questions,qi,-1))} aria-label="Move question up">↑</button><button onClick={()=>edit(s=>move(s.sections[si].questions,qi,1))} aria-label="Move question down">↓</button><button onClick={()=>edit(s=>s.sections[si].questions.splice(qi+1,0,{...structuredClone(q),id:uuid(),label:q.label+' (copy)'}))}>Duplicate</button><button className="danger" onClick={()=>edit(s=>s.sections[si].questions.splice(qi,1))}>Remove</button></div>
            <div className="grid"><label>Question label<input value={q.label} onChange={e=>change('label',e.target.value)}/></label>
              <label>Answer type<select value={q.type} onChange={e=>edit(s=>{const target=s.sections[si].questions[qi]; target.type=e.target.value; delete target.default; target.validation={}; if(['single','multiple'].includes(target.type)) target.choices=target.choices||[{code:'choice_1',label:'Choice 1'}];})}>{types.map(t=><option key={t}>{t}</option>)}</select></label>
              <label>Description<input value={q.description||''} onChange={e=>change('description',e.target.value)}/></label><label>Help text<input value={q.help||''} onChange={e=>change('help',e.target.value)}/></label></div>
            <div className="toolbar"><label className="check"><input type="checkbox" checked={!!q.required} onChange={e=>change('required',e.target.checked)}/>Required</label><label className="check"><input type="checkbox" checked={!!q.sensitive} onChange={e=>change('sensitive',e.target.checked)}/>Personal / protected information</label><small>Stable ID: {q.id}</small></div>
            {['single','multiple'].includes(q.type) && <div className="choices">{q.choices.map((ch,ci)=><div className="toolbar" key={ci}><label className="grow">Choice label<input value={ch.label} onChange={e=>edit(s=>s.sections[si].questions[qi].choices[ci].label=e.target.value)}/></label><label>Stable code<input value={ch.code} onChange={e=>edit(s=>s.sections[si].questions[qi].choices[ci].code=e.target.value)}/></label><button onClick={()=>edit(s=>s.sections[si].questions[qi].choices.splice(ci,1))}>Remove</button></div>)}<button onClick={()=>change('choices',[...q.choices,{code:'c_'+uuid().slice(0,8),label:'New choice'}])}>+ Add choice</button></div>}
            <details><summary>Validation, default answer & conditional visibility</summary><div className="grid">
              {(q.type==='text'?['min_length','max_length']:q.type==='multiple'?['min_selections','max_selections']:['number','currency','rating'].includes(q.type)?['min','max']:[]).map(key=><label key={key}>{key.replaceAll('_',' ')}<input type="number" value={q.validation?.[key]??''} onChange={e=>{const rules={...q.validation}; e.target.value===''?delete rules[key]:rules[key]=Number(e.target.value); change('validation',rules);}}/></label>)}
              {!['media','location'].includes(q.type)&&<label>Default value (optional){['single','boolean','multiple'].includes(q.type)?<select multiple={q.type==='multiple'} value={q.type==='multiple'?(q.default||[]):String(q.default??'')} onChange={e=>{if(q.type==='multiple') change('default',[...e.target.selectedOptions].map(o=>o.value)); else if(e.target.value==='') edit(s=>delete s.sections[si].questions[qi].default); else change('default',q.type==='boolean'?e.target.value==='true':e.target.value);}}>{q.type!=='multiple'&&<option value="">No default</option>}{(q.type==='boolean'?[{code:'true',label:'Yes'},{code:'false',label:'No'}]:q.choices).map(c=><option key={c.code} value={c.code}>{c.label}</option>)}</select>:<input type={['number','currency','rating'].includes(q.type)?'number':['date','time'].includes(q.type)?q.type:'text'} value={q.default??''} onChange={e=>e.target.value===''?edit(s=>delete s.sections[si].questions[qi].default):change('default',['number','currency','rating'].includes(q.type)?Number(e.target.value):e.target.value)}/>}</label>}
              <label>Show when previous question…<select value={q.condition?.question_id||''} onChange={e=>e.target.value?change('condition',{question_id:e.target.value,op:'answered'}):edit(s=>delete s.sections[si].questions[qi].condition)}><option value="">Always show</option>{previous.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
              {q.condition&&<><label>Operator<select value={q.condition.op} onChange={e=>change('condition',{...q.condition,op:e.target.value})}>{['answered','equals','not_equals','contains'].map(op=><option key={op}>{op}</option>)}</select></label>{q.condition.op!=='answered'&&<label>Compared value (choice code for choices)<input value={String(q.condition.value??'')} onChange={e=>change('condition',{...q.condition,value:conditionValue(previous.find(p=>p.id===q.condition.question_id),e.target.value)})}/></label>}</>}
            </div></details>
          </article>;
        })}
        <button className="add" onClick={()=>edit(s=>s.sections[si].questions.push(newQuestion()))}>+ Add question</button>
      </section>)}
      <button onClick={()=>edit(s=>s.sections.push({id:uuid(),label:'New section',questions:[]}))}>+ Add section</button>
    </>}
    {importing && <QuestionImporter schema={schema} onChange={onChange} onClose={()=>setImporting(false)}/>}
  </div>;
}
