import React,{useEffect,useMemo,useState} from 'react';
import {createRealtimeClient} from '@neon/realtime/client';
import {api,download,downloadManifest} from './api';
import {saveBlob} from './device';
import {allQuestions,conditionValue,defaults,isVisible,normalize,uuid,validate} from './core';
import {DynamicForm} from './Renderer';
import {Modal} from './Management';

export function Home({user,projects,project,forms,versions,interviews,setPage,setProjectId}){
  const recent=[...projects].slice(-4).reverse();
  const open=survey=>{setProjectId(survey.id);setPage('Questions');};
  return <>
    <section className="welcome simple-welcome"><div><span className="badge">SURVEYS MADE SIMPLE</span><h2>Ask better questions.<br/>Understand your answers.</h2><p>Welcome, {user.name.split(' ')[0]}. Create a survey, share a link, and turn responses into clear charts and averages.</p><div className="toolbar"><button className="primary" onClick={()=>setPage('My Surveys')}>+ Create a survey</button>{project&&<button onClick={()=>setPage('Questions')}>Continue “{project.name}” →</button>}</div></div><div className="welcome-art" aria-hidden="true"><div>◫</div><span>Build · Share · Understand</span></div></section>
    <div className="stats">{[['Surveys',projects.length,'surveys in your account'],['Responses',interviews.length,'in the selected survey'],['Questionnaires',forms.length,'in the selected survey'],['Published',versions.length,'versions ready to share']].map(([label,n,note])=><article className="card" key={label}><small>{label}</small><strong>{n}</strong><span>{note}</span></article>)}</div>
    <div className="grid"><article className="card"><p className="eyebrow">THREE SIMPLE STEPS</p><h2>From idea to results</h2><ol><li><strong>Write or paste your questions.</strong> Start from scratch or paste a list from Word or Docs.</li><li><strong>Publish and share a link.</strong> Anyone can answer without creating an account.</li><li><strong>See charts and averages.</strong> Open Results to understand the data instantly.</li></ol><div className="toolbar"><button onClick={()=>setPage('My Surveys')}>My surveys →</button>{project&&<button onClick={()=>setPage('Results')}>See results →</button>}</div></article>
      <article className="card"><p className="eyebrow">YOUR SURVEYS</p><h2>Pick up where you left off</h2>{recent.length?<div className="recent-list">{recent.map(survey=><button className="recent-survey" key={survey.id} onClick={()=>open(survey)}><span><strong>{survey.name}</strong><small>{survey.description||'No description yet'}</small></span><span>→</span></button>)}</div>:<p>No surveys yet. Create your first one in under a minute.</p>}<button onClick={()=>setPage('My Surveys')}>View all surveys →</button></article></div>
  </>;
}

function BaseFilters({project,forms,versions,options,setOptions,questions=true}){
  const set=(key,value)=>setOptions({...options,[key]:value});
  const selectedVersions=versions.filter(v=>(!options.form_ids?.length||options.form_ids.includes(v.form_id))&&(!options.version_ids?.length||options.version_ids.includes(v.id)));
  const qs=[...new Map(selectedVersions.flatMap(v=>allQuestions(v.schema)).map(q=>[q.id,q])).values()].filter(q=>options.include_identifiers||(!q.sensitive&&!['location','media'].includes(q.type)));
  return <><div className="grid filters"><label>Questionnaires (select one or more)<select multiple value={options.form_ids||[]} onChange={e=>setOptions({...options,form_ids:[...e.target.selectedOptions].map(o=>o.value),version_ids:[]})}>{forms.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select><small>No selection includes all questionnaires.</small></label><label>Versions<select multiple value={options.version_ids||[]} onChange={e=>set('version_ids',[...e.target.selectedOptions].map(o=>o.value))}>{versions.filter(v=>!options.form_ids?.length||options.form_ids.includes(v.form_id)).map(v=><option key={v.id} value={v.id}>{v.schema.form_name} · v{v.number}</option>)}</select><small>Version-qualified columns preserve original labels.</small></label><label>From (UTC)<input type="datetime-local" value={options.from?.slice(0,16)||''} onChange={e=>set('from',e.target.value?e.target.value+':00Z':'')}/></label><label>To (UTC)<input type="datetime-local" value={options.to?.slice(0,16)||''} onChange={e=>set('to',e.target.value?e.target.value+':59.999Z':'')}/></label><label>Location<select value={options.location||''} onChange={e=>set('location',e.target.value)}><option value="">All locations</option>{(project.config.locations||[]).map(l=><option key={l.id} value={l.id}>{l.label}</option>)}</select></label><label>Team member ID<input placeholder="All team members" value={options.researcher_id||''} onChange={e=>set('researcher_id',e.target.value)}/></label><label>Response status<select value={options.status||''} onChange={e=>set('status',e.target.value)}><option value="">Draft and completed</option><option value="completed">Completed</option><option value="draft">Draft</option></select></label></div>{questions&&<details><summary>Choose question fields ({options.question_ids?.length||'all'} selected)</summary><p>Clear all to include every authorized question.</p><div className="grid">{qs.map(q=><label key={q.id} className="check"><input type="checkbox" checked={(options.question_ids||[]).includes(q.id)} onChange={e=>set('question_ids',e.target.checked?[...(options.question_ids||[]),q.id]:(options.question_ids||[]).filter(id=>id!==q.id))}/>{q.label} <small>{q.type}</small></label>)}</div></details>}</>;
}

export function Filters(props){
  const {versions,options,setOptions}=props;
  const qs=[...new Map(versions.flatMap(v=>allQuestions(v.schema)).filter(q=>['text','single','multiple','boolean','number','currency','rating','date','time'].includes(q.type)&&(!q.sensitive||options.include_identifiers)).map(q=>[q.id,q])).values()];
  const rule=options.answer_filters?.[0];
  const setRule=r=>setOptions({...options,answer_filters:r?[r]:[]});
  const selected=qs.find(q=>q.id===rule?.question_id);
  return <><BaseFilters {...props}/><label>Collection source<select value={options.source||''} onChange={e=>setOptions({...options,source:e.target.value})}><option value="">All authorized responses</option><option value="researcher">Manual or team entry</option><option value="public_link">Public survey links</option></select></label><details><summary>Filter respondents by an answer</summary><div className="grid"><label>Question<select value={rule?.question_id||''} onChange={e=>setRule(e.target.value?{question_id:e.target.value,op:'equals',value:''}:null)}><option value="">No answer filter</option>{qs.map(q=><option key={q.id} value={q.id}>{q.label}</option>)}</select></label>{rule&&<><label>Comparison<select value={rule.op} onChange={e=>setRule({...rule,op:e.target.value,value:e.target.value==='state'?'missing':''})}>{['equals','state',...(selected?.type==='multiple'?['contains']:[]),...(['number','currency','rating'].includes(selected?.type)?['gt','lt']:[])].map(op=><option key={op}>{op}</option>)}</select></label><label>Value{rule.op==='state'?<select value={rule.value} onChange={e=>setRule({...rule,value:e.target.value})}>{['answered','missing','skipped','not_sure','prefer_not_to_answer'].map(s=><option key={s}>{s}</option>)}</select>:<input placeholder="Use choice codes for categorical answers" value={String(rule.value)} onChange={e=>setRule({...rule,value:conditionValue(selected,e.target.value)})}/>}</label></>}</div></details></>;
}

export function ExportPage({project,forms,versions,act,setNotice}){
  const [options,setOptions]=useState({format:'wide',status:'completed'}),[preview,setPreview]=useState(null);
  useEffect(()=>{setOptions({format:'wide',status:'completed'});setPreview(null);},[project.id]);
  const payload={...options,project_id:project.id};
  return <><div className="card"><div className="toolbar"><span className="step">1</span><h2>Select your data</h2><span className="grow"/><span className="badge">Personal identifiers excluded by default</span></div><Filters project={project} forms={forms} versions={versions} options={options} setOptions={o=>{setOptions(o);setPreview(null);}}/></div><div className="card"><div className="toolbar"><span className="step">2</span><h2>Shape your export</h2></div><div className="grid"><label>CSV structure<select value={options.format} onChange={e=>{setOptions({...options,format:e.target.value});setPreview(null);}}><option value="wide">Wide · one row per response</option><option value="long">Long · one row per question response</option><option value="raw">Raw · typed original answer JSON</option><option value="analysis">Analysis-ready · coded answers and state columns</option></select></label><label>Delimiter<select value={options.delimiter||','} onChange={e=>setOptions({...options,delimiter:e.target.value})}><option value=",">Comma</option><option value=";">Semicolon</option><option value={'\t'}>Tab</option></select></label></div><label className="check"><input type="checkbox" checked={!!options.original} onChange={e=>setOptions({...options,original:e.target.checked})}/>Use immutable original submissions instead of latest corrections</label>{project.access.identifiable&&<label className="check"><input type="checkbox" checked={!!options.include_identifiers} onChange={e=>{setOptions({...options,include_identifiers:e.target.checked});setPreview(null);}}/>Include protected fields, attachment references, respondent and team member IDs</label>}<p className="muted">UTF-8 · ISO 8601 timestamps · escaped commas, quotes and line breaks · spreadsheet formula protection</p><button onClick={()=>act(async()=>setPreview(await api('/exports/preview',payload)))}>Preview columns & record count</button></div>
    {preview&&<div className="card"><div className="toolbar"><span className="step">3</span><h2>Review & download</h2><span className="grow"/><strong>{preview.record_count} response{preview.record_count===1?'':'s'}</strong></div><p>{preview.columns.length} columns. Long and raw exports may contain multiple rows per response.</p><div className="column-preview">{preview.columns.map(c=><code key={c}>{c}</code>)}</div><p>{preview.multiple_choice_encoding}</p><p>{preview.missing_encoding}</p><div className="toolbar"><button className="primary" onClick={()=>act(async()=>{const result=await download('/exports/csv',payload,`survey-${options.format}.csv`);setNotice(`Exported ${result.count} responses at ${result.at}. Export recorded in the audit trail.`);})}>↓ Download CSV</button><button onClick={()=>act(()=>download('/exports/dictionary',payload,'survey-data-dictionary.csv'))}>↓ Download data dictionary</button></div></div>}
    <div className="card"><h3>Metadata & de-identification</h3><label className="check"><input type="checkbox" checked={!!options.anonymize} onChange={e=>{setOptions({...options,anonymize:e.target.checked,include_identifiers:false});setPreview(null);}}/>Use per-export response pseudonyms and omit location, collection timestamps, and correction IDs</label><p>Protected questions remain excluded. Classify any identifying free text as protected in the question editor.</p><p>Survey, response pseudonym or ID, version, and export timestamp are always included.</p><div className="grid">{['status','location','created_at','updated_at','correction_id'].map(field=><label key={field} className="check"><input type="checkbox" disabled={options.anonymize&&field!=='status'} checked={(options.metadata_fields||['status','location','created_at','updated_at','correction_id']).includes(field)} onChange={e=>{const fields=options.metadata_fields||['status','location','created_at','updated_at','correction_id'];setOptions({...options,metadata_fields:e.target.checked?[...fields,field]:fields.filter(f=>f!==field)});setPreview(null);}}/>{field.replaceAll('_',' ')}</label>)}</div></div>
    <div className="card"><h3>Export record counts & metadata</h3><p>The manifest for your last CSV download contains its exact interview count, export timestamp, resolved versions, columns, and filters.</p><button onClick={()=>act(downloadManifest)}>↓ Save last export manifest</button></div>
    <div className="note"><strong>About CSV files</strong><p>Images and recordings are represented by attachment UUIDs, never embedded in cells. Authorized attachments can be downloaded separately. Raw exports store answer objects as JSON to preserve types. Spreadsheet-safe text may receive an apostrophe prefix. For exact values use the raw JSON encoding. Preview counts can change before download; the download count uses a consistent database snapshot.</p></div></>;
}

const chartColors=['#146b60','#4f8f7d','#7fb5a0','#a9cdbb','#d4e5da','#d9a441','#c97b4a','#8b7cc8'];
const number=value=>value===null||value===undefined?'—':Number(value).toLocaleString(undefined,{maximumFractionDigits:2});

function Metric({label,value}){return <div className="metric"><small>{label}</small><strong>{value}</strong></div>;}

function Timeline({data}){
  if(!data?.length)return <p className="muted">Responses will appear here over time.</p>;
  const width=720,height=190,pad=28,max=Math.max(...data.map(item=>item.count),1);
  const step=data.length>1?(width-pad*2)/(data.length-1):0;
  const points=data.map((item,index)=>[data.length>1?pad+index*step:width/2,height-pad-(item.count/max)*(height-pad*2)]);
  const line=points.map(([x,y],index)=>(index?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)).join(' ');
  const area=`M${points[0][0].toFixed(1)} ${height-pad} ${line.replace(/^M/,'L')} L${points.at(-1)[0].toFixed(1)} ${height-pad} Z`;
  return <div className="timeline-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Responses over time">
    {[0,.5,1].map(part=>{const y=pad+part*(height-pad*2);return <g key={part}><line x1={pad} x2={width-pad} y1={y} y2={y} className="chart-grid"/><text x={pad-6} y={y+4} textAnchor="end" className="chart-axis">{Math.round(max*(1-part))}</text></g>;})}
    <path d={area} className="chart-area"/><path d={line} className="chart-line"/>
    {points.map(([x,y],index)=><circle key={index} cx={x} cy={y} r="5" className="chart-dot"><title>{data[index].date}: {data[index].count} response{data[index].count===1?'':'s'}</title></circle>)}
    <text x={pad} y={height-4} className="chart-axis">{data[0].date}</text><text x={width-pad} y={height-4} textAnchor="end" className="chart-axis">{data.at(-1).date}</text>
  </svg></div>;
}

function CategoryChart({categories,labels,total,donut=false,multiple=false}){
  const entries=Object.entries(categories);
  if(!entries.length)return <p className="muted">No answers yet.</p>;
  const max=Math.max(...entries.map(([,count])=>count),1);
  const stops=[];let position=0;
  entries.forEach(([,count],index)=>{const size=total?count/total*100:0;stops.push(`${chartColors[index%chartColors.length]} ${position}% ${position+size}%`);position+=size;});
  return <div className={donut?'chart-with-donut':''}>
    {donut&&<div className="donut" style={{background:`conic-gradient(${stops.join(',')})`}}><span><strong>{total}</strong><small>answers</small></span></div>}
    <div className="chart-bars">{entries.map(([code,count],index)=><div className="chart-row" key={code}><span className="chart-label">{labels[code]||code}</span><div className="chart-track"><span style={{width:`${count/max*100}%`,background:chartColors[index%chartColors.length]}}/></div><strong>{count}{multiple?'':` · ${total?(count/total*100).toFixed(0):0}%`}</strong></div>)}</div>
    {multiple&&<small>Respondents could choose more than one answer, so shares can add up to more than 100%.</small>}
  </div>;
}

function Histogram({bins}){
  if(!bins?.length)return null;
  const max=Math.max(...bins.map(bin=>bin.count),1);
  return <div className="histogram">{bins.map(bin=><div className="histogram-bin" key={bin.label} title={`${bin.label}: ${bin.count}`}><strong>{bin.count}</strong><div className="histogram-bar-wrap"><span style={{height:`${bin.count/max*100}%`}}/></div><small>{bin.label}</small></div>)}</div>;
}

function LiveResponses({project}){
  const url=__NEON_REALTIME_URL__;
  const [count,setCount]=useState(null),[status,setStatus]=useState('connecting');
  useEffect(()=>{
    if(!url)return undefined;
    let closed=false,client,subscription,renewing=false;
    const connect=async()=>{
      try{
        const sealed=await api(`/projects/${project.id}/live`);
        if(closed)return;
        if(!client)client=createRealtimeClient({url});
        if(subscription){
          subscription.renew(sealed);
          return;
        }
        subscription=client.subscribe(sealed);
        subscription.onChange(({data,status:next,error})=>{
          if(closed)return;
          if(error){setStatus('error');return;}
          setStatus(next);
          if(data?.length){
            const row=data.find(item=>item.project_id===project.id)||data[0];
            setCount(Number(row.response_count)||0);
          }else setCount(0);
          if(next==='stale'&&!renewing){
            renewing=true;
            connect().finally(()=>{renewing=false;});
          }
        });
      }catch{
        if(!closed)setStatus('unavailable');
      }
    };
    connect();
    return ()=>{closed=true;subscription?.unsubscribe();client?.close();};
  },[project.id,url]);
  if(!url)return null;
  return <article className="card"><small>Live responses</small><strong>{count===null?'—':count}</strong><span>{status==='live'?'Updating in real time':status==='connecting'?'Connecting…':status==='stale'?'Refreshing…':'Live count unavailable'}</span></article>;
}

export function Analytics({project,forms,versions,act}){
  const [options,setOptions]=useState({status:'completed'}),[rows,setRows]=useState(null),[overview,setOverview]=useState(null),[group,setGroup]=useState(false);
  const load=async body=>{const [analysis,summary]=await Promise.all([api(`/projects/${project.id}/analytics`,body),api(`/projects/${project.id}/analytics-overview`,body)]);setRows(analysis);setOverview(summary);};
  useEffect(()=>{setRows(null);setOverview(null);setOptions({status:'completed'});setGroup(false);act(()=>load({status:'completed'}));},[project.id]);
  const set=(key,value)=>setOptions(current=>({...current,[key]:value}));
  const labelsFor=row=>{const q=versions.find(v=>v.id===row.version_id)?.schema?.sections?.flatMap(s=>s.questions).find(question=>question.id===row.question_id);return q?.type==='boolean'?{true:'Yes',false:'No'}:Object.fromEntries((q?.choices||[]).map(choice=>[choice.code,choice.label]));};
  const summary=async()=>{if(!rows)return;const cell=value=>{const text=String(value??'');return /^\s*[=+\-@]/.test(text)?`'${text}`:`"${text.replaceAll('"','""')}"`;};const header=['question','type','version','group','answered','total','average','median','mode','minimum','maximum','standard_deviation','answers'];const lines=[header,...rows.map(row=>[row.label,row.type,versions.find(v=>v.id===row.version_id)?.number??'',row.group,row.answered,row.total,row.mean,row.median,row.mode,row.min,row.max,row.stdev,JSON.stringify(row.categories)])];const blob=new Blob(['\ufeff'+lines.map(line=>line.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});await saveBlob(blob,'survey-results-summary.csv');};
  return <>
    <div className="card"><div className="toolbar"><div className="grow"><h2>Results</h2><p>Choose what to include, then explore charts, averages, and written-answer counts.</p></div></div>
      <div className="grid results-filters">
        <label>Questionnaire<select value={options.form_ids?.[0]||''} onChange={event=>setOptions({...options,form_ids:event.target.value?[event.target.value]:[],version_ids:[]})}><option value="">All questionnaires</option>{forms.map(form=><option key={form.id} value={form.id}>{form.name}</option>)}</select></label>
        <label>Show responses<select value={options.status??''} onChange={event=>set('status',event.target.value)}><option value="completed">Completed</option><option value="">All responses</option><option value="draft">Drafts</option></select></label>
        <label>From<input type="datetime-local" value={options.from?.slice(0,16)||''} onChange={event=>set('from',event.target.value?event.target.value+':00Z':'')}/></label>
        <label>To<input type="datetime-local" value={options.to?.slice(0,16)||''} onChange={event=>set('to',event.target.value?event.target.value+':59.999Z':'')}/></label>
        <label>Location<select value={options.location||''} onChange={event=>set('location',event.target.value)}><option value="">All locations</option>{(project.config.locations||[]).map(location=><option key={location.id} value={location.id}>{location.label}</option>)}</select></label>
        <label>Collected through<select value={options.source||''} onChange={event=>set('source',event.target.value)}><option value="">All sources</option><option value="researcher">Manual entry</option><option value="public_link">Shared link</option></select></label>
      </div>
      <label className="check"><input type="checkbox" checked={group} onChange={event=>setGroup(event.target.checked)}/>Compare results by location</label>
      <div className="toolbar"><button className="primary" onClick={()=>act(()=>load({...options,group_by_location:group}))}>Show results</button><span className="grow"/>{rows&&<><button onClick={()=>act(summary)}>↓ Summary CSV</button><button onClick={()=>window.print()}>Print / save PDF</button></>}</div>
    </div>
    {overview&&<><div className="stats results-stats">{[['Total responses',overview.total],['Completed',overview.completed],['Drafts',overview.draft],['Days collecting',overview.timeline.length]].map(([label,value])=><article className="card" key={label}><small>{label}</small><strong>{value}</strong></article>)}<LiveResponses project={project}/></div><div className="card"><div className="toolbar"><h2 className="grow">Responses over time</h2><span className="badge">{overview.total} total</span></div><Timeline data={overview.timeline}/></div></>}
    {rows&&rows.length===0&&<div className="empty">No responses match these choices yet. Try choosing “All responses” or removing a filter.</div>}
    {rows&&rows.map(row=>{const version=versions.find(item=>item.id===row.version_id);const categorical=['single','multiple','boolean'].includes(row.type);const numeric=['number','currency','rating'].includes(row.type);const states=Object.entries(row.states).filter(([state])=>state!=='answered');
      return <article className="card result-card" key={row.version_id+row.question_id+row.group}>
        <div className="toolbar"><span className="badge">{row.type}</span><small>{version?`Version ${version.number}`:'Questionnaire version'}{row.group!=='all'?` · ${row.group?(project.config.locations||[]).find(item=>item.id===row.group)?.label||'Location':'No location'}`:''}</small><span className="grow"/><strong>{row.answered} of {row.total}</strong></div>
        <h2>{row.label}</h2>
        <p>{row.answered?`${row.answered} response${row.answered===1?'':'s'} answered this question.`:'No one has answered this question yet.'}</p>
        {numeric&&<div className="metrics"><Metric label="Average" value={number(row.mean)}/><Metric label="Median" value={number(row.median)}/><Metric label="Most common" value={number(row.mode)}/><Metric label="Range" value={`${number(row.min)} – ${number(row.max)}`}/><Metric label="Std. deviation" value={number(row.stdev)}/></div>}
        {numeric&&<Histogram bins={row.histogram}/>}
        {categorical&&<CategoryChart categories={row.categories} labels={labelsFor(row)} total={row.answered} donut={row.type!=='multiple'} multiple={row.type==='multiple'}/>}
        {!numeric&&!categorical&&<p className="muted">Open Responses to read the individual answers, or download the data from Export.</p>}
        {states.length>0&&<div className="state-list">{states.map(([state,count])=><span key={state}>{state.replaceAll('_',' ')}: {count}</span>)}</div>}
      </article>;
    })}
  </>;
}

export function Interviews({project,versions,interviews,setInterviews,act,reloadData,setNotice}){
  const [editing,setEditing]=useState(null),[errors,setErrors]=useState(false),[reason,setReason]=useState(''),[versionId,setVersionId]=useState(''),[history,setHistory]=useState(null);
  const version=versions.find(v=>v.id===editing?.version_id), schema=version?.schema;
  const open=row=>{setErrors(false);setReason('');setEditing({...row,answers:structuredClone(row.corrections?.at(-1)?.answers||row.answers),consent:!!row.consent,location_consent:!!row.location_consent});};
  const save=async(status,close=true)=>{
    const answers=normalize(schema,editing.answers);
    if(status==='completed'){
      setErrors(true);
      for(const q of allQuestions(schema))if(isVisible(q,answers)&&(!q.sensitive||project.access.identifiable)&&validate(q,answers[q.id]))throw new Error(`${q.label}: ${validate(q,answers[q.id])}`);
      if(!editing.consent)throw new Error('Record informed consent before completion.');
    }
    let result;
    if(editing.status==='completed') result=await api(`/interviews/${editing.id}/corrections`,{answers,reason,base_correction_id:editing.corrections?.at(-1)?.id||null});
    else result=await api('/interviews',{event_id:uuid(),id:editing.id,version_id:editing.version_id,revision:editing.revision,status,answers,consent:editing.consent,location_consent:editing.location_consent,location:editing.location,created_at:editing.created_at});
    if(close){setEditing(null);await reloadData();setNotice(editing.status==='completed'?'Correction recorded; original submission preserved.':'Interview saved.');}
    else setEditing({...editing,revision:result.revision,answers});
    return result;
  };
  const attach=async(q,file)=>{const limit=import.meta.env.MODE==='hosted'?2:10;if(file.size>limit*1024*1024)throw new Error(`Maximum attachment size is ${limit} MiB.`);let revision=editing.revision;if(!revision){const saved=await save('draft',false);revision=saved.revision;}const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});const id=uuid();await api(`/interviews/${editing.id}/attachments`,{id,question_id:q.id,filename:file.name,mime:file.type,content});setEditing({...editing,revision,answers:{...editing.answers,[q.id]:{state:'answered',value:[...(editing.answers[q.id]?.value||[]),id]}}});};
  return <><div className="card toolbar"><label className="grow">Survey version<select value={versionId} onChange={e=>setVersionId(e.target.value)}><option value="">Select a version to add a response</option>{versions.map(v=><option key={v.id} value={v.id}>{v.schema.form_name} · v{v.number}</option>)}</select></label><button disabled={!versionId||!!project.archived||project.access.role==='viewer'} className="primary" onClick={()=>open({id:uuid(),version_id:versionId,status:'draft',answers:defaults(versions.find(v=>v.id===versionId).schema),consent:false,created_at:new Date().toISOString()})}>+ Add response</button></div>
    <div className="card"><table>
      <thead><tr><th>Response</th><th>Questionnaire</th><th>Source</th><th>Status</th><th>Collected</th><th/></tr></thead>
      <tbody>{interviews.map(i=><tr key={i.id}>
        <td><code>{i.id.slice(0,8)}</code><small>{i.location||'No location'}</small></td>
        <td>{versions.find(v=>v.id===i.version_id)?.schema.form_name}<small>v{versions.find(v=>v.id===i.version_id)?.number}</small></td>
        <td>{i.source==='public_link'?'Public link':'Manual entry'}</td>
        <td><span className="badge">{i.status}</span>{i.corrections.length>0&&<small>{i.corrections.length} corrections</small>}</td>
        <td>{new Date(i.created_at).toLocaleString()}</td>
        <td><div className="toolbar"><button onClick={()=>open(i)}>Review / {i.status==='draft'?'resume':'correct'}</button><button onClick={()=>setHistory(i)}>History</button></div></td>
      </tr>)}</tbody>
    </table>{!interviews.length&&<p className="empty">No responses yet. Add one here, share the survey link, or synchronize from Android.</p>}
    <button onClick={()=>act(async()=>{const more=await api(`/projects/${project.id}/interviews?after=${interviews.at(-1)?.id||''}`);setInterviews([...interviews,...more]);setNotice(`Loaded ${more.length} more responses.`);})}>Load more responses</button></div>
    {editing&&schema&&<Modal title={editing.status==='completed'?'Review or correct response':'Add a response'} onClose={()=>setEditing(null)}><p>{schema.form_name} · published version {version.number}</p><div className="note">{schema.consent||'Record voluntary informed consent before completion.'}</div><label className="check"><input type="checkbox" disabled={editing.status==='completed'} checked={!!editing.consent} onChange={e=>setEditing({...editing,consent:e.target.checked})}/>Respondent gave informed consent</label><label className="check"><input type="checkbox" disabled={editing.status==='completed'} checked={!!editing.location_consent} onChange={e=>setEditing({...editing,location_consent:e.target.checked})}/>Respondent explicitly consented to coordinate capture</label><label>Research location<select value={editing.location||''} disabled={editing.status==='completed'} onChange={e=>setEditing({...editing,location:e.target.value})}><option value="">No location</option>{(project.config.locations||[]).map(l=><option key={l.id} value={l.id}>{l.label}</option>)}</select></label><DynamicForm schema={schema} answers={editing.answers} onChange={answers=>setEditing({...editing,answers})} allowPrivate={project.access.identifiable} locationConsent={editing.location_consent} showErrors={errors} readOnly={project.access.role==='viewer'} onFile={editing.status==='draft'?((q,file)=>act(()=>attach(q,file))):undefined}/>{editing.status==='completed'&&      <label>Reason for correction<textarea value={reason} onChange={e=>setReason(e.target.value)}/></label>}{project.access.role!=='viewer'&&<div className="toolbar">{editing.status==='draft'&&<button onClick={()=>act(()=>save('draft'))}>Save draft</button>}<button className="primary" onClick={()=>act(()=>save('completed'))}>{editing.status==='completed'?'Save correction':'Save completed response'}</button></div>}</Modal>}
    {history&&<Modal title="Response and correction history" onClose={()=>setHistory(null)}><h3>Original submission · {history.created_at}</h3><pre>{JSON.stringify(history.answers,null,2)}</pre>{history.corrections.map(c=><div className="card" key={c.id}><strong>{c.created_at}</strong><p>{c.reason}</p><pre>{JSON.stringify(c.answers,null,2)}</pre></div>)}</Modal>}
  </>;
}

export function Respondents({project,act}){
  const [rows,setRows]=useState([]),[editing,setEditing]=useState(false),[answers,setAnswers]=useState({});
  const load=async()=>setRows(await api(`/projects/${project.id}/respondents`));
  useEffect(()=>{setRows([]);if(project.access.identifiable)act(load);},[project.id,project.access.identifiable]);
  if(!project.access.identifiable)return <div className="empty">Identifiable-data permission is required for respondent profiles.</div>;
  const schema=project.config.fields;
  return <><div className="toolbar"><p className="grow">Respondent fields are configured per project in Settings.</p><button className="primary" disabled={!schema} onClick={()=>{setAnswers(defaults(schema));setEditing(true);}}>+ Add respondent</button></div><div className="card">{rows.map(r=><details key={r.id}><summary>{r.id} · {r.created_at}</summary>{allQuestions(r.data.schema).map(q=><p key={q.id}><strong>{q.label}:</strong> {JSON.stringify(r.data.answers[q.id])}</p>)}</details>)}{!rows.length&&<p className="empty">No authorized respondent profiles.</p>}</div>{editing&&<Modal title="Create respondent profile" onClose={()=>setEditing(false)}><DynamicForm schema={schema} answers={answers} onChange={setAnswers}/><button className="primary" onClick={()=>act(async()=>{await api(`/projects/${project.id}/respondents`,{id:uuid(),data:normalize(schema,answers)});setEditing(false);await load();})}>Save profile</button></Modal>}</>;
}

export function Synchronization({project,manager,act}){
  const [audits,setAudits]=useState([]);
  useEffect(()=>{setAudits([]);if(manager)act(async()=>setAudits(await api(`/projects/${project.id}/audits`)));},[project.id]);
  return <><div className="card"><h2>Offline collection & synchronization</h2><p>In the Android app, sign in and download published surveys. Drafts autosave on the device and remain available offline. Open Sync when connected to upload completed responses.</p><p>Sync events carry stable UUIDs. Retrying an event cannot create duplicate submissions. Revision conflicts require review and never overwrite completed responses.</p><div className="note">A local CSV export is a separate copy of local data. It does not upload responses or mark them as synchronized.</div></div>{manager&&<div className="card"><h2>Server export audit trail</h2><table><thead><tr><th>Exported at</th><th>Actor UUID</th><th>Response count</th><th>State</th></tr></thead><tbody>{audits.map(a=><tr key={a.id}><td>{a.created_at}</td><td><code>{a.actor_id}</code></td><td>{a.record_count}</td><td>{a.state}</td></tr>)}</tbody></table></div>}</>;
}
