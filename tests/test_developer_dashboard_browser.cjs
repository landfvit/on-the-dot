/* Only tests.dashboard_preview: real APIs, disposable accounts/schema. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8015',out='/tmp/on-the-dot-dashboard';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',()=>errors.push('Unexpected dialog / possible XSS'));
  await page.goto(origin+'/internal/dashboard');await page.waitForURL('**/login?**');
  await page.locator('[name=username]').fill('test_editor');await page.locator('[name=password]').fill('dashboard-test-password-only');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/internal/dashboard');
  await page.locator('.metric strong').first().waitFor();assert.equal(await page.locator('.metric').count(),8);
  assert.equal(await page.locator('.chart-bar').count(),7);await page.screenshot({path:out+'/overview-desktop.png',fullPage:true});
  await page.locator('#period').selectOption('30');await page.waitForFunction(()=>document.querySelectorAll('.chart-bar').length===30);
  await page.getByRole('button',{name:'Players',exact:true}).click();await page.locator('#search').fill('test_player');
  await page.getByRole('button',{name:'Search',exact:true}).click();await page.locator('#player-table button').filter({hasText:'test_player'}).click();
  await page.locator('#player-title').filter({hasText:'test_player'}).waitFor();
  const playerContext=await browser.newContext(),playerPage=await playerContext.newPage();
  const signedIn=await playerContext.request.post(origin+'/api/players/login',{data:{identifier:'player@example.com',password:'test-only-password-1234'}});
  assert.equal(signedIn.status(),200);
  assert((await page.locator('#player-detail').textContent()).includes('<img src=x onerror=alert(1)>'));
  assert.equal(await page.locator('#player-detail img').count(),0);
  await page.getByRole('button',{name:'Block account',exact:true}).click();
  await page.locator('#action-reason').fill('Browser moderation test');await page.locator('#action-confirmation').fill('wrong');
  await page.locator('#confirm-action').click();await page.locator('#player-error:not([hidden])').waitFor();
  await page.locator('#action-confirmation').fill('test_player');await page.locator('#confirm-action').click();
  await page.locator('[data-action=unblock]:not([hidden])').waitFor();assert((await page.locator('#player-detail').textContent()).includes('Blocked since'));
  await playerPage.goto(origin+'/account');await playerPage.locator('#error:not([hidden])').waitFor();
  assert((await playerPage.locator('#error').textContent()).includes('This account is blocked'));
  assert(await playerPage.locator('#authentication').isVisible());
  const blocked=await playerContext.request.post(origin+'/api/solo/runs',{data:{difficulty:'easy',request_id:require('node:crypto').randomUUID()}});
  assert.equal(blocked.status(),403);
  await playerPage.setViewportSize({width:390,height:844});await playerPage.screenshot({path:out+'/blocked-player-mobile.png',fullPage:true});
  await playerContext.close();
  await page.screenshot({path:out+'/player-desktop.png'});
  await page.locator('[data-action=unblock]').click();await page.locator('#action-reason').fill('Browser test complete');
  await page.locator('#action-confirmation').fill('test_player');await page.locator('#confirm-action').click();await page.locator('[data-action=block]:not([hidden])').waitFor();
  await page.locator('#close-player').click();await page.getByRole('button',{name:'Games',exact:true}).click();
  await page.locator('#game-mode').selectOption('friend');await page.waitForFunction(()=>document.querySelectorAll('#game-table tbody tr').length===1);
  assert((await page.locator('#game-table').textContent()).includes('Friend Duel'));
  await page.getByRole('button',{name:'Management',exact:true}).click();await page.locator('#audit-table tbody tr').first().waitFor();
  assert.equal(await page.locator('#audit-table tbody tr').count(),2);
  await page.getByRole('button',{name:'Players',exact:true}).click();
  await page.locator('#player-table button').filter({hasText:'test_player'}).click();
  await page.locator('#player-title').filter({hasText:'test_player'}).waitFor();
  await page.getByRole('button',{name:'Delete account',exact:true}).click();
  await page.locator('#action-reason').fill('Delete disposable browser fixture');
  await page.locator('#action-confirmation').fill('test_player');
  for(const width of [390,1440]){
   await page.setViewportSize({width,height:900});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:`${out}/confirm-delete-${width}.png`});
  }
  await page.getByRole('button',{name:'Permanently delete',exact:true}).click();
  await page.locator('#player-dialog').waitFor({state:'hidden'});
  await page.waitForFunction(()=>document.querySelector('#player-table').textContent.includes('No records'));
  await page.getByRole('button',{name:'Management',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('#audit-table tbody tr').length===3);
  assert((await page.locator('#audit-table').textContent()).includes('test_player'));
  for(const width of [390,768,1440]){
   await page.setViewportSize({width,height:844});await page.getByRole('button',{name:'Overview',exact:true}).click();
   await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No page overflow at '+width);
   await page.screenshot({path:`${out}/overview-${width}.png`,fullPage:true});
  }
  await page.route('**/api/developer/overview?*',r=>r.fulfill({status:503,json:{detail:'Database unavailable for test'}}));
  await page.locator('#refresh').click();await page.locator('#error:not([hidden])').waitFor();
  assert((await page.locator('#updated').textContent()).includes('stale'));
  assert.deepEqual(errors,[]);console.log('PASS: private login, charts, search, XSS-safe rendering, block notice and denied gameplay, unblock, confirmed deletion, audit, filters, stale-data errors, desktop/mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
