/* Run against a local uvicorn preview with Playwright available on NODE_PATH:
 * MOBILE_TEST_URL=http://127.0.0.1:8013 node tests/test_mobile_layout.cjs
 * All API traffic is mocked. No accounts, games or database rows are created.
 */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const sharp=require('sharp');
const fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname),'Local preview only');
const artifacts=process.env.MOBILE_TEST_ARTIFACTS||'/tmp/on-the-dot-mobile';
fs.mkdirSync(artifacts,{recursive:true});
const longest='What was the outcome of Brighton & Hove Albion\u2019s home Premier League meeting with Wolverhampton Wanderers in 2022/23: a Brighton & Hove Albion win, a draw, or a Wolverhampton Wanderers win?';
const options=['Brighton & Hove Albion','Wolverhampton Wanderers','Manchester United','Draw'].map((text,i)=>({id:String(i),text}));
const explanation='Brighton & Hove Albion. Recorded result: Brighton & Hove Albion 6\u20130 Wolverhampton Wanderers, 2022/23 Premier League. Home club is written first.';
const rules={answer_ms:15000,xp_per_correct:10,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4},bonus_mode:'win',format:'shootout'};
const catalog={categories:[{code:'ALL',label:'All clubs',counts:{easy:100,medium:100,hard:100}}],topics:[{code:'ALL',label:'Mixed topics',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
let run,failPoll=false,guest=false;
function start(){run={run_id:'layout-test',server_now:Date.now(),phase:'ANSWERING',position:1,deadline:Date.now()+120000,
  category:{label:'All clubs',topic_label:'Match recognition'},difficulty:'easy',rules,role:'shooter',review:[],
  question:{text:longest,options},total_xp:0,base_xp:0,bonus_xp:0,multiplier:1,correct:0,is_trial:false,
  shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},attempts:[],round:1,next_role:'keeper',winner:null,sudden_death:false}};}

async function geometry(page){
  return page.evaluate(()=>{
    const ids=['question-title','choices','feedback','next','leave','shootout-board','stadium-controls'];
    const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom};};
    const boxes=Object.fromEntries(ids.map(id=>[id,rect(document.getElementById(id))]));
    const overflow=[];
    for(const e of [document.querySelector('.solo-questions'),document.querySelector('#question-panel'),document.querySelector('#question-title'),...document.querySelectorAll('#choices button')]){
      if(e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1)overflow.push({id:e.id||e.textContent,scroll:[e.scrollWidth,e.scrollHeight],size:[e.clientWidth,e.clientHeight]});
    }
    const textFits=[...document.querySelectorAll('#choices button')].every(e=>e.getBoundingClientRect().height>=44);
    return {boxes,overflow,textFits,bodyOverflow:document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight,
      camera:rect(document.querySelector('#stadium-framing')),viewport:[innerWidth,innerHeight]};
  });
}
function stable(a,b){for(const id of ['question-title','choices','next','leave'])for(const key of ['x','y','width','height'])assert(Math.abs(a.boxes[id][key]-b.boxes[id][key])<1,`${id} moved: ${JSON.stringify([a.boxes[id],b.boxes[id]])}`);}
function fits(g){
  assert.deepEqual(g.overflow,[],JSON.stringify(g));assert(!g.bodyOverflow);assert(g.textFits);
  const button=g.boxes.leave,board=g.boxes['shootout-board'];
  assert(button.height>=44);assert(button.x>=board.x+board.width+4,'Forfeit must sit beside the score');
  assert(Math.abs(button.y-board.y)<1,'Forfeit and score share a top edge');
  assert(button.x+button.width<=g.viewport[0]&&button.bottom<=g.viewport[1]);
  assert(button.y>=g.boxes['stadium-controls'].bottom,'Forfeit must not overlap the top toolbar');
  assert(g.camera.height>50&&g.camera.width>100);
}

(async()=>{
  const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
  try{
    const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      let data,status=200;
      if(path==='/api/players/me'){data=guest?{detail:'Sign in'}:{username:'Mobile tester',level:1,total_xp:0};status=guest?401:200;}
      else if(path==='/api/solo/catalog')data=catalog;
      else if(path==='/api/solo/active')data={run,trial_available:false};
      else if(path.endsWith('/answers')){
        run.phase='REVIEW';run.total_xp+=10;run.correct++;run.review.push({position:run.position,option_id:'0',correct:'0',is_correct:true,outcome:run.role==='keeper'?'save':'goal',explanation,text:run.question.text});
        run.shootout.player=1;run.shootout.kicks.player=1;run.shootout.attempts=[{side:'player',goal:true,number:1}];data=run;
      }else if(path.endsWith('/next')){
        run.phase='ANSWERING';run.position++;run.role='keeper';run.question={text:'Who won the Premier League in 2017/18?',options:options.slice(0,3)};run.deadline=Date.now()+120000;data=run;
      }else if(path.endsWith('/leave')){run.phase='ABANDONED';run.shootout.winner='opponent';data=run;}
      else if(path==='/api/solo/runs/layout-test'){
        if(failPoll){status=503;data={detail:'Connection lost. Please reconnect.'};}else data=run;
      }else throw new Error(`Unexpected API ${path}`);
      await route.fulfill({status,json:{...data,...(data===run?{server_now:Date.now()}:{})}});
    });
    for(const [width,height] of [[320,568],[360,640],[375,667],[390,664],[390,844],[430,932],[768,1024],[568,320],[667,375],[844,390]]){
      start();
      if(width===320||width===568){run.shootout.kicks={player:9,opponent:9};run.shootout.sudden_death=true;}
      await page.setViewportSize({width,height});await page.goto(origin+'/penalties');
      await page.waitForFunction(()=>window.PointsStadium?.inspect().active&&!window.PointsStadium.inspect().entering);
      await page.waitForTimeout(250);
      const before=await geometry(page);fits(before);
      assert.equal(await page.locator('#question-title').evaluate(e=>getComputedStyle(e).fontWeight),'550');
      assert((await page.locator('#choices button').evaluateAll(es=>es.map(e=>Number(getComputedStyle(e).fontWeight)))).every(w=>w===700));
      assert.equal(await page.locator('#leave').textContent(),'Forfeit');
      assert.equal(await page.locator('#question-panel #leave').count(),0);
      assert.equal(await page.locator('#leave').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 111, 97)');
      assert.equal(await page.locator('.run-meta,#run-category,#run-xp,.solo-score,#penalty-score').count(),0);
      assert.equal(await page.locator('#motion-toggle').getAttribute('aria-pressed'),'false');
      assert(await page.locator('#motion-toggle').isDisabled(),'Respect system reduced motion');
      const centers=await page.locator('#stadium-controls .icon-button').evaluateAll(es=>es.map(e=>{
        const a=e.getBoundingClientRect(),b=e.querySelector('img').getBoundingClientRect();
        return [Math.abs(a.x+a.width/2-b.x-b.width/2),Math.abs(a.y+a.height/2-b.y-b.height/2),a.width,a.height];
      }));
      assert(centers.length===3&&centers.every(([x,y,w,h])=>x<1&&y<1&&w===h),JSON.stringify(centers));
      if(width===390&&height===664){
        await page.locator('#stadium-controls [data-theme-toggle]').click();
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().theme),'dark');
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().markingsColor),0xffffff);
        stable(before,await geometry(page));
        await page.screenshot({path:`${artifacts}/dark-live-game.png`});
        await page.locator('#stadium-controls [data-theme-toggle]').click();
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().theme),'light');
      }
      await page.locator('#choices button').first().click();
      await page.waitForFunction(()=>!document.getElementById('next').hidden&&!document.getElementById('next').disabled);
      await page.waitForTimeout(150);
      const after=await geometry(page);fits(after);stable(before,after);
      assert.equal(await page.locator('#feedback').textContent(),'');
      assert.equal(await page.locator('.answer-selection').count(),0);
      const chosen=page.locator('#choices button.chosen');
      assert.equal(await chosen.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(136, 176, 75)');
      assert.equal(await chosen.evaluate(e=>getComputedStyle(e).color),'rgb(17, 17, 17)');
      assert.equal(await chosen.evaluate(e=>getComputedStyle(e).borderRadius),'6px');
      if(await page.locator('#feedback-expand').isVisible()){
        await page.locator('#feedback-expand').click();assert.equal(await page.locator('#feedback-full').textContent(),run.question.options[0].text);
        await page.locator('#feedback-close').click();stable(after,await geometry(page));
      }
      await page.screenshot({path:`${artifacts}/${width}x${height}-review.png`});
      await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#question-title').textContent.startsWith('Who won'));
      await page.waitForTimeout(100);const next=await geometry(page);fits(next);stable(before,next);
      // No scroll movement after attempting a touch/wheel-style scroll.
      await page.mouse.wheel(0,350);await page.waitForTimeout(50);stable(next,await geometry(page));
      assert.equal(await page.evaluate(()=>scrollY),0);
      if(width===320||width===568){
        await page.evaluate(()=>{
          document.getElementById('shootout-board').dataset.mode='friend';
          document.getElementById('name-player').textContent='w'.repeat(24);
          document.getElementById('name-opponent').textContent='friend_with_a_long_name';
        });
        fits(await geometry(page));
        assert(await page.locator('#shootout-board').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
        await page.screenshot({path:`${artifacts}/forfeit-long-names-${width}.png`});
      }
      console.log(`PASS ${width}x${height}: question, answers, review and Next stay fixed`);
    }
    // A server error must retain the grid and offer a reachable Reconnect.
    failPoll=true;await page.waitForSelector('#retry:not([hidden])');const disconnected=await geometry(page);fits(disconnected);
    assert(await page.locator('#retry').isVisible());failPoll=false;await page.locator('#retry').click();await page.waitForSelector('#retry[hidden]',{state:'attached'});
    await page.locator('#leave').click();await page.waitForSelector('#summary:not([hidden])');
    await page.waitForFunction(()=>document.body.classList.contains('stadium-ending'));
    assert.equal(await page.locator('#question-panel').isVisible(),false);
    await page.locator('#another').click();assert(await page.locator('#selection').isVisible());
    assert.equal(await page.locator('#shootout-board').isVisible(),false);
    // Desktop remains a normal side panel, not the mobile grid.
    await page.setViewportSize({width:1440,height:900});start();run.deadline=Date.now()+15000;await page.goto(origin+'/penalties');
    await page.waitForFunction(()=>window.PointsStadium?.inspect().active);
    assert.equal(await page.locator('#question-panel').evaluate(e=>getComputedStyle(e).display),'block');
    assert.equal(await page.locator('#stadium-clock,#stadium-score,#stadium-role').count(),0);
    assert.match(await page.locator('#seconds').textContent(),/^\d+ s$/);
    const beforeTime=await page.locator('#timer').evaluate(e=>e.value);
    async function greenBarPixels(){
      const {data,info}=await sharp(await page.locator('#timer').screenshot()).removeAlpha().raw().toBuffer({resolveWithObject:true});
      let green=0;for(let i=0;i<data.length;i+=info.channels)if(Math.abs(data[i]-136)<8&&Math.abs(data[i+1]-176)<8&&Math.abs(data[i+2]-75)<8)green++;
      return green;
    }
    const beforePixels=await greenBarPixels();assert(beforePixels>100,'Timer must be visibly green');
    await page.waitForTimeout(1800);
    assert((await page.locator('#timer').evaluate(e=>e.value))<beforeTime-1);
    assert((await greenBarPixels())<beforePixels*.96,'Rendered green bar must shrink, not just its value');
    for(const theme of ['dark','light']){
      await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
      assert.equal(await page.locator('#choices button').first().evaluate(e=>getComputedStyle(e).backgroundColor),'rgba(0, 0, 0, 0)');
      assert.equal(await page.locator('#choices button').first().evaluate(e=>getComputedStyle(e).color),theme==='dark'?'rgb(246, 243, 235)':'rgb(17, 17, 17)');
      assert.equal(await page.locator('#leave').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 111, 97)');
      assert.equal(await page.locator('#leave').evaluate(e=>getComputedStyle(e).borderRadius),'999px');
      assert((await greenBarPixels())>100);
    }
    console.log('PASS integer seconds, no duplicate HUD, shrinking green timer, red Forfeit pill in both themes');
    await page.screenshot({path:`${artifacts}/desktop.png`});
    run.deadline=Date.now()+120000;
    // Verify pixels in the actual 3D framing region, including a moving shot.
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.waitForFunction(()=>!document.getElementById('motion-toggle').disabled);
    assert.equal(await page.locator('#motion-toggle').getAttribute('aria-pressed'),'true');
    await page.evaluate(async()=>{await PointsStadium.enter('keeper',{intro:false});});
    const frame=await page.locator('#stadium-framing').boundingBox();
    const clip={x:Math.ceil(frame.x),y:Math.ceil(frame.y),width:Math.floor(frame.width),height:Math.floor(frame.height)};
    const still=await page.screenshot({clip});
    const stats=await sharp(still).stats();assert(stats.channels.slice(0,3).some(c=>c.stdev>10),'Stadium pixels are blank');
    const {data:rgb,info}=await sharp(still).removeAlpha().raw().toBuffer({resolveWithObject:true});
    let greenPixels=0;
    for(let i=0;i<rgb.length;i+=info.channels)if(Math.abs(rgb[i]-136)<20&&Math.abs(rgb[i+1]-176)<20&&Math.abs(rgb[i+2]-75)<20)greenPixels++;
    assert(greenPixels>info.width*info.height*.05,'Pitch does not render the supplied green');
    await page.evaluate(()=>{window.testShotDone=false;PointsStadium.shot('save').then(()=>window.testShotDone=true);});
    await page.waitForTimeout(250);const moving=await page.screenshot({clip});assert(!still.equals(moving),'Shot did not move');
    await page.waitForFunction(()=>window.testShotDone);
    assert((await page.evaluate(()=>PointsStadium.inspect())).caught,'Keeper did not visibly catch the ball');
    console.log('PASS nonblank stadium, animated shot and keeper catch');
    guest=true;start();run.is_trial=true;await page.emulateMedia({reducedMotion:'reduce'});
    await page.goto(origin+'/penalties?ad_preview=1');await page.waitForSelector('#question-panel:not([hidden])');
    assert.equal(await page.locator('[data-ad-slot]:visible').count(),0);
    await page.locator('#leave').click();await page.waitForSelector('#summary:not([hidden])');
    await page.waitForFunction(()=>document.body.classList.contains('stadium-ending'));
    assert(await page.locator('#guest-benefits').isVisible());assert.equal(await page.locator('[data-ad-slot]:visible').count(),0);
    await page.screenshot({path:`${artifacts}/guest-results.png`,fullPage:true});
    await page.locator('#another').click();assert(await page.locator('#selection').isVisible());
    assert.equal(await page.locator('#start').textContent(),'Play as guest');assert.equal(await page.locator('#guest-benefits').isVisible(),false);
    assert.equal(await page.locator('[data-ad-slot]:visible').count(),1);
    console.log('PASS guest registration offer, replay and ads hidden during gameplay');
    assert.deepEqual(errors,[]);console.log('PASS connection recovery, results, restart and desktop');
    await context.close();
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
