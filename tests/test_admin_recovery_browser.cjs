/* Private dashboard assets and APIs are mocked. No credentials or real email. */
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const root=path.join(__dirname,'..'),output='/tmp/on-the-dot-recovery';
fs.mkdirSync(output,{recursive:true});
const player={account_id:'00000000-0000-0000-0000-000000000001',username:'test_player',
 email:'player@example.com',created_at:'2026-09-30T10:00:00Z',club:'Arsenal',bio:'',
 is_guest:false,blocked_at:null,sessions:2,audit:[],password_reset_configured:true};
(async()=>{
 const browser=process.env.TEST_BROWSER==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  let profile={...player},requests=[],failure=null,release=null,delayed=false;
  await page.route('**/internal/dashboard',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'trivia_app/templates/developer_dashboard.html'))}));
  for(const extension of ['js','css'])await page.route('**/trivia-assets/developer_dashboard.'+extension+'*',route=>route.fulfill({
   contentType:extension==='js'?'text/javascript':'text/css',body:fs.readFileSync(path.join(root,'trivia_app/static/developer_dashboard.'+extension))}));
  await page.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url());let data,status=200;
   if(url.pathname.endsWith('/password-reset')){
    assert.equal(request.method(),'POST');const body=request.postDataJSON();requests.push(body);
    assert.deepEqual(Object.keys(body).sort(),['confirmation','reason']);
    assert.equal(body.confirmation,player.username);assert.equal(body.reason,'Player requested recovery');
    if(delayed)await new Promise(resolve=>{release=resolve;});
    status=failure?502:202;data=failure?{detail:failure}:{message:'Reset email sent to the address on this account. The link works once and expires in 30 minutes.'};
   }else if(url.pathname.endsWith('/overview'))data={days:7,totals:{},trend:[],modes:[],questions:[]};
   else if(url.pathname.endsWith('/players'))data={items:[{...profile,level:1,xp:0,games:0}],offset:0,limit:25,total:1};
   else if(url.pathname.endsWith('/players/'+player.account_id))data=profile;
   else if(url.pathname.endsWith('/games'))data={items:[],offset:0,limit:10,total:0};
   else throw Error('Unexpected API '+url.pathname);
   await route.fulfill({status,json:data});
  });
  async function open(){
   await page.goto(origin+'/internal/dashboard');await page.locator('[data-tab=players]').click();
   await page.locator('#player-table button').click();await page.waitForSelector('#player-actions:not([hidden])');
  }
  async function form(){
   await page.locator('[data-action=password_reset]').click();
   assert((await page.locator('#action-impact').textContent()).includes(player.email));
   await page.locator('#action-reason').fill('Player requested recovery');
   await page.locator('#action-confirmation').fill(player.username);
  }
  for(const [width,height] of [[320,740],[390,844],[1440,1000]]){
   await page.setViewportSize({width,height});await open();await form();
   assert(!(await page.locator('#confirm-action').getAttribute('class')).includes('danger'));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   assert(await page.locator('#player-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth));
   await page.screenshot({path:`${output}/confirm-${process.env.TEST_BROWSER||'chrome'}-${width}.png`,fullPage:true});
   const before=requests.length;await page.locator('#confirm-action').click();
   await page.waitForSelector('#player-notice:not([hidden])');assert.equal(requests.length,before+1);
   assert(await page.locator('#action-form').isHidden());
   assert((await page.locator('#player-notice').textContent()).includes('Reset email sent'));
   await page.screenshot({path:`${output}/sent-${process.env.TEST_BROWSER||'chrome'}-${width}.png`,fullPage:true});
   console.log(`PASS admin recovery ${width}: confirmation, minimal payload, success, bounds`);
  }
  for(const [change,note] of [[{password_reset_configured:false},'not configured'],[{blocked_at:'2026-09-30'},'Unblock'],[{email:null},'no email']]){
   profile={...player,...change};await open();assert(await page.locator('[data-action=password_reset]').isDisabled());
   assert((await page.locator('#recovery-note').textContent()).includes(note));
  }
  profile={...player,is_guest:true};await page.goto(origin+'/internal/dashboard');await page.locator('[data-tab=players]').click();
  await page.locator('#player-table button').click();await page.waitForFunction(()=>document.querySelector('#player-title').textContent==='Guest');
  assert(await page.locator('#player-actions').isHidden());
  profile={...player};failure='The reset email could not be sent. Check email delivery and try again.';
  await open();await form();await page.locator('#confirm-action').click();await page.waitForSelector('#player-error:not([hidden])');
  assert.equal(await page.locator('#player-error').textContent(),failure);assert(await page.locator('#confirm-action').isEnabled());
  failure=null;delayed=true;const before=requests.length;await page.locator('#confirm-action').click();
  await page.waitForFunction(()=>document.querySelector('#confirm-action').disabled);
  assert(await page.locator('#cancel-action').isDisabled());
  assert(await page.locator('[data-action=delete]').isDisabled());
  // Closing a dialog while delivery is in flight must not reopen it on response.
  await page.locator('#close-player').click();
  assert.equal(requests.length,before+1);assert(release);release();delayed=false;
  await page.waitForTimeout(150);assert(await page.locator('#player-dialog').isHidden());
  await page.locator('#player-table button').click();await page.waitForSelector('#player-actions:not([hidden])');
  assert(await page.locator('[data-action=password_reset]').isEnabled());
  await page.locator('[data-action=block]').click();assert.equal(await page.locator('#confirm-action').textContent(),'Confirm');
  assert((await page.locator('#confirm-action').getAttribute('class')).includes('danger'));
  assert.deepEqual(errors,[]);console.log('PASS config, blocked/guest states, retry, in-flight close, existing actions');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
