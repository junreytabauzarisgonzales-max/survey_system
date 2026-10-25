import test from 'node:test';
import assert from 'node:assert/strict';
import {normalize, isVisible, validate, parseQuestionScript, mergeImportedSections} from './core.js';
test('condition cascade removes hidden values without evaluating code', () => {
  const schema = {sections:[{questions:[{id:'a',type:'boolean'}, {id:'b',type:'text',condition:{question_id:'a',op:'equals',value:true}}, {id:'c',type:'text',condition:{question_id:'b',op:'answered'}}]}]};
  const a = normalize(schema, {a:{state:'answered',value:false},b:{state:'answered',value:'stale'},c:{state:'answered',value:'stale'}});
  assert.equal(a.b.state,'skipped'); assert.equal(a.c.state,'skipped');
  assert.equal(isVisible({condition:{question_id:'a',op:'eval',value:'alert()'}},a),false);
});
test('required answers distinguish explicit refusal from unanswered', () => {
  const q={type:'text',required:true};
  assert.equal(validate(q,{state:'prefer_not_to_answer'}),'');
  assert.ok(validate(q,{state:'missing'}));
  assert.ok(validate(q,{state:'answered',value:'  '}));
});
test('currency remains numeric and bounded', () => {
  const q={type:'currency',validation:{min:0,max:500}};
  assert.ok(validate(q,{state:'answered',value:'₱30'}));
  assert.equal(validate(q,{state:'answered',value:30.5}),'');
  assert.ok(validate(q,{state:'answered',value:NaN}));
});
test('plain-text questions detect title, choices and multiple selection', () => {
  const parsed=parseQuestionScript(`Student Learning Experience

1. What is your year level?
A. First year
B. Second year

2. Which resources do you use? (select all that apply)
- Books
- Videos
`);
  assert.equal(parsed.title,'Student Learning Experience');
  assert.equal(parsed.count,2);
  assert.equal(parsed.sections.length,1);
  const [year,resources]=parsed.sections[0].questions;
  assert.equal(year.type,'single');
  assert.deepEqual(year.choices.map(c=>c.code),['a','b']);
  assert.deepEqual(year.choices.map(c=>c.label),['First year','Second year']);
  assert.equal(resources.type,'multiple');
  assert.deepEqual(resources.choices.map(c=>c.label),['Books','Videos']);
});
test('plain text detects yes/no, ratings and numeric questions', () => {
  const parsed=parseQuestionScript(`1. Do you agree?
Yes
No

2. How satisfied are you? (1-10)

3. How many hours do you study?
`);
  const [agree,satisfied,hours]=parsed.sections[0].questions;
  assert.equal(agree.type,'boolean');
  assert.equal(agree.choices,undefined);
  assert.equal(satisfied.type,'rating');
  assert.deepEqual(satisfied.validation,{min:1,max:10});
  assert.equal(hours.type,'number');
});
test('imported questions append without keeping an empty starter section', () => {
  const parsed=parseQuestionScript('1. Your name?');
  const merged=mergeImportedSections({sections:[{id:'old',label:'Section 1',questions:[]}]},parsed);
  assert.equal(merged.sections.length,1);
  assert.equal(merged.sections[0].label,'Survey questions');
  assert.equal(merged.sections[0].questions[0].label,'Your name?');
  assert.notEqual(merged.sections[0].questions[0].id,'old');
});
test('question parser warns about unrecognized content', () => {
  const parsed=parseQuestionScript('Some title\n\ninstructions here');
  assert.equal(parsed.count,0);
  assert.ok(parsed.warnings.length>0);
});
