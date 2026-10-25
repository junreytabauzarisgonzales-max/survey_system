import React, {useEffect, useState} from 'react';
import {api} from './api';

const surveyUrl = link => `${window.location.origin}/survey/${link.token}`;

function LinkCard({link, versions, update, act, setNotice}) {
  const [expires, setExpires] = useState(link.expires_at ? new Date(link.expires_at).toISOString().slice(0, 16) : '');
  useEffect(() => setExpires(link.expires_at ? new Date(link.expires_at).toISOString().slice(0, 16) : ''), [link]);
  const expired = link.expires_at && new Date(link.expires_at) <= new Date();
  const version = versions.find(v => v.id === link.version_id);
  return <article className="card public-link-card">
    <div className="toolbar"><strong className="grow">{link.name}</strong><span className="badge">{!link.enabled ? 'Disabled' : expired ? 'Expired' : 'Enabled'}</span></div>
    <p>{version?.schema.form_name} · version {version?.number} · no account needed</p>
    <label>Shareable link<input readOnly value={surveyUrl(link)} onFocus={e => e.target.select()}/></label>
    <div className="toolbar">
      <button onClick={() => act(async () => { await navigator.clipboard.writeText(surveyUrl(link)); setNotice('Share link copied.'); })}>Copy link</button>
      <a className="button-link" href={surveyUrl(link)} target="_blank" rel="noopener noreferrer">Open survey ↗</a>
      <button className={link.enabled ? 'danger' : ''} onClick={() => update(link, {enabled: !link.enabled})}>{link.enabled ? 'Disable link' : 'Enable link'}</button>
    </div>
    <div className="toolbar"><label className="grow">Expiration (UTC, optional)<input type="datetime-local" value={expires} onChange={e => setExpires(e.target.value)}/></label><button onClick={() => update(link, {expires_at: expires ? expires + ':00Z' : null})}>Update expiration</button></div>
    <small>Sharing stays on this version even after future edits. Archiving its survey or questionnaire also stops new responses.</small>
  </article>;
}

export function PublicLinks({project, versions, act, setNotice}) {
  const [links, setLinks] = useState([]), [versionId, setVersionId] = useState('');
  const [name, setName] = useState('Public survey'), [expires, setExpires] = useState('');
  useEffect(() => {
    let active = true;
    setLinks([]); setVersionId('');
    act(async () => { const rows = await api(`/projects/${project.id}/public-links`); if (active) setLinks(rows); });
    return () => { active = false; };
  }, [project.id, act]);
  const load = async () => setLinks(await api(`/projects/${project.id}/public-links`));
  const update = (link, changes) => act(async () => {
    await api(`/projects/${project.id}/public-links/${link.id}`, {...link, ...changes}, 'PUT');
    await load(); setNotice('Share link updated.');
  });
  return <section className="public-links" aria-label="Public survey links">
    <form className="card" onSubmit={e => {e.preventDefault(); act(async () => {
      await api(`/projects/${project.id}/public-links`, {name, version_id: versionId, expires_at: expires ? expires + ':00Z' : null});
      await load(); setNotice('Share link created. Copy it and send it to your respondents.');
    });}}>
      <span className="badge">NO ACCOUNT NEEDED</span><h2>Create a share link</h2>
      <p>Anyone with the link can read your consent message and submit answers without signing in. New responses appear in Responses and Results.</p>
      <div className="grid"><label>Published version to share<select required value={versionId} onChange={e => setVersionId(e.target.value)}><option value="">Select a published version</option>{versions.map(v => <option key={v.id} value={v.id}>{v.schema.form_name} · v{v.number}</option>)}</select></label><label>Link name<input required value={name} maxLength="300" onChange={e => setName(e.target.value)}/></label><label>Link expiration (UTC, optional)<input type="datetime-local" value={expires} onChange={e => setExpires(e.target.value)}/></label></div>
      <button className="primary" disabled={!versionId || project.archived}>Create link</button>
      <small className="sharing-help">Links use this website's address. Share a publicly hosted HTTPS address so respondents can open the link from their own devices.</small>
    </form>
    {links.map(link => <LinkCard key={link.id} {...{link, versions, update, act, setNotice}}/>)}
  </section>;
}
