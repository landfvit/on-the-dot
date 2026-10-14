const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/private/tmp/otd-question-editor';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=process.env.TEST_BROWSER==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[360,740],[390,844],[1440,900]])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];let rows=[],duel=null;
   await page.addInitScript(t=>localStorage.setItem('onthedot.theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname,method=route.request().method(),body=method==='GET'?null:route.request().postDataJSON();
    if(path==='/api/players/questions'){
     if(method==='GET')return route.fulfill({json:{questions:rows,topics:['Transfers and loans','Player milestones']}});
     const row={submission_id:'a1a0dfce-5e3a-4815-99c0-4ec1a53f49bb',revision:1,content:body,status:'draft',review_note:''};rows=[row];return route.fulfill({status:201,json:row});
    }
    if(path.endsWith('/submit')){rows[0].status='pending';return route.fulfill({json:rows[0]});}
    if(path==='/api/friends/rooms'){duel=body;return route.fulfill({status:201,json:{code:'test-custom'}});}
    return route.fulfill({status:401,json:{detail:'Sign in'}});
   });
   await page.route('**/friends/test-custom',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><title>Custom duel</title>'}));
   await page.goto(origin+'/my-questions');await page.getByRole('button',{name:'New question',exact:true}).click();
   const form=page.locator('#question-form');await form.locator('[name=question]').fill('From which club did Liverpool sign Mohamed Salah in 2017?');
   for(const [i,v] of ['Roma','Chelsea','Fiorentina','Basel'].entries())await form.locator(`[name=option${i}]`).fill(v);
   assert.equal(await form.locator('[name=source_url]').count(),0);
   const geometry=await page.locator('#question-editor').evaluate(d=>{const r=d.getBoundingClientRect();return {inside:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,noOverflow:d.scrollWidth<=d.clientWidth+1,modal:d.matches(':modal')};});
   assert.deepEqual(geometry,{inside:true,noOverflow:true,modal:true});
   await page.screenshot({path:`${out}/${process.env.TEST_BROWSER||'chrome'}-${width}-${theme}-editor.png`});
   await page.getByRole('button',{name:'Save question',exact:true}).click();await page.getByText('Question saved.',{exact:true}).waitFor();
   await page.getByRole('button',{name:'Submit for review',exact:true}).click();await page.locator('.question-state').filter({hasText:'pending'}).waitFor();
   await page.locator('.question-row input[type=checkbox]').check();assert.equal(await page.locator('#create-custom-duel').isEnabled(),true);
   assert.equal(await page.locator('#bank-fallback').isChecked(),false);await page.locator('#bank-fallback').check();assert.equal(await page.locator('#fallback-difficulty').isVisible(),true);
   await page.screenshot({path:`${out}/${process.env.TEST_BROWSER||'chrome'}-${width}-${theme}-library.png`});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.locator('#create-custom-duel').click();await page.waitForURL('**/friends/test-custom');
   assert.equal(duel.bank_fallback,true);assert.equal(duel.question_ids.length,1);assert.deepEqual(errors,[]);
   await page.close();console.log(`PASS editor ${width} ${theme}`);
  }
  // Render the real protected template in an isolated test process. Browser
  // requests below are mocked, so no admin credentials or reviews are changed.
  const {execFileSync}=require('node:child_process');
  const reviewHTML=execFileSync('.venv/bin/python',['-c',`from fastapi.testclient import TestClient
from trivia_app.main import app
from api.trivia_access import require_editor
app.dependency_overrides[require_editor]=lambda: True
response=TestClient(app).get('/internal/trivia/community-questions')
assert response.status_code==200
print(response.text)`],{encoding:'utf8',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  for(const [width,height] of [[390,844],[1440,900]])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];let decision=null;
   await page.addInitScript(t=>localStorage.setItem('onthedot.theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
   const row={submission_id:'a1a0dfce-5e3a-4815-99c0-4ec1a53f49bb',revision:1,status:'pending',username:'ExamplePlayer',review_note:'',content:{question:'Which club did Thierry Henry join after leaving Arsenal in 2007?',options:['Barcelona','Inter','Juventus','Real Madrid'],correct:0,difficulty:'easy',explanation:'A permanent transfer in summer 2007.'}};
   await page.route('**/internal/trivia/community-questions',r=>r.fulfill({contentType:'text/html',body:reviewHTML}));
   await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/trivia/community-questions')return route.fulfill({json:{questions:decision?[]:[row],total:decision?0:1}});
    if(path.endsWith('/review')){decision=route.request().postDataJSON();return route.fulfill({json:{...row,status:decision.decision}});}
    return route.fulfill({status:401,json:{detail:'Sign in'}});
   });
   await page.goto(origin+'/internal/trivia/community-questions');await page.getByRole('button',{name:'Review',exact:true}).click();
   await page.locator('#review-form [name=verified]').check();await page.locator('#review-form [name=note]').fill('Transfer and all answer choices checked against the source.');
   const geometry=await page.locator('#question-review').evaluate(d=>{const r=d.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight&&d.scrollWidth<=d.clientWidth+1;});assert(geometry);
   await page.screenshot({path:`${out}/${process.env.TEST_BROWSER||'chrome'}-${width}-${theme}-review.png`});
   await page.getByRole('button',{name:'Approve and publish',exact:true}).click();await page.getByText('Published to the public bank.',{exact:true}).waitFor();
   assert.equal(decision.decision,'approved');assert.equal(decision.verified,true);assert.deepEqual(errors,[]);await page.close();console.log(`PASS review ${width} ${theme}`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
