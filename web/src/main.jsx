import React, {useCallback,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api,setToken} from './api';
import {Projects,Questionnaires,Builder,Share,Settings as SurveySettings,Researchers} from './Management';
import {Home,Interviews,Analytics,ExportPage,Synchronization} from './Research';
import {PublicSurvey} from './PublicSurvey';
import './style.css';

const navigation=[
  {id:'Home',icon:'◫'},
  {id:'My Surveys',icon:'▤'},
  {id:'Questions',icon:'✎'},
  {id:'Share',icon:'↗'},
  {id:'Responses',icon:'☷'},
  {id:'Results',icon:'▥'},
  {id:'Settings',icon:'⚙'},
];
const activeNav=page=>({Builder:'Questions',Researchers:'Settings',Synchronization:'Settings','Export Data':'Settings'}[page]||page);
const surveyOnly=new Set(['Questions','Builder','Share','Responses','Results','Researchers','Synchronization','Export Data']);
const headings={
  Home:['Home','Create, share, and understand surveys without the busywork.'],
  'My Surveys':['My Surveys','Every survey you own or help with.'],
  Questions:['Questions','Write questions or paste a list from Word, Docs, or a message.'],
  Builder:['Questions','Design the questions people will answer.'],
  Share:['Share','Publish a version and invite people with a link.'],
  Responses:['Responses','Every answer, in one place.'],
  Results:['Results','Charts, averages, and clear summaries of your collected data.'],
  Settings:['Settings','Your account and survey preferences.'],
  Researchers:['Team access','Invite people to help with this survey.'],
  Synchronization:['Offline sync','Bring responses collected on Android into this survey.'],
  'Export Data':['Download data','Download CSV files and a matching data dictionary.'],
};
const descriptions={
  Home:'Start with a question. Finish with a clear picture.',
  'My Surveys':'All your surveys in one simple list.',
  Questions:'Build your questionnaire one question at a time, or paste a whole list at once.',
  Share:'Anyone with a link can answer without creating an account.',
  Responses:'Review completed answers and drafts, or add a response yourself.',
  Results:'See totals, charts, averages, and other summaries automatically.',
  Settings:'Keep your account and survey details up to date.',
  Researchers:'Share your survey with teammates by email.',
  Synchronization:'Android responses sync safely without duplicates.',
  'Export Data':'Choose exactly what you need for further analysis.',
};

function SettingsPage({ctx}){
  const {user,project,setPage,onLogout}=ctx;
  return <>
    <div className="card"><div className="toolbar"><div className="grow"><h2>Your account</h2><p><strong>{user.name}</strong> · {user.email}</p><span className="badge">Workspace owner</span></div><button onClick={onLogout}>Sign out</button></div><p>You can create surveys immediately. Each survey is private to you unless you invite team members.</p></div>
    {project?<SurveySettings {...ctx}/>:<div className="empty">Select or create a survey to change its settings.</div>}
    {project&&<div className="card"><h2>Advanced tools</h2><p>These tools are optional. Most surveys only need questions, a share link, and Results.</p><div className="toolbar"><button onClick={()=>setPage('Researchers')}>Team access</button><button onClick={()=>setPage('Synchronization')}>Offline sync</button><button onClick={()=>setPage('Export Data')}>Download data</button></div></div>}
  </>;
}

function App(){
  const [user,setUser]=useState(null),[ready,setReady]=useState(false),[page,setPage]=useState('Home'),[projects,setProjects]=useState([]),[projectId,setProjectId]=useState(''),[forms,setForms]=useState([]),[versions,setVersions]=useState([]),[interviews,setInterviews]=useState([]),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[formId,setFormId]=useState('');
  const [authMode,setAuthMode]=useState('login');
  const act=useCallback(async fn=>{setBusy(true);setError('');try{return await fn();}catch(e){setError(e.message);return null;}finally{setBusy(false);}},[]);
  const reload=useCallback(async()=>{const list=await api('/projects');setProjects(list);if(!projectId&&list.length)setProjectId(list[0].id);},[projectId]);
  const activeProject=useRef(projectId);activeProject.current=projectId;
  const reloadData=useCallback(async()=>{if(!projectId)return;const [f,v,i]=await Promise.all(['forms','versions','interviews'].map(key=>api(`/projects/${projectId}/${key}`)));if(activeProject.current!==projectId)return;setForms(f);setVersions(v);setInterviews(i);},[projectId]);
  useEffect(()=>{api('/me').then(setUser).catch(()=>setToken('')).finally(()=>setReady(true));},[]);
  useEffect(()=>{if(user)act(reload);},[user,reload,act]);
  useEffect(()=>{setForms([]);setVersions([]);setInterviews([]);setFormId('');if(user&&projectId)act(reloadData);},[user,projectId,reloadData,act]);
  useEffect(()=>{if(user&&projectId&&page==='Responses')act(reloadData);},[page,user,projectId,reloadData,act]);
  const project=projects.find(p=>p.id===projectId);
  const logout=()=>act(async()=>{await api('/logout',{});setToken('');setUser(null);setProjects([]);setProjectId('');setPage('Home');setAuthMode('login');});
  const ctx={user,project,projects,forms,versions,interviews,setInterviews,act,reload,reloadData,setNotice,setPage,setProjectId,formId,setFormId,manager:project?.access.role==='manager',onLogout:logout};
  const authenticate=async event=>{
    event.preventDefault();
    const data=Object.fromEntries(new FormData(event.currentTarget));
    act(async()=>{
      const result=await api(authMode==='register'?'/register':'/login',data);
      setToken(result.token);setUser(result.user);setPage('Home');setNotice(authMode==='register'?'Your account is ready. Create your first survey.':'');
    });
  };
  if(!ready)return <main className="login"><h1>Student Survey Creator</h1><p>Opening your workspace…</p></main>;
  if(!user)return <main className="login">
    <div className="brand-mark">S</div><p className="eyebrow">STUDENT SURVEY &amp; QUESTIONNAIRE CREATOR</p>
    <h1>{authMode==='login'?'Welcome back.':'Create your account.'}</h1>
    <p>{authMode==='login'?'Sign in to build surveys, share links, and see results.':'Anyone can create an account. No approval is needed, and you can start a survey right away.'}</p>
    <form onSubmit={authenticate}>
      {authMode==='register'&&<label>Your name<input name="name" required autoComplete="name"/></label>}
      <label>Email<input type="email" name="email" required autoComplete="username"/></label>
      <label>Password<input type="password" name="password" required minLength={8} autoComplete={authMode==='login'?'current-password':'new-password'}/></label>
      {authMode==='register'&&<small>Use at least 8 characters.</small>}
      <button className="primary" disabled={busy}>{busy?'Please wait…':authMode==='login'?'Sign in →':'Create my account →'}</button>
    </form>
    {error&&<p role="alert" className="error">{error}</p>}
    <button type="button" className="switch-auth" onClick={()=>{setAuthMode(authMode==='login'?'register':'login');setError('');}}>{authMode==='login'?'New here? Create a free account':'Already have an account? Sign in'}</button>
  </main>;
  const nav=activeNav(page), [heading,subheading]=headings[page]||[nav,''];
  const body=page==='Home'?<Home {...{user,projects,project,forms,versions,interviews,setPage,setProjectId}}/>
    :page==='My Surveys'?<Projects {...ctx}/>
    :page==='Settings'?<SettingsPage ctx={ctx}/>
    :page==='Researchers'?<><div className="toolbar"><button onClick={()=>setPage('Settings')}>← Back to Settings</button></div><Researchers {...ctx}/></>
    :page==='Synchronization'?<><div className="toolbar"><button onClick={()=>setPage('Settings')}>← Back to Settings</button></div><Synchronization {...ctx}/></>
    :page==='Export Data'?<><div className="toolbar"><button onClick={()=>setPage('Settings')}>← Back to Settings</button><button onClick={()=>setPage('Results')}>View results</button></div><ExportPage {...ctx}/></>
    :!project?<div className="empty"><h2>{projects.length?'Choose a survey':'Create your first survey'}</h2><p>{projects.length?'Pick a survey from the list or select one in the top bar.':'A survey takes less than a minute to start.'}</p><button className="primary" onClick={()=>setPage('My Surveys')}>{projects.length?'Choose a survey →':'Create a survey →'}</button></div>
    :page==='Questions'?<Questionnaires {...ctx}/>
    :page==='Builder'?<Builder {...ctx}/>
    :page==='Share'?<Share {...ctx}/>
    :page==='Responses'?<Interviews {...ctx}/>
    :page==='Results'?<Analytics {...ctx}/>
    :null;
  return <div className="shell"><aside><a className="brand" href="#" onClick={e=>{e.preventDefault();setPage('Home');}}><span className="brand-mark">S</span><span>SURVEY<small>STUDENT SURVEYS &amp; QUESTIONNAIRES</small></span></a><p className="nav-label">WORKSPACE</p><nav aria-label="Main navigation">{navigation.map(item=><button className={nav===item.id?'active':''} key={item.id} onClick={()=>{setPage(item.id);setError('');setNotice('');}}><span className="nav-icon">{item.icon}</span>{item.id}</button>)}</nav><div className="sidebar-footer"><strong>{user.name}</strong><small>Workspace owner</small><button onClick={logout}>Sign out</button></div></aside>
    <div className="workspace"><header><span>Workspace / <strong>{nav}</strong></span>{projects.length>0&&<label className="project-select"><span>Current survey</span><select aria-label="Current survey" value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">Select a survey</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}{p.archived?' · archived':''}</option>)}</select></label>}</header><main><div className="page-heading"><div><p className="eyebrow">STUDENT SURVEY CREATOR</p><h1>{heading}</h1><p>{subheading||descriptions[page]||''}</p></div><span className="badge">{busy?'Working…':project?.archived?'Archived survey':'Survey workspace'}</span></div>
      {error&&<div className="error banner" role="alert">{error}<button onClick={()=>setError('')}>Dismiss</button></div>}{notice&&<div className="success banner" role="status">{notice}<button onClick={()=>setNotice('')}>Dismiss</button></div>}
      {body}
    </main><footer>Student Survey &amp; Questionnaire Creator System <span>Build · Share · Understand</span></footer></div></div>;
}
const publicPath=window.location.pathname==='/survey'||window.location.pathname.startsWith('/survey/');
const publicToken=window.location.pathname.match(/^\/survey\/([A-Za-z0-9_-]+)\/?$/)?.[1]||'';
createRoot(document.getElementById('root')).render(publicPath?<PublicSurvey token={publicToken}/>:<App/>);
