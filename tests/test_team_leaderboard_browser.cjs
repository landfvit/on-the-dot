/* Local-only UI checks; every account/game API is mocked. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-teams';fs.mkdirSync(output,{recursive:true});
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const club={team_id:33,name:'Manchester United'};
const profile={username:'long_username_for_test',email:'example@example.com',bio:'',club,level:3,total_xp:360,level_xp:300,next_level_xp:1000,
 streak:{current:5,longest:7},stats:{wins:4,losses:2,played:6,win_rate:66.7},preferences:{animations:false,reduced_motion:true}};
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[],starts=[],rankRequests=[];page.on('pageerror',e=>errors.push(e.message));
  let locked=false,exhausted=false;
  await page.route('**/api/**',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;let data,status=200;
   if(path==='/api/players/me')data={...profile,team_change:{can_change:!locked,next_change_at:locked?new Date(Date.now()+72*3600000).toISOString():null}};
   else if(path==='/api/players/settings')data={password_reset_available:false};
   else if(path==='/api/players/teams')data={teams:[club,{team_id:40,name:'Liverpool'}]};
   else if(path==='/api/solo/catalog'){
    const counts={easy:99,medium:125,hard:exhausted?9:212};
    data={categories:[{code:'ALL',counts}],topics:[{code:'ALL',counts_by_team:{ALL:counts}}],rules,resets_at:'2099-09-28T00:00:00Z'};
   }else if(path==='/api/solo/active')data={run:null,trial_available:true};
   else if(path==='/api/solo/runs'){
    starts.push(route.request().postDataJSON());exhausted=true;status=409;
    data={detail:'No new shootout is available for this selection right now. Try a different difficulty.'};
   }else if(path==='/api/community/leaderboard'){
    const board=url.searchParams.get('board'),metric=url.searchParams.get('metric'),period=url.searchParams.get('period');rankRequests.push({board,metric,period});
    const item={rank:1,xp:1234567,total_xp:1234567,level:23,streak:123,wins:321,win_rate:62.5,members:15};
    const entry=board==='teams'?{...item,...club}:{...item,username:profile.username,club};
    data={board,metric,period,since:null,as_of:new Date().toISOString(),entries:[entry],me:entry,participants:1,signed_in:true,distribution:[{minimum:1000,label:'1,000+',count:1}]};
   }else throw Error('Unexpected API '+path);
   await route.fulfill({status,json:data});
  });
  for(const [width,height] of [[320,568],[390,844],[768,1024],[1440,1000]]){
   exhausted=false;await page.setViewportSize({width,height});await page.goto(origin+'/penalties');
   await page.waitForFunction(()=>!document.getElementById('start').disabled);
   assert.equal(await page.locator('#selection select').count(),0);
   assert.equal(await page.locator('#selection input[type=radio]').count(),3);
   assert(!/available questions|unused approved|\d+ available/.test(await page.locator('#selection').innerText()));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:`${output}/selection-${width}.png`,fullPage:true});
   await page.locator('input[name=difficulty][value=hard]').check();await page.locator('#start').click();
   await page.waitForFunction(()=>document.getElementById('availability').textContent.startsWith('No new shootout'));
   assert.equal(starts.at(-1).category,'ALL');assert.equal(starts.at(-1).topic,'ALL');assert.equal(starts.at(-1).difficulty,'hard');
   assert(await page.locator('#start').isDisabled());assert(!/\d/.test(await page.locator('#availability').textContent()));
   await page.locator('input[name=difficulty][value=medium]').check();assert(await page.locator('#start').isEnabled());
   await page.goto(origin+'/leaderboard');await page.waitForSelector('#ranking-table:not([hidden])');
   assert.equal(rankRequests.at(-1).metric,'xp');assert.equal(rankRequests.at(-1).board,'players');
   assert.equal(await page.locator('#team-level-choice').isVisible(),false);
   for(const board of ['players','teams']){
    await page.locator(`input[name=board][value=${board}]`).check();
    for(const metric of board==='teams'?['xp','streak','wins','win_rate','level']:['xp','streak','wins','win_rate']){
     await page.locator(`input[name=metric][value=${metric}]`).check();
     await page.waitForFunction(metric=>document.getElementById('ranking-table').dataset.metric===metric&&!document.getElementById('ranking-table').hidden,metric);
     assert.equal(await page.locator('#ranking-rows tr:first-child td').count(),3);
     assert.equal(rankRequests.at(-1).board,board);
     if(['level','streak'].includes(metric))assert.equal(rankRequests.at(-1).period,'all');
     assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
     const overflow=await page.locator('#ranking-table').evaluate(e=>e.scrollWidth>e.clientWidth+1);assert(!overflow);
    }
    await page.screenshot({path:`${output}/${board}-${width}.png`,fullPage:true});
   }
   await page.locator('input[name=board][value=players]').check();
   await page.waitForFunction(()=>document.getElementById('ranking-table').dataset.metric==='xp'&&!document.getElementById('ranking-table').hidden);
   assert(await page.locator('input[name=metric][value=xp]').isChecked());
   console.log(`PASS ${width}: difficulty-only selection, mixed payload, all ranking metrics, no overflow`);
  }
  locked=true;await page.goto(origin+'/account');await page.waitForSelector('#own-profile:not([hidden])');
  assert(await page.locator('#add-team').isDisabled());assert.match(await page.locator('#team-change-note').textContent(),/change teams again.*UTC/);
  await page.screenshot({path:`${output}/team-cooldown.png`,fullPage:true});
  locked=false;await page.reload();await page.waitForSelector('#own-profile:not([hidden])');assert(await page.locator('#add-team').isEnabled());
  await page.locator('#add-team').click();await page.waitForSelector('#team-edit:not([hidden])');assert.equal(await page.locator('#team-options input').count(),3);
  assert.deepEqual(errors,[]);console.log('PASS team cooldown status and unchanged profile team picker');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
