import React, {useEffect, useRef, useState} from 'react';
import {allQuestions, defaults, isVisible, normalize, uuid, validate} from './core';
import {DynamicForm} from './Renderer';
import './public.css';

async function publicRequest(token, body) {
  const response = await fetch(`/api/public/surveys/${encodeURIComponent(token)}${body ? '/responses' : ''}`, {
    method: body ? 'POST' : 'GET', credentials: 'omit', cache: 'no-store',
    headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined,
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || 'The survey is unavailable.');
    error.status = response.status;
    throw error;
  }
  return result;
}

function receiptStorage(token, value) {
  try {
    const key = 'agal-public-receipt-' + token;
    if (value === undefined) return sessionStorage.getItem(key);
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch { /* The survey also works when browser storage is unavailable. */ }
  return null;
}

export function PublicSurvey({token}) {
  const [survey, setSurvey] = useState(null), [loading, setLoading] = useState(true);
  const [answers, setAnswers] = useState({}), [consent, setConsent] = useState(false);
  const [locationConsent, setLocationConsent] = useState(false), [location, setLocation] = useState('');
  const [files, setFiles] = useState([]), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [showErrors, setShowErrors] = useState(false);
  const [receipt, setReceipt] = useState(() => receiptStorage(token));
  const [attempt, setAttempt] = useState(0);
  const pending = useRef(null);
  const schema = survey?.schema;
  const locked = busy || pending.current !== null;

  useEffect(() => {
    let active = true;
    setLoading(true);
    if (receipt) { setLoading(false); return () => { active = false; }; }
    publicRequest(token).then(data => {
      if (!active) return;
      setSurvey(data); setAnswers(defaults(data.schema)); setError('');
    }).catch(e => { if (active) { setSurvey(null); setError(e.message); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, attempt, receipt]);

  async function attach(question, file) {
    setError('');
    if (file.size === 0 || file.size + files.reduce((n, f) => n + f.size, 0) > 10 * 1024 * 1024) {
      setError('Please choose files totaling no more than 10 MiB.'); return;
    }
    setBusy(true);
    try {
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = () => reject(new Error('The selected file could not be read.'));
        reader.readAsDataURL(file);
      });
      const id = uuid();
      setFiles(previous => [...previous, {id, question_id: question.id, filename: file.name, mime: file.type, content, size: file.size}]);
      setAnswers(previous => normalize(schema, {...previous, [question.id]: {state: 'answered', value: [...(previous[question.id]?.value || []), id]}}));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError(''); setShowErrors(true);
    if (!pending.current) {
      const effective = normalize(schema, answers);
      const invalid = allQuestions(schema).find(q => isVisible(q, effective) && validate(q, effective[q.id]));
      if (invalid) { setError(`${invalid.label}: ${validate(invalid, effective[invalid.id])}`); return; }
      if (!consent) { setError('Please confirm your consent before submitting.'); return; }
      if (!locationConsent && allQuestions(schema).some(q => q.type === 'location' && effective[q.id]?.state === 'answered')) {
        setError('Coordinate answers require your explicit location consent.'); return;
      }
      const referenced = new Set(allQuestions(schema).filter(q => q.type === 'media').flatMap(q => effective[q.id]?.value || []));
      pending.current = {submission_id: uuid(), answers: effective, consent, location_consent: locationConsent, location: location || null,
        attachments: files.filter(f => referenced.has(f.id)).map(({size, ...attachment}) => attachment)};
    }
    setBusy(true);
    try {
      const result = await publicRequest(token, pending.current);
      receiptStorage(token, result.receipt); setReceipt(result.receipt);
      pending.current = null; setAnswers({}); setFiles([]);
    } catch (e) {
      // A known rejection allows editing. An unconfirmed network/server failure
      // retains the exact request, so retries cannot create a second interview.
      if (e.status && e.status < 500) pending.current = null;
      setError(pending.current ? 'We could not confirm your submission. Please retry; the same answers will be sent safely without creating a duplicate.' : e.message);
    } finally { setBusy(false); }
  }

  function startAgain() {
    receiptStorage(token, null); setReceipt(null); setSurvey(null); setAnswers({}); setFiles([]);
    setConsent(false); setLocationConsent(false); setLocation(''); setShowErrors(false); setError('');
    pending.current = null; setAttempt(n => n + 1);
  }

  const visibleQuestions = schema ? allQuestions(schema).filter(q => isVisible(q, normalize(schema, answers))) : [];
  const answered = visibleQuestions.filter(q => ['answered', 'not_sure', 'prefer_not_to_answer'].includes(answers[q.id]?.state)).length;
  return <div className="public-survey">
    <header className="public-header"><span className="brand-mark">S</span><strong>Student Survey Creator</strong><span className="badge">Questionnaire</span></header>
    <main className="public-content">
      {loading ? <div className="card" role="status">Opening questionnaire…</div> : receipt ?
        <section className="card public-success"><span className="badge">RESPONSE RECEIVED</span><h1>Thank you for taking part.</h1><p>Your answers have been submitted.</p><p>Receipt: <code>{receipt}</code></p><button onClick={startAgain}>Start another response</button></section> : !survey ?
        <section className="card"><h1>Survey unavailable</h1><p role="alert">{error || 'Please check the link with the person who shared it.'}</p><button onClick={() => setAttempt(n => n + 1)}>Try again</button></section> :
        <><div className="public-title"><p className="eyebrow">{survey.project_name}</p><h1>{survey.title}</h1><p>No account or sign-in is required. Fields marked * need an answer, or you may choose “not sure” or “prefer not to answer.”</p><small>Questionnaire version {survey.version_number} · {answered} of {visibleQuestions.length} visible questions addressed</small></div>
          <form onSubmit={submit} noValidate>
            {error && <div className="error banner" role="alert">{error}</div>}
            <fieldset disabled={locked}>
              <section className="card"><h2>Your consent</h2><p className="consent-statement">{schema.consent || 'Participation is voluntary. You may choose not to answer a question or stop before submitting.'}</p><label className="check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>I have read the statement and agree to participate</label>
                {allQuestions(schema).some(q => q.type === 'location') && <label className="check"><input type="checkbox" checked={locationConsent} onChange={e => {setLocationConsent(e.target.checked); if (!e.target.checked) setAnswers(previous => normalize(schema, Object.fromEntries(Object.entries(previous).map(([id, a]) => [id, allQuestions(schema).some(q => q.id === id && q.type === 'location') ? {state:'missing'} : a]))));}}/>I explicitly consent to providing coordinates (optional)</label>}
                {survey.locations.length > 0 && <label>Location (optional)<select value={location} onChange={e => setLocation(e.target.value)}><option value="">Select a location</option>{survey.locations.map(l => <option key={l.id} value={l.id}>{l.label}</option>)}</select></label>}
              </section>
              <section className="card"><DynamicForm schema={schema} answers={answers} onChange={setAnswers} locationConsent={locationConsent} showErrors={showErrors} onFile={attach}/></section>
            </fieldset>
            <div className="public-submit"><p>Your answers will be sent when you submit. You can close this page before submitting; unsent answers are not saved to this browser.</p><button className="primary" type="submit" disabled={busy}>{busy ? 'Submitting…' : pending.current ? 'Retry submission' : 'Submit answers'}</button></div>
          </form></>}
    </main><footer>Student Survey &amp; Questionnaire Creator System · Thank you for taking part in this survey.</footer>
  </div>;
}
