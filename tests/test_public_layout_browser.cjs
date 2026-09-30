/* Local presentation audit. All account/game APIs are mocked; no real writes. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/private/tmp/on-the-dot-ui-audit';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
const meta=require(process.cwd()+'/trivia_app/static/public_metadata.json');
const profile={username:'long_username_1234567890',email:'player@example.invalid',bio:'Premier League football.',club:{team_id:64,name:'Hull City'},outfit:{kit_id:'64-2026-home',number:88},
 total_xp:1234567,level:99,level_xp:1234000,next_level_xp:1235000,completed_quizzes:888,stats:{wins:999,losses:888,played:1887,win_rate:52.9},streak:{current:123,longest:456},team_change:{can_change:true,next_change_at:null},preferences:{animations:true,reduced_motion:false}};
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const problems=[],errors=[];
async function audit(page,name){
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const issues=await page.evaluate(()=>{
  const found=[],visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden],.sr-only')&&
   [...document.querySelectorAll('details:not([open])')].every(d=>!d.contains(e)||d.querySelector('summary')?.contains(e)),box=e=>e.getBoundingClientRect();
  if(document.documentElement.scrollWidth>innerWidth+1)found.push('horizontal page overflow');
  const header=document.querySelector('.public-header'),main=document.querySelector('main');
  if(main&&[...main.querySelectorAll('h1')].some(visible))found.push('visible page title');
  if(header&&main){const a=box(header),b=box(main),s=getComputedStyle(main);
   if(Math.abs(a.left-b.left-parseFloat(s.paddingLeft))>1||Math.abs(a.right-b.right+parseFloat(s.paddingRight))>1)found.push('main edges differ from header');}
  for(const e of document.querySelectorAll('button,a,summary,th,td,.metric,.period-tabs span,.xp-caption span')){
   if(!visible(e))continue;const r=box(e),s=getComputedStyle(e);
   if(r.left< -1||r.right>innerWidth+1)found.push('offscreen '+(e.id||e.textContent.trim().slice(0,45)));
   if(e.scrollWidth>e.clientWidth+2&&s.display!=='inline'&&s.overflowX==='visible')found.push('overflow '+(e.id||e.textContent.trim().slice(0,45)));
  }
  // Leaf controls must not collide with siblings; ancestor command links and
  // deliberate input adornments are excluded from the pairwise comparison.
  const controls=[...document.querySelectorAll('button,a,summary,.period-tabs label,.difficulty-options label')].filter(e=>visible(e)&&!e.closest('[role=tooltip]'));
  for(let i=0;i<controls.length;i++)for(let j=i+1;j<controls.length;j++){
   const a=controls[i],b=controls[j];if(a.contains(b)||b.contains(a)||a.closest('dialog')!==b.closest('dialog'))continue;
   const x=box(a),y=box(b),w=Math.min(x.right,y.right)-Math.max(x.left,y.left),h=Math.min(x.bottom,y.bottom)-Math.max(x.top,y.top);
   if(w>2&&h>2)found.push('controls overlap '+(a.id||a.textContent.trim().slice(0,20))+' / '+(b.id||b.textContent.trim().slice(0,20)));
  }
  return [...new Set(found)];
 });
 if(issues.length)problems.push({name,issues});
 await page.screenshot({path:`${out}/${name}.png`,fullPage:true});
}
(async()=>{
 const browser=process.env.TEST_BROWSER==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[320,568],[390,700],[768,1024],[844,390],[1440,900]])for(const theme of ['light','dark']){
   const page=await browser.newPage({viewport:{width,height}});let signedIn=true;
   await page.addInitScript(t=>localStorage.setItem('onthedot.theme',t),theme);
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    const u=new URL(route.request().url()),p=u.pathname;let data;
    if(p==='/api/players/me'||p.startsWith('/api/players/profiles/'))return route.fulfill({status:signedIn?200:401,json:signedIn?profile:{detail:'Sign in'}});
    if(p==='/api/players/settings')data={password_reset_available:true};
    else if(p==='/api/players/friends')data={friends:[
     {username:'friend_username_123456789',status:'accepted',invite:'/friends?code=test'},
     {username:'incoming_player_123456789',status:'pending',incoming:true},
     {username:'outgoing_player_123456789',status:'pending',incoming:false}]};
    else if(p==='/api/players/teams')data={teams:meta.clubs};
    else if(p==='/api/solo/catalog')data={topics:[{code:'ALL',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
    else if(p==='/api/daily/catalog')data={remaining:1000,ranked_available:true,resets_at:'2099-01-01T00:00:00Z',rules};
    else if(p==='/api/solo/active'||p==='/api/daily/active')data={run:null};
    else if(p==='/api/friends/active')data={code:null};
    else if(p==='/api/community/leaderboard'){
     const board=u.searchParams.get('board')||'players';
     data={board,period:'all',metric:u.searchParams.get('metric')||'xp',participants:2,signed_in:true,
      entries:[{...profile,rank:1,xp:1234567,wins:999,win_rate:52.9,daily_highscore:999,streak:123,...(board==='teams'?{team_id:35,name:'AFC Bournemouth',members:999}:{} )}],me:null,
      distribution:[{label:'0–99',count:0},{label:'100–249',count:0},{label:'250–499',count:0},{label:'500–999',count:0},{label:'1,000+',count:2}]};
    }else if(p==='/api/community/history')data={entries:[],total:0,signed_in:true};
    else {errors.push('Unexpected API '+p);return route.fulfill({status:404,json:{detail:'Missing test route'}});}
    return route.fulfill({json:data});
   });
   for(const [name,path] of [['home','/'],['guide','/how-to-play'],['solo','/penalties'],['daily','/daily'],['duel','/friends'],['board','/leaderboard'],['history','/history'],['profile','/account']]){
    await page.goto(origin+path);await page.waitForLoadState('networkidle');
    await audit(page,`${width}-${theme}-${name}`);
    if(name==='profile'){
     await page.locator('#add-team').click();await page.locator('#team-edit:not([hidden])').waitFor();await audit(page,`${width}-${theme}-team-picker`);
     await page.locator('#cancel-team').click();
     await page.locator('[data-profile-tab=friends]').click();await page.locator('.friend-row').first().waitFor();await audit(page,`${width}-${theme}-friends`);
     await page.locator('[data-profile-tab=settings]').click();
     await audit(page,`${width}-${theme}-settings`);
     for(const setting of ['email','profile','password','preferences','sound']){
      await page.locator(`[data-profile-dialog=${setting}-dialog]`).click();await audit(page,`${width}-${theme}-${setting}-dialog`);
      await page.locator(`#${setting}-dialog [data-close-dialog]`).click();
     }
     await page.locator('#delete-open').click();await audit(page,`${width}-${theme}-delete`);await page.locator('#delete-cancel').click();
    }
   }
   signedIn=false;await page.goto(origin+'/account');await page.locator('#authentication:not([hidden])').waitFor();await audit(page,`${width}-${theme}-signin`);
   await page.goto(origin+'/account?mode=register');await page.locator('#authentication:not([hidden])').waitFor();await audit(page,`${width}-${theme}-register`);
   await page.goto(origin+'/daily');await page.locator('#mode-auth:not([hidden])').waitFor();await audit(page,`${width}-${theme}-daily-guest`);
   await page.close();console.log(`Checked ${width} ${theme}`);
  }
 }finally{await browser.close();}
 fs.writeFileSync(`${out}/report.json`,JSON.stringify({problems,errors},null,2));console.log(JSON.stringify({problems,errors}));
 if(process.env.AUDIT_STRICT){assert.deepEqual(errors,[]);assert.deepEqual(problems,[]);}
})().catch(e=>{console.error(e);process.exitCode=1;});
