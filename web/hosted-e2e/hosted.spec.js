import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test('documentation, hosted workspace and public responses share a PostgreSQL-backed deployment',async({page,request})=>{
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{level:1})).toContainText('Better surveys.');
  await page.getByRole('link',{name:'Open the online workspace'}).click();
  await expect(page).toHaveURL(/\/app\//);
  await expect(page.getByRole('heading',{name:'Welcome back.'})).toBeVisible();

  const email=`hosted-${randomUUID()}@example.test`,password='hosted-test-password';
  const registered=await request.post('/api/register',{data:{name:'Hosted owner',email,password}});
  expect(registered.ok()).toBeTruthy();
  const session=await registered.json(),headers={Authorization:`Bearer ${session.token}`};
  const project=await (await request.post('/api/projects',{headers,data:{name:'Hosted questionnaire'}})).json();
  const qid=randomUUID();
  const form=await (await request.post(`/api/projects/${project.id}/forms`,{headers,data:{name:'A cloud survey',draft:{sections:[{id:randomUUID(),label:'Your feedback',questions:[{id:qid,label:'What did you learn?',type:'text',required:true}]}]}}})).json();
  const version=await (await request.post(`/api/forms/${form.id}/publish`,{headers,data:{revision:form.revision}})).json();
  const link=await (await request.post(`/api/projects/${project.id}/public-links`,{headers,data:{name:'Hosted public link',version_id:version.id}})).json();

  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in →',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();

  await page.goto(`/survey/${link.token}`);
  await expect(page.getByRole('heading',{name:'A cloud survey'})).toBeVisible();
  await page.getByRole('textbox',{name:'What did you learn?',exact:true}).fill('PostgreSQL keeps our answers.');
  await page.getByLabel('I have read the statement and agree to participate').check();
  await page.getByRole('button',{name:'Submit answers',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Thank you for taking part.'})).toBeVisible();
  const rows=await (await request.get(`/api/projects/${project.id}/interviews`,{headers})).json();
  expect(rows).toHaveLength(1);
  expect(rows[0].answers[qid].value).toBe('PostgreSQL keeps our answers.');
  expect(rows[0].source).toBe('public_link');
  expect(errors).toEqual([]);
});
