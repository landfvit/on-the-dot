/* Profile/result presentation against mocked APIs: no account writes. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015',out='/tmp/on-the-dot-profile-xp';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
const profile={username:'onthedot_player',bio:'Premier League trivia, one penalty at a time.',email:'test@example.test',club:{team_id:33,name:'Manchester United'},
 total_xp:1050,level:3,level_xp:600,next_level_xp:1200,completed_quizzes:18,stats:{wins:12,losses:8,played:20,win_rate:60},streak:{current:4,longest:9},preferences:{animations:true,reduced_motion:false}};
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const before={total_xp:150,level:1,level_xp:0,next_level_xp:200},after={total_xp:650,level:3,level_xp:600,next_level_xp:1200};
const transition={earned_xp:500,before,after,levels:[{level:1,minimum_xp:0},{level:2,minimum_xp:200},{level:3,minimum_xp:600},{level:4,minimum_xp:1200}]};
let run;
function start(){run={run_id:'xp-test',phase:'ANSWERING',position:1,deadline:Date.now()+120000,role:'shooter',rules,category:{label:'All clubs'},difficulty:'medium',
 question:{text:'Which team plays at Old Trafford?',options:[{id:'0',text:'Manchester United'},{id:'1',text:'Arsenal'}]},review:[],correct:25,total_xp:500,base_xp:500,bonus_xp:0,multiplier:1,is_trial:false,
 shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},attempts:[],round:1,next_role:'keeper',winner:null,sudden_death:false}};}
async function greenPixels(locator){const {data,info}=await sharp(await locator.screenshot()).removeAlpha().raw().toBuffer({resolveWithObject:true});let n=0;for(let i=0;i<data.length;i+=info.channels)if(Math.abs(data[i]-136)<8&&Math.abs(data[i+1]-176)<8&&Math.abs(data[i+2]-75)<8)n++;return n;}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.stack));
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname;let data;
   if(path==='/api/players/me'||path.startsWith('/api/players/profiles/'))data=profile;
   else if(path==='/api/players/settings')data={password_reset_available:false};
   else if(path==='/api/players/friends')data={friends:[]};
   else if(path==='/api/solo/catalog')data={categories:[],topics:[{code:'ALL',counts_by_team:{ALL:{easy:50,medium:50,hard:50}}}],rules};
   else if(path==='/api/daily/catalog')data={remaining:1000,ranked_available:true,resets_at:new Date(Date.now()+86400000).toISOString(),rules};
   else if(['/api/solo/active','/api/daily/active'].includes(path))data={run:run?{...run,server_now:Date.now()}:null};
   else if(path.endsWith('/leave')){run={...run,phase:'ABANDONED',player_progress:after,xp_transition:transition,shootout:run.shootout?{...run.shootout,winner:'opponent'}:null};data=run;}
   else if(['/api/solo/runs/xp-test','/api/daily/runs/xp-test'].includes(path))data=run;
   else throw Error('Unexpected API '+path);
   await route.fulfill({json:data===run?{...data,server_now:Date.now()}:data});
  });
  for(const [width,height] of [[320,568],[390,844],[768,1024],[1440,1000]]){
   await page.setViewportSize({width,height});
   for(const theme of ['light','dark']){
    await page.goto(origin+'/account');await page.locator('#profile:not([hidden])').waitFor();
    await page.evaluate(theme=>{localStorage.setItem('onthedot.theme',theme);document.documentElement.dataset.theme=theme;},theme);
    assert.equal(await page.locator('#level-progress').evaluate(e=>e.value),450);assert((await greenPixels(page.locator('#level-progress')))>100);
    assert(await page.locator('#profile-record').isVisible());assert.equal(await page.locator('#profile-name').textContent(),profile.username);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:`${out}/profile-${width}-${theme}.png`,fullPage:true});
    await page.locator('[data-profile-tab=settings]').click();await page.getByText('Sound',{exact:true}).click();
    assert(await page.locator('#sound-volume').isVisible());assert(await page.locator('#level-progress').isVisible());
    assert(!await page.locator('#profile-stats').isVisible());assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:`${out}/settings-${width}-${theme}.png`,fullPage:true});
    await page.locator('[data-profile-tab=friends]').click();assert(await page.locator('#friend-add').isVisible());
   }
   console.log('PASS profile '+width+': XP pixels, overview/friends/settings, both themes');
  }
  await page.goto(origin+'/u/'+profile.username);await page.locator('#profile:not([hidden])').waitFor();
  assert(!await page.locator('#own-profile').isVisible());assert(!await page.locator('#profile-tabs').isVisible());assert(await page.locator('#public-add-friend').isVisible());
  await page.setViewportSize({width:390,height:664});start();await page.goto(origin+'/penalties');
  await page.waitForFunction(()=>window.PointsStadium?.inspect().active);
  await page.evaluate(()=>{window.levelCues=[];const play=PointsAudio.play;PointsAudio.play=name=>{levelCues.push(name);return play(name);};});
  await page.locator('#leave').click();
  await page.waitForFunction(()=>document.body.style.getPropertyValue('--stadium-result')==='1');
  const initial=await page.locator('#result-level-progress').evaluate(e=>e.value);assert(initial<200);
  await page.waitForFunction(()=>document.getElementById('result-level-label').textContent==='Level 3'&&document.getElementById('result-level-progress').value===50);
  assert.equal(await page.locator('#result-level-up').textContent(),'Level 3 unlocked!');
  assert.equal(await page.evaluate(()=>levelCues.filter(n=>n==='level-up').length),1);
  assert((await greenPixels(page.locator('#result-level-progress')))>10);
  assert(await page.locator('#summary').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight&&e.scrollHeight<=e.clientHeight+1));
  await page.screenshot({path:out+'/level-up-mobile.png'});
  await page.goto(origin+'/penalties?run=xp-test');await page.locator('#summary:not([hidden])').waitFor();
  assert.equal(await page.locator('#result-level-progress').evaluate(e=>e.value),50);assert(!await page.locator('#result-level-up').isVisible());
  assert.equal(await page.evaluate(()=>PointsAudio.inspect().state),'locked');
  start();run={...run,shootout:null,survival:{ranked:true,goals:0,mistakes:0,lives:3,max_lives:3}};
  await page.goto(origin+'/daily');await page.waitForFunction(()=>window.PointsStadium?.inspect().active);
  await page.locator('#leave').click();
  await page.waitForFunction(()=>document.getElementById('result-level-label').textContent==='Level 3'&&document.getElementById('result-level-progress').value===50);
  assert.equal(await page.locator('#result-level-up').textContent(),'Level 3 unlocked!');
  assert(await page.locator('#summary').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight&&e.scrollHeight<=e.clientHeight+1));
  await page.screenshot({path:out+'/daily-level-up-mobile.png'});
  assert.deepEqual(errors,[]);console.log('PASS Solo and Daily XP after outro, multi-level rollover, one level chime, no replay in history');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
