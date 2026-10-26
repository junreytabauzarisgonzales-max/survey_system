import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {open} from 'node:fs/promises';

test('public website teaches users without contacting the survey API',async({page})=>{
  const apiRequests=[],errors=[];
  page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api'))apiRequests.push(request.url());});
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{level:1})).toContainText('Better surveys.');
  await expect(page.getByLabel('Email',{exact:true})).toHaveCount(0);
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Documentation'}).click();
  await expect(page.getByRole('heading',{name:'Storage, exports, and backups'})).toBeVisible();
  await expect(page.locator('#sharing')).toContainText('accepts only same-PC connections');
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Tutorials'}).click();
  await page.getByRole('button',{name:'Android',exact:true}).click();
  await expect(page.getByRole('article')).toContainText('Use device storage — no account needed');
  await page.getByRole('button',{name:/Back up and restore a workspace/}).click();
  await expect(page.getByRole('article')).toContainText('Restore local backup');
  await page.reload();
  await expect(page.getByRole('button',{name:'Android',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('heading',{name:'Back up and restore a workspace'})).toBeVisible();
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
});

test('downloads correspond to real packages and missing packages have no fake links',async({page,request})=>{
  const manifest=await (await request.get('/releases/downloads.json')).json();
  await page.goto('/downloads');
  for(const [platform,label] of [['windows','Windows'],['android','Android']]) {
    const release=manifest[platform];
    const card=page.getByRole('article').filter({has:page.getByRole('heading',{name:label,exact:true})});
    if(!release.url) {
      await expect(card.getByRole('button',{name:`${label} download not available yet`})).toBeDisabled();
      await expect(card.locator('a[download]')).toHaveCount(0);
    } else {
      const link=card.getByRole('link',{name:`Download for ${label}`,exact:false});
      await expect(link).toHaveAttribute('href',release.url);
      if(release.url.startsWith('/releases/')) {
        const downloaded=page.waitForEvent('download');
        await link.click();
        const download=await downloaded;
        expect(download.suggestedFilename()).toBe(release.filename);
        const path=await download.path();
        const handle=await open(path,'r'),signature=Buffer.alloc(4);
        try {await handle.read(signature,0,4,0);} finally {await handle.close();}
        expect(platform==='windows'?signature.toString('ascii',0,2):signature.toString('hex')).toBe(platform==='windows'?'MZ':'504b0304');
        const hash=createHash('sha256');
        for await(const chunk of createReadStream(path))hash.update(chunk);
        expect(hash.digest('hex')).toBe(release.sha256);
      }
    }
  }
});

test('download failures offer retry and navigation fits mobile screens',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.route('**/releases/downloads.json',route=>route.fulfill({status:503,body:'Unavailable'}));
  await page.goto('/downloads');
  await expect(page.getByRole('alert')).toContainText('Download information is temporarily unavailable');
  await page.unroute('**/releases/downloads.json');
  await page.getByRole('button',{name:'Retry download information'}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  for(const path of ['/','/documentation','/tutorials','/downloads']) {
    await page.goto(path);
    await expect(page.getByRole('heading',{level:1})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  }
});
