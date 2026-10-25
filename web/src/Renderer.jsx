import React from 'react';
import {isVisible, normalize, states, validate} from './core';

export function DynamicForm({schema,answers,onChange,locationConsent=false,allowPrivate=true,onFile,showErrors=false,readOnly=false}) {
  const normalized=normalize(schema,answers);
  const set=(q,value)=>onChange(normalize(schema,{...normalized,[q.id]:value===''||value===null?{state:'missing'}:{state:'answered',value}}));
  return schema.sections.map(section=><section className="form-section" key={section.id}><h3>{section.label}</h3>{section.questions.map(q=>{
    if(!isVisible(q,normalized)) return null;
    const protectedField=q.sensitive||['media','location'].includes(q.type);
    if(protectedField&&!allowPrivate) return <p key={q.id}>{q.label} — protected field; identifiable-data permission required.</p>;
    const a=normalized[q.id]||{state:'missing'}, value=a.value, disabled=readOnly||(q.type==='location'&&!locationConsent);
    return <div className="response-field" key={q.id}><div className="toolbar"><strong className="grow">{q.label}{q.required?' *':''}</strong><select aria-label={q.label+' answer status'} disabled={readOnly} value={a.state} onChange={e=>onChange({...normalized,[q.id]:e.target.value==='answered'?{state:'answered',value:q.default??(q.type==='multiple'?[]:q.type==='boolean'?false:'')}:{state:e.target.value}})}>{states.map(s=><option key={s} value={s}>{s.replaceAll('_',' ')}</option>)}</select></div>
      <p>{q.description}</p>
      {q.type==='text'?<textarea aria-label={q.label} disabled={disabled} value={value??''} onChange={e=>set(q,e.target.value)}/>:
      q.type==='single'?<select aria-label={q.label} disabled={disabled} value={value??''} onChange={e=>set(q,e.target.value)}><option value="">Select…</option>{q.choices.map(c=><option key={c.code} value={c.code}>{c.label}</option>)}</select>:
      q.type==='multiple'?<div>{q.choices.map(c=><label className="check" key={c.code}><input type="checkbox" disabled={disabled} checked={(value||[]).includes(c.code)} onChange={e=>set(q,e.target.checked?[...(value||[]),c.code]:(value||[]).filter(v=>v!==c.code))}/>{c.label}</label>)}</div>:
      q.type==='boolean'?<select aria-label={q.label} disabled={disabled} value={value===undefined?'':String(value)} onChange={e=>set(q,e.target.value===''?null:e.target.value==='true')}><option value="">Select…</option><option value="true">Yes</option><option value="false">No</option></select>:
      q.type==='location'?<><small>Explicit location consent is required. Coordinates are optional unless this question is required.</small><div className="grid">{['latitude','longitude'].map(key=><label key={key}>{key}<input type="number" step="any" disabled={disabled} value={value?.[key]??''} onChange={e=>set(q,{...value,[key]:e.target.value===''?null:Number(e.target.value)})}/></label>)}</div></>:
      q.type==='media'?<><small>Attachment references: {(value||[]).join(', ')||'none'}</small>{onFile?<input aria-label={q.label} type="file" disabled={disabled} accept="image/jpeg,image/png,audio/mp4,audio/mpeg,audio/wav,application/pdf" onChange={e=>e.target.files[0]&&onFile(q,e.target.files[0])}/>:<p>Media files can be attached when collecting an interview.</p>}</>:
      <input aria-label={q.label} disabled={disabled} type={['number','currency','rating'].includes(q.type)?'number':q.type} step="any" value={value??''} onChange={e=>set(q,['number','currency','rating'].includes(q.type)?(e.target.value===''?null:Number(e.target.value)):e.target.value)}/>}
      <small>{q.help}</small>{showErrors&&validate(q,a)&&<p className="error">{validate(q,a)}</p>}
    </div>;
  })}</section>);
}
