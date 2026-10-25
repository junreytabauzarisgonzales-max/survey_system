import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test('register for free, create a private survey, and sign out',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Welcome back.'})).toBeVisible();
  await page.getByRole('button',{name:'New here? Create a free account'}).click();
  await expect(page.getByRole('heading',{name:'Create your account.'})).toBeVisible();
  await page.getByLabel('Your name',{exact:true}).fill('Ada Student');
  await page.getByLabel('Email',{exact:true}).fill(`ada-${randomUUID()}@example.test`);
  await page.getByLabel('Password',{exact:true}).fill('student-pass-123');
  await page.getByRole('button',{name:/Create my account/}).click();
  await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();
  await expect(page.getByText('Your account is ready. Create your first survey.')).toBeVisible();
  await page.getByRole('navigation').getByRole('button',{name:/My Surveys$/}).click();
  await page.getByLabel('Survey title',{exact:true}).fill('My private survey');
  await page.getByRole('button',{name:'Create survey →'}).click();
  await expect(page.getByRole('heading',{name:'Questions',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'+ Add question'}).click();
  await page.getByLabel('Question label',{exact:true}).fill('What should we improve?');
  await page.getByRole('button',{name:'Publish version →'}).click();
  await expect(page.getByRole('status')).toContainText('Published version 1');
  await page.getByRole('button',{name:'Sign out'}).click();
  await expect(page.getByRole('heading',{name:'Welcome back.'})).toBeVisible();
  expect(errors).toEqual([]);
});
