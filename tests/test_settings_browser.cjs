/* Local UI checks with mocked API: no real users or email delivery. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-settings';fs.mkdirSync(output,{recursive:true});
const metadata=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/public_metadata.json')));
const initial={username:'matchday_player',email:'player@example.com',bio:'Football every day.',club:{team_id:33,name:'Manchester United'},
  level:3,total_xp:680,level_xp:600,next_level_xp:1200,streak:{current:3,longest:5},stats:{wins:7,losses:3,played:10,win_rate:70},
  preferences:{animations:true,reduced_motion:false}};
(async()=>{
 const browser=process.env.TEST_BROWSER==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));let signedIn=true,profile=structuredClone(initial),resetToken;
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname,method=route.request().method(),body=method==='GET'?{}:route.request().postDataJSON();let data={},status=200;
   if(path==='/api/players/me'&&method==='GET'){data=signedIn?profile:{detail:'Sign in'};status=signedIn?200:401;}
   else if(path==='/api/players/me'&&method==='PATCH'){assert.deepEqual(Object.keys(body),['bio']);Object.assign(profile,body);data=profile;}
   else if(path==='/api/players/me'&&method==='DELETE'){assert.equal(body.confirmation,'DELETE');signedIn=false;data={deleted:true};}
   else if(path==='/api/players/settings')data={password_reset_available:true};
   else if(path==='/api/players/friends')data={friends:[]};
   else if(path==='/api/players/password'){assert.equal(body.current_password,'current-password');data={changed:true};}
   else if(path==='/api/players/preferences'){profile.preferences=body;data=body;}
   else if(path==='/api/players/teams')data={teams:metadata.clubs};
   else if(path==='/api/players/me/team'){profile.club=metadata.clubs.find(t=>t.team_id===body.team_id)||null;data=profile;}
   else if(path==='/api/players/password-reset/request')data={message:'If an account uses this email, a reset link will arrive shortly.'};
   else if(path==='/api/players/password-reset/confirm'){resetToken=body.token;data={changed:true};}
   else if(path==='/api/community/leaderboard')data={entries:[{...profile,rank:1,wins:7,losses:3,win_rate:70}],me:null,participants:1,distribution:[],period:'all',metric:'level',signed_in:false};
   else if(path==='/api/solo/catalog')data={categories:[{code:'ALL',label:'All clubs',counts:{easy:100,medium:100,hard:100}}],
     topics:[{code:'ALL',label:'Mixed topics',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],
     rules:{format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}}};
   else if(path==='/api/solo/active')data={run:null,trial_available:true};
   else {errors.push('Unexpected '+method+' '+path);status=404;}
   await route.fulfill({status,json:data});
  });
  for(const [width,height] of [[390,844],[1440,1000]]){
   await page.setViewportSize({width,height});await page.goto(origin+'/account');await page.waitForSelector('#own-profile:not([hidden])');
   await page.locator('#add-team').click();await page.waitForSelector('#team-options input');
   assert.equal(await page.locator('#team-options input').count(),metadata.clubs.length+1);
   await page.waitForFunction(()=>[...document.querySelectorAll('#team-options img')].every(i=>i.complete&&i.naturalWidth>0));
   await page.getByRole('radio',{name:'Arsenal',exact:true}).check();await page.locator('#save-team').click();
   await page.waitForFunction(()=>document.querySelector('#profile-team img')?.alt==='Arsenal');
   await page.locator('[data-profile-tab=settings]').click();await page.locator('[data-profile-dialog=profile-dialog]').click();
   assert(await page.locator('#profile-username').evaluate(e=>e.readOnly));
   assert.equal(await page.locator('#profile-username').inputValue(),initial.username);
   await page.locator('#bio').fill('Updated bio');await page.locator('#profile-edit button[type=submit], #profile-edit button.primary').click();
   await page.waitForFunction(()=>document.querySelector('#profile-bio').textContent==='Updated bio');
   assert.equal(await page.locator('#profile-name').textContent(),initial.username);
   await page.locator('#profile-dialog [data-close-dialog]').click();
   await page.locator('[data-profile-dialog=password-dialog]').click();
   await page.locator('#current-password').fill('current-password');
   const toggle=page.locator('#current-password').locator('..').getByRole('button');await toggle.click();assert.equal(await page.locator('#current-password').getAttribute('type'),'text');await toggle.click();
   await page.locator('#new-password').fill('new-password');await page.locator('#confirm-password').fill('new-password');
   await page.locator('#password-edit').getByRole('button',{name:'Change password',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#password-status').textContent.includes('Password changed'));
   await page.locator('#password-dialog [data-close-dialog]').click();
   await page.locator('[data-profile-dialog=preferences-dialog]').click();
   await page.locator('#setting-animations').uncheck();await page.locator('#setting-reduced-motion').check();await page.locator('#preferences-edit button').click();
   await page.waitForFunction(()=>document.querySelector('#preferences-status').textContent==='Preferences saved.');
   assert.equal(await page.evaluate(()=>PointsPreferences.get().animations),false);
   await page.locator('#preferences-dialog [data-close-dialog]').click();
   await page.locator('#delete-open').click();assert(await page.locator('#delete-dialog').isVisible());await page.locator('#delete-cancel').click();
   await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${output}/account-${width}.png`,fullPage:true});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   console.log(`PASS account ${width}: club badges, permanent username, bio, password, preferences and delete confirmation`);
  }
  signedIn=false;await page.setViewportSize({width:390,height:844});await page.goto(origin+'/account');
  await page.locator('#forgot-password').click();await page.locator('#reset-email').fill('player@example.com');await page.locator('#reset-request button').first().click();
  await page.waitForFunction(()=>document.querySelector('#reset-status').textContent.includes('reset link'));
  const token='a'.repeat(43);await page.goto(origin+'/account#reset='+token);await page.waitForSelector('#reset-confirm:not([hidden])');
  assert(!page.url().includes(token));await page.locator('#reset-new-password').fill('reset-password');await page.locator('#reset-confirm button:not(.password-toggle)').click();
  await page.waitForFunction(()=>document.querySelector('#reset-status').textContent.includes('Password reset'));assert.equal(resetToken,token);
  await page.goto(origin+'/leaderboard?ad_preview=1');await page.waitForSelector('#ranking-rows .club-badge');
  assert.equal(await page.locator('[data-ad-slot]:visible').count(),1);await page.screenshot({path:`${output}/leaderboard-ads.png`,fullPage:true});
  await page.goto(origin+'/penalties?ad_preview=1');assert.equal(await page.locator('[data-ad-slot]:visible').count(),1);
  assert.match(await page.locator('.site-footer').textContent(),/PL Seasons 16\/17 - 25\/26/);
  await page.screenshot({path:`${output}/selection-ads.png`,fullPage:true});
  await page.goto(origin+'/penalties');assert.equal(await page.locator('[data-ad-slot]:visible').count(),0);
  signedIn=true;await page.goto(origin+'/account');await page.locator('[data-profile-tab=settings]').click();await page.locator('#delete-open').click();await page.locator('#delete-password').fill('current-password');await page.locator('#delete-confirmation').fill('DELETE');
  await page.locator('#delete-account .danger-button').click();await page.waitForURL('**/penalties');assert(!signedIn);
  assert.deepEqual(errors,[]);console.log('PASS recovery, token privacy, ad placements, seasons and deletion');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
