import React, {useState} from 'react';
import {mergeImportedSections, parseQuestionScript, questionScriptExample} from './core';

const answerTypes = ['text','single','multiple','number','currency','rating','boolean','date','time'];

function withType(question, type) {
  const next = {...question, type};
  if (['single', 'multiple'].includes(type)) {
    next.choices = question.choices?.length ? question.choices : [{code:'a', label:'Choice 1'}, {code:'b', label:'Choice 2'}];
  } else {
    delete next.choices;
  }
  if (type === 'rating') next.validation = question.validation || {min:1, max:5};
  if (!['number', 'currency', 'rating'].includes(type)) delete next.validation;
  return next;
}

export function QuestionImporter({schema, onChange, onClose}) {
  const [script, setScript] = useState('');
  const [parsed, setParsed] = useState(() => parseQuestionScript(''));
  const update = value => { setScript(value); setParsed(parseQuestionScript(value)); };
  const count = parsed.sections.reduce((total, section) => total + section.questions.length, 0);
  const change = (si, qi, changes) => setParsed(current => ({
    ...current,
    sections: current.sections.map((section, index) => index !== si ? section : {
      ...section,
      questions: section.questions.map((question, questionIndex) => questionIndex !== qi ? question : {...question, ...changes}),
    }),
  }));
  const remove = (si, qi) => setParsed(current => ({
    ...current,
    sections: current.sections.map((section, index) => index !== si ? section : {
      ...section,
      questions: section.questions.filter((_, questionIndex) => questionIndex !== qi),
    }).filter(section => section.questions.length),
  }));
  const add = () => { onChange(mergeImportedSections(schema, parsed)); onClose(); };
  return <div className="modal-backdrop"><section className="modal importer" role="dialog" aria-modal="true" aria-label="Paste questions">
    <div className="toolbar"><h2 className="grow">Paste questions</h2><button onClick={onClose} aria-label="Close dialog">✕</button></div>
    <p>Paste questions from Word, Google Docs, a message, or any plain text. Start each question with a number. Put answers on their own lines using letters or bullet points.</p>
    <div className="grid import-grid">
      <label>Your questions<textarea className="script-input" value={script} onChange={event => update(event.target.value)} placeholder={questionScriptExample}/></label>
      <aside className="import-help"><strong>Quick tips</strong><ul><li><code>1. Question text?</code></li><li><code>A. First answer</code> or <code>- First answer</code></li><li>Add <code>(select all that apply)</code> for multiple answers.</li><li>Add <code>(1-5)</code> for a rating scale.</li><li>Add <code>*</code> to the end to make a question required.</li></ul><button type="button" onClick={() => update(questionScriptExample)}>Fill with an example</button></aside>
    </div>
    <div className="toolbar"><span className="badge">{count} question{count === 1 ? '' : 's'} detected</span><span className="grow"/>{script && <button type="button" onClick={() => update('')}>Clear</button>}</div>
    {script && parsed.warnings.length > 0 && <div className="note">{parsed.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</div>}
    {parsed.sections.map((section, si) => <section className="import-preview" key={section.id}>
      <h3>{section.label}</h3>
      {section.questions.map((question, qi) => <article className="import-question" key={question.id}>
        <span className="question-number">{qi + 1}</span>
        <div className="grow">
          <label>Question<input value={question.label} onChange={event => change(si, qi, {label:event.target.value})}/></label>
          <div className="toolbar">
            <label>Answer type<select value={question.type} onChange={event => change(si, qi, withType(question, event.target.value))}>{answerTypes.map(type => <option key={type}>{type}</option>)}</select></label>
            <label className="check"><input type="checkbox" checked={!!question.required} onChange={event => change(si, qi, {required:event.target.checked})}/>Required</label>
            <button type="button" className="danger" onClick={() => remove(si, qi)}>Remove</button>
          </div>
          {question.choices?.length > 0 && <div className="choice-chips">{question.choices.map((choice, ci) => <span key={choice.code}><input aria-label={'Choice ' + (ci + 1) + ' label'} value={choice.label} onChange={event => change(si, qi, {choices:question.choices.map((item, index) => index === ci ? {...item, label:event.target.value} : item)})}/></span>)}<button type="button" onClick={() => change(si, qi, {choices:[...question.choices, {code:'c' + (question.choices.length + 1), label:'Choice ' + (question.choices.length + 1)}]})}>+ Add choice</button></div>}
          {question.validation?.min !== undefined && <small>Scale {question.validation.min} to {question.validation.max}</small>}
        </div>
      </article>)}
    </section>)}
    <div className="toolbar import-actions"><button type="button" onClick={onClose}>Cancel</button><button type="button" className="primary" disabled={!count} onClick={add}>Add {count} question{count === 1 ? '' : 's'}</button></div>
  </section></div>;
}
