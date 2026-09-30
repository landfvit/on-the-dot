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
  let locked=false,exhausted=false,totalPlayers=3;
  await page.route('**/api/**',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;let data,status=200;
   if(path==='/api/players/me')data={...profile,team_change:{can_change:!locked,next_change_at:locked?new Date(Date.now()+72*3600000).toISOString():null}};
   else if(path==='/api/players/friends')data={friends:[]};
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
    const item={rank:1,xp:1234567,total_xp:1234567,level:23,streak:123,wins:321,win_rate:62.5,members:15,daily_highscore:42};
    const entry=board==='teams'?{...item,...club}:{...item,username:profile.username,club};
    const count=board==='teams'?1:totalPlayers,offset=Number(url.searchParams.get('offset')),limit=Number(url.searchParams.get('limit'));
    const entries=Array.from({length:Math.max(0,Math.min(limit,count-offset))},(_,i)=>({...entry,rank:offset+i+1,...(board==='players'?{username:offset+i?`player_${offset+i+1}`:profile.username}:{})}));
    data={board,metric,period,since:null,as_of:new Date().toISOString(),entries,me:entry,participants:count,signed_in:true,distribution:metric==='daily_highscore'?[]:[{minimum:0,label:'<100',count:0},{minimum:100,label:'100-249',count:0},{minimum:250,label:'250-499',count:0},{minimum:500,label:'500-999',count:0},{minimum:1000,label:'1,000+',count}]};
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
   if(await page.locator('#mode-intro').isVisible())await page.locator('#mode-intro button[value=play]').click();
   await page.waitForFunction(()=>document.getElementById('availability').textContent.startsWith('No new shootout'));
   assert.equal(starts.at(-1).category,'ALL');assert.equal(starts.at(-1).topic,'ALL');assert.equal(starts.at(-1).difficulty,'hard');
   assert(await page.locator('#start').isDisabled());assert(!/\d/.test(await page.locator('#availability').textContent()));
   await page.locator('input[name=difficulty][value=medium]').check();assert(await page.locator('#start').isEnabled());
   await page.goto(origin+'/leaderboard');await page.waitForSelector('#ranking-table:not([hidden])');
   assert.equal(rankRequests.at(-1).metric,'xp');assert.equal(rankRequests.at(-1).board,'players');
   assert.equal(await page.locator('input[name=period]').count(),0);
   assert.equal(await page.locator('#ranking-period').textContent(),'All time');
   assert.equal(await page.locator('#page-number').textContent(),'1 - 3 of 3');
   assert(await page.locator('#next-page').isDisabled());
   assert(await page.locator('#level-choice').isVisible());
   for(const board of ['players','teams']){
    await page.locator(`input[name=board][value=${board}]`).check();
    for(const metric of ['xp','streak','wins','win_rate','daily_highscore','level']){
     await page.locator(`input[name=metric][value=${metric}]`).check();
     await page.waitForFunction(({metric,board})=>{const t=document.getElementById('ranking-table');return t.dataset.metric===metric&&t.dataset.board===board&&!t.hidden;},{metric,board});
     assert.equal(await page.locator('#ranking-rows tr:first-child td').count(),3);
     assert.equal(rankRequests.at(-1).board,board);
     assert.equal(rankRequests.at(-1).period,'all');
     if(metric==='level'){
      assert.equal(await page.locator('#ranking-rows tr:first-child td:last-child').textContent(),'23');
      assert.equal(await page.locator('#rank-value').textContent(),'Levels');
     }
     assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
     const overflow=await page.locator('#ranking-table').evaluate(e=>e.scrollWidth>e.clientWidth+1);assert(!overflow);
    }
    for(const theme of ['light','dark']){
     await page.emulateMedia({colorScheme:theme});
     await page.waitForFunction(theme=>document.documentElement.dataset.theme===theme,theme);
     const layout=await page.locator('.community-page').evaluate(root=>{
      const box=selector=>root.querySelector(selector).getBoundingClientRect(),tabs=box('.ranking-tabs');
      const buttons=[...root.querySelectorAll('.ranking-tabs span')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,right:r.right,width:r.width,height:r.height,overflow:e.scrollWidth>e.clientWidth||e.scrollHeight>e.clientHeight};});
      return {width:tabs.width,left:tabs.left,right:tabs.right,buttons,boardGap:box('.board-tabs').top-box('#community-pagination').bottom,headingGap:tabs.top-document.querySelector('.page-return').getBoundingClientRect().bottom,boardWidth:box('.board-tabs').width,
       selected:getComputedStyle(root.querySelector('.ranking-tabs :checked+span')).backgroundColor,
       bars:[...root.querySelectorAll('.distribution-bar')].map(e=>getComputedStyle(e).backgroundColor)};
     });
     const columns=width<=600?2:3;
     assert.equal(layout.buttons.length,6);assert(layout.headingGap>=24);assert(layout.boardGap>=20);
     assert(Math.abs(layout.boardWidth-layout.width)<1);
     for(const b of layout.buttons){assert(!b.overflow);assert(b.height>=44);assert(Math.abs(b.width-(layout.width-(columns-1)*8)/columns)<1);}
     assert(Math.abs(layout.buttons[0].x-layout.left)<1);assert(Math.abs(layout.buttons[columns-1].right-layout.right)<1);
     assert.equal(layout.selected,theme==='dark'?'rgb(246, 243, 235)':'rgb(17, 17, 17)');
     assert(layout.bars.every(color=>color==='rgb(136, 176, 75)'));
     await page.screenshot({path:`${output}/${board}-${width}-${theme}.png`,fullPage:true});
    }
   }
   await page.locator('input[name=board][value=players]').check();
   await page.waitForFunction(()=>document.getElementById('rank-name').textContent==='Player'&&document.getElementById('ranking-table').dataset.metric==='level'&&!document.getElementById('ranking-table').hidden);
   assert(await page.locator('input[name=metric][value=level]').isChecked());
   assert.equal(rankRequests.at(-1).board,'players');
   totalPlayers=53;await page.reload();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='1 - 25 of 53');
   assert.equal(await page.locator('#ranking-rows tr').count(),25);assert(await page.locator('#previous-page').isDisabled());
   await page.locator('#next-page').click();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='26 - 50 of 53');
   assert.equal(await page.locator('#ranking-rows tr').count(),25);
   await page.locator('#next-page').click();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='51 - 53 of 53');
   assert.equal(await page.locator('#ranking-rows tr').count(),3);assert(await page.locator('#next-page').isDisabled());
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:`${output}/last-page-${width}.png`,fullPage:true});
   await page.locator('#previous-page').click();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='26 - 50 of 53');
   await page.locator('input[name=metric][value=wins]').check();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='1 - 25 of 53');
   totalPlayers=25;await page.reload();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='1 - 25 of 25');assert(await page.locator('#next-page').isDisabled());
   totalPlayers=0;await page.reload();await page.waitForFunction(()=>document.getElementById('page-number').textContent==='0 - 0 of 0');assert(await page.locator('#community-pagination').isVisible());assert(await page.locator('#next-page').isDisabled());
   totalPlayers=3;
   console.log(`PASS ${width}: all-time metrics, full-width controls, green charts, both themes and 25-row pagination`);
  }
  locked=true;await page.goto(origin+'/account');await page.waitForSelector('#own-profile:not([hidden])');
  assert(await page.locator('#add-team').isDisabled());assert.match(await page.locator('#team-change-note').textContent(),/change teams again.*UTC/);
  await page.screenshot({path:`${output}/team-cooldown.png`,fullPage:true});
  locked=false;await page.reload();await page.waitForSelector('#own-profile:not([hidden])');assert(await page.locator('#add-team').isEnabled());
  await page.locator('#add-team').click();await page.waitForSelector('#team-edit:not([hidden])');assert.equal(await page.locator('#team-options input').count(),3);
  assert.deepEqual(errors,[]);console.log('PASS team cooldown status and unchanged profile team picker');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
