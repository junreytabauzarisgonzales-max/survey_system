import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test('share version-pinned link, answer on mobile without account, retry safely, review and close link', async ({page,request,browser}) => {
  const login=await (await request.post('/api/login',{data:{email:'browser@example.test',password:'browser-test-password'}})).json();
  const headers={Authorization:'Bearer '+login.token};
  const post=async(path,data)=>{const response=await request.post('/api'+path,{headers,data});expect(response.ok()).toBeTruthy();return response.json();};
  const project=await post('/projects',{name:'Public browser study',config:{consent:'You may decline or stop before submitting.'}});
  const story=randomUUID(),choice=randomUUID(),contact=randomUUID(),trigger=randomUUID(),follow=randomUUID(),media=randomUUID();
  const schema={sections:[{id:randomUUID(),label:'Your experience',questions:[
    {id:story,label:'Your story',type:'text',required:true},
    {id:choice,label:'Activities',type:'multiple',choices:[{code:'a',label:'Activity A'},{code:'b',label:'Activity B'}]},
    {id:contact,label:'Optional contact',type:'text',sensitive:true},
    {id:trigger,label:'Share more detail?',type:'boolean'},
    {id:follow,label:'More detail',type:'text',condition:{question_id:trigger,op:'equals',value:true}},
    {id:media,label:'Optional document',type:'media'},
  ]}]};
  const form=await post(`/projects/${project.id}/forms`,{name:'Self-answer form',draft:schema});
  await post(`/forms/${form.id}/publish`,{revision:form.revision});
  await page.addInitScript(token=>sessionStorage.setItem('agal-token',token),login.token);
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();
  await page.getByRole('combobox',{name:'Current survey',exact:true}).selectOption(project.id);
  await page.getByRole('navigation').getByRole('button',{name:/Share$/}).click();
  await page.getByRole('combobox',{name:'Published version to share',exact:true}).selectOption({label:'Self-answer form · v1'});
  await page.getByLabel('Link name',{exact:true}).fill('Open invitation');
  await page.getByRole('button',{name:'Create link',exact:true}).click();
  const link=page.getByLabel('Shareable link',{exact:true});
  await expect(link).toBeVisible();
  const url=await link.inputValue();
  expect(url).toContain('/survey/');

  const respondent=await browser.newContext({viewport:{width:390,height:844}});
  const survey=await respondent.newPage();
  const browserErrors=[],authHeaders=[];
  survey.on('pageerror',e=>browserErrors.push(e.message));
  survey.on('request',r=>{if(r.url().includes('/api/public/'))authHeaders.push(r.headers().authorization);});
  try {
    await survey.goto(url);
    await expect(survey.getByRole('heading',{name:'Self-answer form'})).toBeVisible();
    await expect(survey.getByRole('navigation')).toHaveCount(0);
    await expect(survey.getByLabel('Password',{exact:true})).toHaveCount(0);
    await survey.getByLabel('Your story',{exact:true}).fill('Kumusta, "ñ"\nA public response 🌿');
    await survey.getByLabel('Activity A',{exact:true}).check();
    await survey.getByLabel('Activity B',{exact:true}).check();
    await survey.getByLabel('Optional contact',{exact:true}).fill('Protected contact detail');
    await survey.getByRole('combobox',{name:'Share more detail?',exact:true}).selectOption('true');
    await survey.getByLabel('More detail',{exact:true}).fill('This must become skipped');
    await survey.getByRole('combobox',{name:'Share more detail?',exact:true}).selectOption('false');
    await expect(survey.getByLabel('More detail',{exact:true})).toHaveCount(0);
    await survey.getByLabel('Optional document',{exact:true}).setInputFiles({name:'note.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 test attachment')});
    await survey.getByRole('button',{name:'Submit answers',exact:true}).click();
    await expect(survey.getByRole('alert')).toContainText('confirm your consent');
    await survey.getByLabel('I have read the statement and agree to participate').check();
    const payloads=[];
    let first=true;
    await survey.route('**/api/public/surveys/*/responses',async route=>{
      payloads.push(route.request().postDataJSON());
      if(first){first=false;const response=await route.fetch();expect(response.ok()).toBeTruthy();await route.abort('failed');}
      else await route.continue();
    });
    await survey.getByRole('button',{name:'Submit answers',exact:true}).click();
    await expect(survey.getByRole('button',{name:'Retry submission',exact:true})).toBeVisible();
    await expect(survey.getByLabel('Your story',{exact:true})).toBeDisabled();
    await survey.getByRole('button',{name:'Retry submission',exact:true}).click();
    await expect(survey.getByRole('heading',{name:'Thank you for taking part.'})).toBeVisible();
    expect(payloads).toHaveLength(2);expect(payloads[0]).toEqual(payloads[1]);
    expect(authHeaders.every(h=>h===undefined)).toBeTruthy();
    expect(await survey.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await survey.reload();
    await expect(survey.getByRole('heading',{name:'Thank you for taking part.'})).toBeVisible();

    await page.getByRole('navigation').getByRole('button',{name:/Responses$/}).click();
    await expect(page.getByRole('cell',{name:'Public link',exact:true})).toHaveCount(1);
    const records=await (await request.get(`/api/projects/${project.id}/interviews`,{headers})).json();
    expect(records).toHaveLength(1);expect(records[0].researcher_id).toBeNull();
    expect(records[0].answers[follow].state).toBe('skipped');
    const exported=await request.post('/api/exports/csv',{headers,data:{project_id:project.id,source:'public_link',format:'long'}});
    const csv=await exported.text();
    expect(csv).toContain('public_link');expect(csv).toContain('Kumusta, ""ñ""');expect(csv).not.toContain('Protected contact detail');
    const updated=await request.put(`/api/projects/${project.id}/forms/${form.id}`,{headers,data:{...form,draft:{sections:[{...schema.sections[0],questions:schema.sections[0].questions.map(q=>q.id===story?{...q,label:'Changed story label'}:q)}]}}});
    const newForm=await updated.json();await post(`/forms/${form.id}/publish`,{revision:newForm.revision});
    await survey.getByRole('button',{name:'Start another response'}).click();
    await expect(survey.getByLabel('Your story',{exact:true})).toBeVisible();
    await expect(survey.getByLabel('Changed story label',{exact:true})).toHaveCount(0);
    await page.getByRole('navigation').getByRole('button',{name:/Share$/}).click();
    await page.getByRole('button',{name:'Disable link',exact:true}).click();
    await expect(page.locator('.public-link-card').getByText('Disabled',{exact:true})).toBeVisible();
    await survey.reload();
    await expect(survey.getByRole('heading',{name:'Survey unavailable'})).toBeVisible();
    expect(browserErrors).toEqual([]);
  } finally {await respondent.close();}
});
