/* Modal-only profile checks. All account requests are mocked, including writes. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const engine=process.env.TEST_BROWSER||'chrome',out='/private/tmp/on-the-dot-profile-dialogs';
fs.mkdirSync(out,{recursive:true});
const initial={username:'profile_player',email:'player@example.invalid',bio:'Football every day.',club:{team_id:33,name:'Manchester United'},
 total_xp:680,level:3,level_xp:600,next_level_xp:1200,streak:{current:3,longest:5},stats:{wins:7,losses:3,played:10,win_rate:70},
 preferences:{animations:true,reduced_motion:false},team_change:{can_change:true,next_change_at:null}};
const geometry=page=>page.evaluate(()=>({scroll:scrollY,height:document.querySelector('main').offsetHeight,
 boxes:['.public-header','.profile-title','.profile-progress','#profile-tabs','.site-footer'].map(s=>{
  const r=document.querySelector(s).getBoundingClientRect();return [r.x,r.y,r.width,r.height];
 })}));
async function cardFits(page,id){
 const result=await page.locator('#'+id).evaluate(d=>{
  const r=d.getBoundingClientRect(),h=d.querySelector('.profile-dialog-heading').getBoundingClientRect();
  return {modal:d.matches(':modal'),inside:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,
   heading:h.top>=r.top&&h.bottom<=r.bottom,noOverflow:d.scrollWidth<=d.clientWidth+1,focused:d.contains(document.activeElement),
   blurred:['#profile','.public-header','.page-return'].every(s=>getComputedStyle(document.querySelector(s)).filter==='blur(5px)')&&getComputedStyle(d).filter==='none'};
 });
 assert.deepEqual(result,{modal:true,inside:true,heading:true,noOverflow:true,focused:true,blurred:true});
}
(async()=>{
 const browser=engine==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[320,568],[390,700],[844,390],[1440,900]])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];let profile=structuredClone(initial),rejectEmail=false,releaseTeams;
   await page.addInitScript(t=>localStorage.setItem('onthedot.theme',t),theme);
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname,method=req.method();let data;
    if(path==='/api/players/me'){
     if(method==='PATCH')Object.assign(profile,req.postDataJSON());
     data=profile;
    }else if(path==='/api/players/settings')data={password_reset_available:true};
    else if(path==='/api/players/friends')data={friends:[]};
    else if(path==='/api/players/email'){
     if(rejectEmail)return route.fulfill({status:403,json:{detail:'Current password is incorrect.'}});
     profile.email=req.postDataJSON().email;data=profile;
    }else if(path==='/api/players/teams'){
     if(releaseTeams===null)await new Promise(resolve=>{releaseTeams=resolve;});
     data={teams:[{team_id:33,name:'Manchester United'},{team_id:42,name:'Arsenal'}]};
    }else {errors.push('Unexpected request '+path);return route.fulfill({status:404,json:{detail:'Missing mock'}});}
    await route.fulfill({json:data});
   });
   await page.goto(origin+'/account');await page.locator('#kit-form:not([hidden])').waitFor();
   await page.locator('[data-profile-tab=settings]').click();
   assert.equal(await page.locator('[data-profile-panel=settings] details').count(),0);
   const names=['email','profile','password','preferences','sound','delete'];
   for(const [index,name] of names.entries()){
    const id=name+'-dialog',trigger=page.locator(`[data-profile-dialog=${id}]`);
    await trigger.scrollIntoViewIfNeeded();const before=await geometry(page);
    await trigger.click();await cardFits(page,id);assert.deepEqual(await geometry(page),before,'Opening must not move the profile');
    for(let n=0;n<12;n++){
     await page.keyboard.press('Tab');
     // Native dialogs allow focus into browser chrome (reported as BODY),
     // but never into the inert profile controls behind the backdrop.
     const active=await page.locator('#'+id).evaluate(d=>({inside:d.contains(document.activeElement),tag:document.activeElement.tagName,id:document.activeElement.id}));
     assert(active.inside||active.tag==='BODY',`${id}: background received focus: ${JSON.stringify(active)}`);
    }
    await page.screenshot({path:`${out}/${engine}-${width}-${theme}-${name}.png`});
    if(index%3===0)await page.keyboard.press('Escape');
    else if(index%3===1)await page.locator(`#${id} [data-close-dialog]`).click();
    else await page.mouse.click(2,2);
    await page.locator('#'+id).waitFor({state:'hidden'});
    await page.waitForFunction(dialogId=>document.activeElement===document.querySelector(`[data-profile-dialog=${dialogId}]`),id);
    assert.deepEqual(await geometry(page),before,'Closing must not move the profile');
   }
   // Validation feedback belongs in the active card, not behind its backdrop.
   await page.locator('[data-profile-dialog=email-dialog]').click();rejectEmail=true;
   await page.locator('#email-password').fill('incorrect-password');
   await page.locator('#email-edit button[type=submit]').click();
   await page.locator('#email-edit-status').filter({hasText:'Current password is incorrect.'}).waitFor();
   assert(!await page.locator('#error').isVisible());rejectEmail=false;
   await page.locator('#account-email').fill('new@example.invalid');await page.locator('#email-edit button[type=submit]').click();
   await page.locator('#email-edit-status').filter({hasText:'Sign-in email saved.'}).waitFor();
   await page.locator('#email-dialog [data-close-dialog]').click();
   await page.locator('[data-profile-dialog=password-dialog]').click();await page.locator('#current-password').fill('private-password');
   await page.locator('#current-password').locator('..').getByRole('button').click();
   assert.equal(await page.locator('#current-password').getAttribute('type'),'text');
   await page.keyboard.press('Escape');await page.locator('[data-profile-dialog=password-dialog]').click();
   assert.equal(await page.locator('#current-password').inputValue(),'');assert.equal(await page.locator('#current-password').getAttribute('type'),'password');
   await page.keyboard.press('Escape');
   // Closing during a fetch must not reopen the card when the response arrives.
   await page.locator('[data-profile-tab=overview]').click();await page.locator('#add-team').scrollIntoViewIfNeeded();
   const beforeTeam=await geometry(page);releaseTeams=null;
   await page.locator('#add-team').click();await page.locator('#team-edit-status').filter({hasText:'Loading teams...'}).waitFor();
   await page.waitForFunction(()=>document.querySelector('#team-dialog').open);
   await page.locator('#team-dialog [data-close-dialog]').click();
   while(typeof releaseTeams!=='function')await new Promise(r=>setTimeout(r,10));
   const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/players/teams');releaseTeams();await response;
   assert(!await page.locator('#team-dialog').isVisible());assert.deepEqual(await geometry(page),beforeTeam);
   await page.locator('#add-team').click();await page.locator('#team-edit:not([hidden])').waitFor();await cardFits(page,'team-dialog');
   await page.locator('#cancel-team').click();assert.deepEqual(await geometry(page),beforeTeam);
   assert.deepEqual(errors,[]);await page.close();
   console.log(`PASS ${engine} ${width} ${theme}: six cards, stable layout, focus, feedback, secrets, team fetch cancellation`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
