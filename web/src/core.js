export const types = ['text','single','multiple','number','currency','date','time','rating','boolean','media','location'];
export const states = ['answered','missing','skipped','not_sure','prefer_not_to_answer'];
export const uuid = () => crypto.randomUUID();
export const allQuestions = schema => (schema?.sections || []).flatMap(s => s.questions);
export const blankSchema = () => ({sections: [{id: uuid(), label: 'Section 1', questions: []}]});
export function isVisible(q, answers) {
  const r = q.condition;
  if (!r) return true;
  const a = answers[r.question_id] || {state:'missing'};
  const v = a.state === 'answered' ? a.value : null;
  switch(r.op) {
    case 'equals': return v === r.value;
    case 'not_equals': return v !== null && v !== r.value;
    case 'contains': return Array.isArray(v) && v.includes(r.value);
    case 'answered': return a.state === 'answered';
    default: return false;
  }
}
export function normalize(schema, answers) {
  const result = {};
  for (const q of allQuestions(schema)) result[q.id] = isVisible(q, result) ? (answers[q.id] || {state:'missing'}) : {state:'skipped'};
  return result;
}
export function defaults(schema) {
  return normalize(schema,Object.fromEntries(allQuestions(schema).filter(q => q.default !== undefined).map(q => [q.id,{state:'answered',value:q.default}])));
}
export function validate(q, a) {
  if (a.state !== 'answered') return q.required && !['not_sure','prefer_not_to_answer'].includes(a.state) ? 'This question is required.' : '';
  const v = a.value, r = q.validation || {};
  if(q.required&&((q.type==='text'&&!(typeof v==='string'&&v.trim()))||(['multiple','media'].includes(q.type)&&!(Array.isArray(v)&&v.length))))return 'This question is required.';
  if (['number','currency','rating'].includes(q.type)) {
    if (typeof v !== 'number' || !Number.isFinite(v)) return 'Enter a valid number.';
    if ((r.min !== undefined && v < r.min) || (r.max !== undefined && v > r.max)) return 'Value is outside the allowed range.';
  }
  if (q.type === 'text' && (typeof v !== 'string' || v.length < (r.min_length || 0) || v.length > (r.max_length || 100000))) return 'Check the text length.';
  if (q.type === 'multiple' && (!Array.isArray(v) || v.length < (r.min_selections || 0) || v.length > (r.max_selections || 1000))) return 'Check the number of selected choices.';
  if (q.type === 'single' && !q.choices.some(c => c.code === v)) return 'Select a choice.';
  if (['date','time'].includes(q.type) && !v) return 'Enter a date or time.';
  if (q.type === 'location' && (!v || !Number.isFinite(v.latitude) || !Number.isFinite(v.longitude) || Math.abs(v.latitude)>90 || Math.abs(v.longitude)>180)) return 'Enter valid coordinates.';
  return '';
}
export function conditionValue(q, value) {
  if (q?.type === 'boolean') return value === 'true';
  if (['number','currency','rating'].includes(q?.type)) return Number(value);
  return value;
}

const yesNo = labels => labels.length === 2 && labels.includes('yes') && labels.includes('no');
const choiceCode = (used, index) => {
  const letters = 'abcdefghijklmnopqrstuvwxyz';
  let code = index < letters.length ? letters[index] : 'choice_' + (index + 1);
  while (used.has(code)) code += '_';
  used.add(code);
  return code;
};

function finishQuestion(question) {
  const choices = (question.choices || []).filter(choice => choice.label);
  const labels = choices.map(choice => choice.label.trim().toLowerCase());
  const label = question.label;
  delete question.choices;
  delete question.validation;
  if (choices.length) {
    if (yesNo(labels)) question.type = 'boolean';
    else {
      question.type = /select all|choose all|check all|tick all|all that apply|multiple (?:answers|choices|options)/i.test(label) ? 'multiple' : 'single';
      const used = new Set();
      question.choices = choices.map((choice, index) => ({code: choiceCode(used, index), label: choice.label.trim()}));
    }
  } else {
    const scale = label.match(/\b(\d{1,2})\s*(?:-|to|–|—)\s*(\d{1,2})\b/i);
    if (/rating|rate your|satisfied|satisfaction|scale/i.test(label)) {
      question.type = 'rating';
      const low = scale ? Number(scale[1]) : 1, high = scale ? Number(scale[2]) : 5;
      if (high > low) question.validation = {min: low, max: high};
    } else if (/\bhow many\b|\bnumber of\b|\bage\b|\bhours?\b|\bminutes?\b|\bdays?\b|\bmonths?\b|\byears?\b|\bscore\b|\btimes? per\b/i.test(label)) {
      question.type = 'number';
    } else question.type = 'text';
  }
  question.required = !!question.required;
  question.sensitive = false;
  return question;
}

export function parseQuestionScript(input) {
  const warnings = [];
  const sections = [];
  let title = '', currentSection = null, currentQuestion = null;
  const clean = String(input || '').replace(/\r\n?/g, '\n');
  const lines = clean.split('\n');
  const addSection = label => {
    currentSection = {id: uuid(), label: label || 'Survey questions', questions: []};
    sections.push(currentSection);
    currentQuestion = null;
    return currentSection;
  };
  const addQuestion = (label, required = false) => {
    if (!currentSection) addSection(title || 'Survey questions');
    const text = label.replace(/\s*\*+\s*$/, '').trim();
    if (!text) { warnings.push('Skipped an empty question line.'); return; }
    currentQuestion = {id: uuid(), label: text, type: 'text', required, sensitive: false};
    currentSection.questions.push(currentQuestion);
  };
  const addChoice = (label, code = '') => {
    if (!currentQuestion) { warnings.push(`Ignored a choice without a question: “${label}”`); return; }
    currentQuestion.choices = currentQuestion.choices || [];
    if (!currentQuestion.choices.some(choice => choice.label.toLowerCase() === label.toLowerCase())) {
      currentQuestion.choices.push({label, code});
    }
  };
  let seenContent = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const heading = line.match(/^(?:#{1,4}\s+(.+)|section\s*\d*\s*[:.\-–—]\s*(.+))$/i);
    if (heading) { addSection((heading[1] || heading[2]).trim()); seenContent = true; continue; }
    const lettered = line.match(/^(?:\(([a-zA-Z])\)|([a-zA-Z])[.)])\s+(.+)$/);
    if (currentQuestion && lettered) { addChoice(lettered[3], (lettered[1] || lettered[2]).toLowerCase()); seenContent = true; continue; }
    if (currentQuestion && /^(yes|no|true|false)$/i.test(line) && (currentQuestion.choices || []).every(choice => /^(yes|no|true|false)$/i.test(choice.label))) {
      addChoice(line[0].toUpperCase() + line.slice(1).toLowerCase());
      seenContent = true;
      continue;
    }
    const bullet = line.match(/^[-*•–—]\s+(.+)$/);
    if (bullet) {
      if (currentQuestion) addChoice(bullet[1]);
      else addQuestion(bullet[1]);
      seenContent = true;
      continue;
    }
    const numbered = line.match(/^(?:q(?:uestion)?\s*)?(\d{1,3})\s*[.)\-–—:]\s+(.+)$/i);
    if (numbered) { addQuestion(numbered[2], /required/i.test(numbered[2])); seenContent = true; continue; }
    const prefixed = line.match(/^q(?:uestion)?\s*[:.\-–—]\s+(.+)$/i);
    if (prefixed) { addQuestion(prefixed[1]); seenContent = true; continue; }
    if (line.endsWith('?')) { addQuestion(line); seenContent = true; continue; }
    if (!currentSection && !currentQuestion && !title) {
      title = line;
      seenContent = true;
      continue;
    }
    if (currentQuestion && !currentQuestion.choices && line.length <= 300) {
      currentQuestion.label += ' ' + line;
      seenContent = true;
      continue;
    }
    if (!currentQuestion && seenContent && line.length <= 120) { addSection(line); seenContent = true; continue; }
    warnings.push(`Could not understand: “${line}”`);
    seenContent = true;
  }
  for (const section of sections) {
    section.questions = section.questions.map(finishQuestion);
    section.questions.forEach(question => {
      if (/\brequired\b/i.test(question.label)) {
        question.required = true;
        question.label = question.label.replace(/\s*[\[(]?required[\])]?\s*$/i, '').trim();
      }
    });
    section.questions = section.questions.filter(question => question.label);
  }
  const kept = sections.filter(section => section.questions.length);
  if (!clean.trim()) warnings.push('Paste some questions first.');
  else if (!kept.length) warnings.push('No questions were detected. Start each question with a number, like “1. What is your year level?”');
  return {title, sections: kept, warnings, count: kept.reduce((total, section) => total + section.questions.length, 0)};
}

export function mergeImportedSections(schema, parsed) {
  const base = schema ? structuredClone(schema) : blankSchema();
  const kept = (base.sections || []).filter(section => section.questions?.length);
  const incoming = (parsed?.sections || []).filter(section => section.questions?.length).map(section => ({
    id: uuid(),
    label: section.label,
    questions: section.questions.map(question => ({...structuredClone(question), id: uuid()})),
  }));
  return {sections: [...kept, ...incoming].length ? [...kept, ...incoming] : blankSchema().sections};
}

export const questionScriptExample = `Student Learning Experience

1. What is your year level?
A. First year
B. Second year
C. Third year
D. Fourth year

2. Which learning resources do you use? (select all that apply)
- Books
- Videos
- Online articles

3. How many hours do you study each day?

4. How satisfied are you with your learning experience? (1-5)

5. What improvements would you suggest?
`;
