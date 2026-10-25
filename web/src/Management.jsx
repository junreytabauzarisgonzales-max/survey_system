import React,{useEffect,useState} from 'react';
import {api} from './api';
import {allQuestions,blankSchema,uuid} from './core';
import {FormBuilder} from './FormBuilder';
import {PublicLinks} from './PublicLinks';

export function Modal({title,children,onClose}){return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label={title}><div className="toolbar"><h2 className="grow">{title}</h2><button onClick={onClose} aria-label="Close dialog">✕</button></div>{children}</section></div>;}

export function Projects({projects,user,act,reload,setProjectId,setPage,setFormId,setNotice}){
  const [editing,setEditing]=useState(null),[history,setHistory]=useState(null),[templates,setTemplates]=useState([]);
  const [deleting,setDeleting]=useState(null),[confirmation,setConfirmation]=useState('');
  const [name,setName]=useState(''),[description,setDescription]=useState('');
  useEffect(()=>{act(async()=>setTemplates(await api('/templates')));},[]);
  const create=async event=>{
    event.preventDefault();
    act(async()=>{
      const project=await api('/projects',{name,description,config:{}});
      const form=await api(`/projects/${project.id}/forms`,{name,draft:blankSchema()});
      setName('');setDescription('');
      await reload();
      setProjectId(project.id);setFormId(form.id);setPage('Builder');
      setNotice('Survey created. Add questions below, or paste a list from Word or Docs.');
    });
  };
  const closeDelete=()=>{setDeleting(null);setConfirmation('');};
  const remove=async event=>{
    event.preventDefault();
    const target=deleting;
    act(async()=>{
      await api(`/projects/${target.id}`,{confirm_name:confirmation},'DELETE');
      closeDelete();
      await reload();
      setProjectId(current=>current===target.id?'':current);
      setNotice(`Survey “${target.name}” deleted.`);
    });
  };
  return <>
    <form className="card create-survey" onSubmit={create}>
      <span className="badge">START A NEW SURVEY</span><h2>What do you want to ask?</h2>
      <div className="grid"><label>Survey title<input required value={name} onChange={event=>setName(event.target.value)} placeholder="e.g. Student learning experience"/></label><label>Short description (optional)<input value={description} onChange={event=>setDescription(event.target.value)} placeholder="A sentence about who this survey is for"/></label></div>
      <button className="primary">Create survey →</button>
    </form>
    <div className="toolbar"><h2 className="grow">My surveys <small>{projects.length}</small></h2></div>
    <div className="project-grid">{projects.map(p=><article className="card project-card" key={p.id}><span className="badge">{p.archived?'Archived':'Active'} · {p.access.role==='manager'?'Owner':'Team member'}</span><h2>{p.name}</h2><p>{p.description||'No description yet.'}</p><div className="toolbar"><button className="primary" onClick={()=>{setProjectId(p.id);setPage('Questions');}}>Open survey →</button></div>{p.access.role==='manager'&&<details><summary>Survey options</summary><div className="toolbar"><button onClick={()=>setEditing(structuredClone(p))}>Edit details</button><button onClick={()=>act(async()=>setHistory(await api(`/projects/${p.id}/history?kind=project&id=${p.id}`)))}>History</button><button onClick={()=>act(async()=>{await api(`/projects/${p.id}/duplicate`,{});await reload();setNotice('Survey duplicated with its questions.');})}>Duplicate</button><button onClick={()=>act(async()=>{await api(`/projects/${p.id}`,{...p,archived:!p.archived},'PUT');await reload();})}>{p.archived?'Reactivate':'Archive'}</button><button className="danger" onClick={()=>{setConfirmation('');setDeleting(p);}}>Delete survey</button></div></details>}</article>)}</div>
    {!projects.length&&<div className="empty">Create your first survey above. You can write questions by hand or paste a list.</div>}
    {templates.length>0&&<details className="card template-list"><summary>Or start from a ready-made template</summary><div className="grid">{templates.map(t=><article className="card" key={t.id}><span className="badge">STARTER TEMPLATE</span><h2>{t.name}</h2><p>{t.description}</p><button onClick={()=>act(async()=>{const p=await api(`/templates/${t.id}/apply`,{});await reload();setProjectId(p.id);setPage('Questions');setNotice('Template copied into your account. Review and edit before publishing.');})}>Use this template</button></article>)}</div></details>}
    {editing&&<Modal title="Edit survey details" onClose={()=>setEditing(null)}><form onSubmit={e=>{e.preventDefault();act(async()=>{await api(`/projects/${editing.id}`,editing,'PUT');setEditing(null);await reload();setNotice('Survey details saved.');});}}><label>Survey title<input required value={editing.name} onChange={e=>setEditing({...editing,name:e.target.value})}/></label><label>Short description<textarea value={editing.description} onChange={e=>setEditing({...editing,description:e.target.value})}/></label><button className="primary">Save changes</button></form></Modal>}
    {history&&<Modal title="Survey change history" onClose={()=>setHistory(null)}>{history.map(h=><article className="card" key={h.id}><strong>{h.created_at}</strong><p>{h.snapshot.name} · revision {h.snapshot.revision}</p></article>)}</Modal>}
    {deleting&&<Modal title="Delete survey" onClose={closeDelete}><form onSubmit={remove}><p>This permanently deletes <strong>{deleting.name}</strong>, including its questionnaires, published versions, share links, responses, attachments and team access. This cannot be undone.</p><label>Type the survey title to confirm<input required autoFocus value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><div className="toolbar"><button type="button" onClick={closeDelete}>Cancel</button><button className="danger" disabled={confirmation!==deleting.name}>Delete permanently</button></div></form></Modal>}
  </>;
}

export function Questionnaires({project,forms,versions,manager,act,reloadData,setFormId,setPage,setNotice}){
  const [name,setName]=useState('');
  return <>
    <div className="card"><div className="toolbar"><div className="grow"><h2>Questions</h2><p>Write your questions below, or open a questionnaire and use <strong>Paste questions</strong>. Public links are created after you publish a version.</p></div>{versions.length>0&&<button onClick={()=>setPage('Share')}>Share survey →</button>}</div>
      {manager&&<form className="toolbar" onSubmit={e=>{e.preventDefault();act(async()=>{const f=await api(`/projects/${project.id}/forms`,{name,draft:blankSchema()});setName('');await reloadData();setFormId(f.id);setPage('Builder');setNotice('Questionnaire created. Add or paste your questions.');});}}>
        <label className="grow">Add another questionnaire<input required value={name} onChange={e=>setName(e.target.value)} placeholder="Questionnaire name"/></label>
        <button>+ Create questionnaire</button>
      </form>}
      <table>
        <thead><tr><th>Questionnaire</th><th>Questions</th><th>Published versions</th><th>Actions</th></tr></thead>
        <tbody>{forms.map(f=><tr key={f.id}>
          <td><strong>{f.name}</strong><small>{f.archived?'Archived':'Draft revision '+f.revision}</small></td>
          <td>{allQuestions(f.draft).length}</td>
          <td>{versions.filter(v=>v.form_id===f.id).map(v=><span key={v.id} className="badge">v{v.number}</span>)}</td>
          <td><div className="toolbar">
            <button onClick={()=>{setFormId(f.id);setPage('Builder');}}>{manager?'Edit questions':'Preview'}</button>
            {manager&&<>
              <button onClick={()=>act(async()=>{await api(`/projects/${project.id}/forms`,{name:f.name+' (copy)',draft:f.draft});await reloadData();setNotice('Questionnaire duplicated as a draft.');})}>Duplicate</button>
              <button onClick={()=>act(async()=>{await api(`/projects/${project.id}/forms/${f.id}`,{...f,archived:!f.archived},'PUT');await reloadData();})}>{f.archived?'Reactivate':'Archive'}</button>
            </>}
          </div></td>
        </tr>)}</tbody>
      </table>{!forms.length&&<p className="empty">No questionnaire yet. Create one above to begin.</p>}
    </div>
  </>;
}

export function Share({project,versions,act,setPage,setNotice,manager}){
  return <>
    <div className="card"><div className="toolbar"><div className="grow"><h2>Share your survey</h2><p>A share link lets anyone answer without an account. Each link stays on the version you choose, so editing later never changes an invitation already sent.</p></div>{!versions.length&&manager&&<button className="primary" onClick={()=>setPage('Questions')}>Publish a version first →</button>}</div></div>
    {!manager?<div className="empty"><h2>Owner access required</h2><p>Ask the survey owner to create or change share links.</p></div>:versions.length>0?<PublicLinks {...{project,versions,act,setNotice}}/>:<div className="empty"><h2>Nothing to share yet</h2><p>Open Questions, add your questions, then publish a version. A share link can be created right after.</p><button className="primary" onClick={()=>setPage('Questions')}>Go to Questions →</button></div>}
    {versions.length>0&&<div className="card"><h2>Published versions</h2><table><thead><tr><th>Questionnaire</th><th>Version</th><th>Questions</th><th>Published</th></tr></thead><tbody>{versions.map(version=><tr key={version.id}><td>{version.schema.form_name}</td><td>v{version.number}</td><td>{allQuestions(version.schema).length}</td><td>{new Date(version.published_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
  </>;
}

export function Builder({project,forms,versions,formId,setFormId,manager,act,reloadData,setPage,setNotice}){
  const [draft,setDraft]=useState(null),[history,setHistory]=useState(null);
  useEffect(()=>{setDraft(structuredClone(forms.find(f=>f.id===formId)||null));},[forms,formId]);
  useEffect(()=>{if(!formId&&forms.length)setFormId(forms[0].id);},[forms,formId]);
  const save=async()=>{const f=await api(`/projects/${project.id}/forms/${draft.id}`,draft,'PUT');await reloadData();return f;};
  const published=versions.some(v=>v.form_id===draft?.id);
  return <><div className="card toolbar"><button onClick={()=>setPage('Questions')}>← All questionnaires</button><label className="grow">Questionnaire<select value={formId} onChange={e=>setFormId(e.target.value)}><option value="">Select questionnaire</option>{forms.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label>{draft&&manager&&<><button onClick={()=>act(async()=>setHistory(await api(`/projects/${project.id}/history?kind=form&id=${draft.id}`)))}>History</button><button onClick={()=>act(async()=>{await save();setNotice('Draft saved. Published versions remain unchanged.');})}>Save draft</button><button className="primary" onClick={()=>act(async()=>{const f=await save();const v=await api(`/forms/${f.id}/publish`,{revision:f.revision});await reloadData();setNotice(`Published version ${v.number}. Open Share to create a link.`);})}>Publish version →</button></>}{published&&<button onClick={()=>setPage('Share')}>Share →</button>}</div>
    {draft?<><label>Questionnaire title<input disabled={!manager} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label><fieldset disabled={!manager}><FormBuilder schema={draft.draft} onChange={schema=>setDraft({...draft,draft:schema})}/></fieldset><div className="card"><h3>Published versions</h3>{versions.filter(v=>v.form_id===draft.id).map(v=><details key={v.id}><summary>Version {v.number} · {v.published_at} · {allQuestions(v.schema).length} questions</summary><p>{v.id}</p><ul>{allQuestions(v.schema).map(q=><li key={q.id}>{q.label} — {q.type}</li>)}</ul></details>)}</div></>:<div className="empty">Select a questionnaire, or create one from Questions.</div>}
    {history&&<Modal title="Draft change history" onClose={()=>setHistory(null)}>{history.map(h=><div className="card" key={h.id}><strong>{h.created_at} · revision {h.snapshot.revision}</strong><p>{h.snapshot.name} · {allQuestions(h.snapshot.draft).length} questions</p></div>)}</Modal>}
  </>;
}

export function Settings({project,manager,act,reload,setNotice}){
  const [config,setConfig]=useState(structuredClone(project.config));
  useEffect(()=>setConfig(structuredClone(project.config)),[project]);
  const set=(k,v)=>setConfig({...config,[k]:v});
  return <><div className="card"><h2>Survey settings</h2><p>Changes are saved to the survey history. The consent message is captured when you publish a questionnaire.</p><fieldset disabled={!manager}><label>About this survey<textarea value={config.objectives||''} onChange={e=>set('objectives',e.target.value)}/></label><label>Consent message<textarea value={config.consent||''} onChange={e=>set('consent',e.target.value)}/></label><div className="grid">{['locations','categories'].map(key=><section key={key}><h3>{key==='locations'?'Locations (optional)':'Respondent categories (optional)'}</h3>{(config[key]||[]).map((item,index)=><div className="toolbar" key={item.id}><input aria-label={key+' label'} className="grow" value={item.label} onChange={e=>set(key,config[key].map((v,i)=>i===index?{...v,label:e.target.value}:v))}/><small>{item.id.slice(0,8)}</small><button onClick={()=>set(key,config[key].filter((_,i)=>i!==index))}>Remove</button></div>)}<button onClick={()=>set(key,[...(config[key]||[]),{id:uuid(),label:'New '+(key==='locations'?'location':'category')}])}>+ Add {key==='locations'?'location':'category'}</button></section>)}</div><label>Delete old responses after (days)<input type="number" min="1" max="36500" value={config.retention_days||3650} onChange={e=>set('retention_days',Number(e.target.value))}/></label><button className="primary" onClick={()=>act(async()=>{await api(`/projects/${project.id}`,{...project,config,archived:!!project.archived},'PUT');await reload();setNotice('Survey settings saved.');})}>Save survey settings</button></fieldset></div>
    <div className="card"><h2>Respondent profile fields (advanced)</h2><p>These fields are only available to team members with identifiable-data permission.</p><fieldset disabled={!manager}><FormBuilder schema={config.fields} onChange={s=>set('fields',s)}/></fieldset><p>Save survey settings above to apply these fields.</p></div>
    {manager&&<div className="card"><h2>Delete old responses</h2><p>This permanently deletes responses older than the saved retention period, including attachments and corrections. Create a backup first.</p><button className="danger" onClick={()=>{if(window.confirm('Permanently delete records outside the saved retention period?'))act(async()=>{const result=await api(`/projects/${project.id}/retention`,{confirm_project_id:project.id});setNotice(`Removed ${result.deleted_interviews} responses older than ${result.cutoff}.`);});}}>Delete responses outside the retention period</button></div>}
  </>;
}

export function Researchers({project,user,manager,act,setNotice}){
  const [members,setMembers]=useState([]),[member,setMember]=useState({user_id:'',email:'',role:'researcher',identifiable:false});
  const load=async()=>{if(manager)setMembers(await api(`/projects/${project.id}/members`));};
  useEffect(()=>{act(load);},[project.id]);
  if(!manager)return <div className="empty">Only the survey owner can manage the team.</div>;
  return <><div className="card"><h2>Team access</h2><p>Invite someone by the email they used to create their account.</p><table><thead><tr><th>Team member</th><th>Role</th><th>Identifiable data</th><th/></tr></thead><tbody>{members.map(m=><tr key={m.user_id}><td>{m.name}<small>{m.email}</small></td><td>{m.role}</td><td>{m.identifiable?'Allowed':'Restricted'}</td><td><button onClick={()=>setMember({user_id:m.user_id,email:m.email,role:m.role,identifiable:!!m.identifiable})}>Edit access</button></td></tr>)}</tbody></table><div className="grid"><label>Email address<input type="email" placeholder="person@example.com" value={member.email||''} onChange={e=>setMember({...member,user_id:'',email:e.target.value})}/></label><label>Role<select value={member.role} onChange={e=>setMember({...member,role:e.target.value})}>{['researcher','viewer','manager'].map(r=><option key={r}>{r}</option>)}</select></label><label className="check"><input type="checkbox" checked={member.identifiable} onChange={e=>setMember({...member,identifiable:e.target.checked})}/>May view identifiable information</label></div><button className="primary" onClick={()=>act(async()=>{await api(`/projects/${project.id}/members`,member,'PUT');setMember({user_id:'',email:'',role:'researcher',identifiable:false});await load();setNotice('Team access saved.');})}>Save team access</button></div>
    {!!user.admin&&<form className="card" onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const data=Object.fromEntries(new FormData(form));act(async()=>{await api('/users',data);form.reset();await load();setNotice('Account created. Add them by email above.');});}}><h2>Create a team account</h2><div className="grid"><label>Name<input name="name" required/></label><label>Email<input name="email" type="email" required/></label><label>Temporary password<input name="password" type="password" minLength="8" required autoComplete="new-password"/></label></div><button>Create account</button></form>}
  </>;
}
