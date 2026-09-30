/* Navigation must keep its geometry across routes, scrollbars and game states.
 * API responses are mocked; this suite never creates or changes a real account. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',engine=process.env.TEST_BROWSER||'chrome';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/private/tmp/on-the-dot-header';fs.mkdirSync(out,{recursive:true});
const profile={username:'header_player',email:'player@example.invalid',bio:'',club:null,level:1,total_xp:20,level_xp:0,next_level_xp:200,
 streak:{current:1,longest:1},stats:{wins:1,losses:0,played:1,win_rate:100},preferences:{animations:true,reduced_motion:false}};
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
async function geometry(page){
 return page.evaluate(()=>{
  const selectors=['.public-header','.points-brand','.brand-mark','.top-navigation','[data-nav-slot=leaderboard]','[data-nav-slot=profile]','[data-theme-toggle]','[data-sound-toggle]'];
  return Object.fromEntries(selectors.map(s=>{
   const r=document.querySelector(s).getBoundingClientRect();return [s,[r.x,r.y,r.width,r.height].map(n=>Math.round(n*100)/100)];
  }));
 });
}
async function fits(page){
 assert(await page.evaluate(()=>{
  const header=document.querySelector('.public-header'),r=header.getBoundingClientRect(),mark=header.querySelector('.points-brand').getBoundingClientRect();
  const controls=[...header.querySelectorAll('.top-navigation > *')].filter(e=>e.getClientRects().length).map(e=>e.getBoundingClientRect());
  return r.left>=0&&r.right<=innerWidth&&controls.every(c=>c.left>=mark.right+4&&c.right<=r.right+1&&c.top>=r.top&&c.bottom<=r.bottom)&&
   controls.every((c,i)=>controls.every((b,j)=>i===j||Math.min(c.right,b.right)-Math.max(c.left,b.left)<=1));
 }),'Header controls fit without collisions');
}
(async()=>{
 const browser=engine==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[320,568],[390,700],[768,1024],[800,900],[844,390],[1440,900],[2560,1440]])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];let signedIn=true,reference;
   await page.addInitScript(t=>localStorage.setItem('onthedot.theme',t),theme);
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    const p=new URL(route.request().url()).pathname;let data;
    if(p==='/api/players/me'||p.startsWith('/api/players/profiles/'))return route.fulfill({status:signedIn?200:401,json:signedIn?profile:{detail:'Sign in'}});
    if(p==='/api/players/settings')data={password_reset_available:true};
    else if(p==='/api/players/friends')data={friends:[]};
    else if(p==='/api/solo/catalog')data={topics:[{code:'ALL',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
    else if(p==='/api/daily/catalog')data={remaining:1000,ranked_available:true,rules};
    else if(p==='/api/solo/active'||p==='/api/daily/active')data={run:null};
    else if(p==='/api/friends/active')data={code:null};
    else if(p==='/api/community/leaderboard')data={board:'players',period:'all',metric:'xp',entries:[],me:null,participants:0,distribution:[],signed_in:true};
    else if(p==='/api/community/history')data={entries:[],total:0,signed_in:true};
    else {errors.push('Unexpected API '+p);return route.fulfill({status:404,json:{detail:'Missing mock'}});}
    await route.fulfill({json:data});
   });
   for(const path of ['/penalties','/account','/leaderboard','/history','/how-to-play','/daily','/friends','/u/header_player','/']){
    await page.goto(origin+path);await page.waitForLoadState('networkidle');await fits(page);
    reference??=await geometry(page);assert.deepEqual(await geometry(page),reference,`${engine} ${width} ${theme} ${path}`);
    await page.screenshot({path:`${out}/${engine}-${width}-${theme}-${path.replaceAll('/','_')||'home'}.png`});
    if(path==='/account'){
     await page.locator('[data-profile-tab=settings]').click();await page.evaluate(()=>scrollTo(0,0));
     assert.deepEqual(await geometry(page),reference,'Changing profile content must not change the header');
     await page.locator('[data-profile-dialog=email-dialog]').click();
     // CSS blur has no effect on the element's layout rectangle.
     await page.evaluate(()=>scrollTo(0,0));assert.deepEqual(await geometry(page),reference,'Dialog scroll lock must not shift the header');
     await page.locator('#email-dialog [data-close-dialog]').click();
    }
    if(path==='/penalties'){
     const slot=await page.locator('[data-nav-slot=play]:visible').boundingBox();
     // Real game animation is covered by test_stadium_inline_browser; here
     // exercise every shell state without waiting for a WebGL context.
     for(const state of ['shootout-active','shootout-finished','selection']){
      await page.evaluate(state=>{
       const main=document.querySelector('main');main.classList.remove('shootout-active','shootout-finished');
       if(state!=='selection')main.classList.add(state);
       document.querySelector('#motion-toggle').hidden=state==='selection';
      },state);
      await fits(page);assert.deepEqual(await geometry(page),reference,`Game state ${state}`);
      assert.deepEqual(await page.locator('[data-nav-slot=play]:visible').boundingBox(),slot,'Animation control uses the same reserved slot');
     }
    }
   }
   // Missing optional Home links must not pull the persistent icons sideways.
   await page.locator('[data-nav-slot=play]').evaluateAll(es=>es.forEach(e=>e.remove()));
   assert.deepEqual(await geometry(page),reference);
   signedIn=false;await page.goto(origin+'/account?mode=register');await page.waitForLoadState('networkidle');
   assert.deepEqual(await geometry(page),reference,'Guest registration has the same shell');
   assert.deepEqual(errors,[]);await page.close();console.log(`PASS ${engine} ${width} ${theme}: routes, content height, dialog, game states, guest`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
