/* Local browser regression: real stadium timing, mocked game APIs, no writes. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015',out='/tmp/on-the-dot-hud';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  for(const [width,mode] of [[390,'full'],[1440,'full'],[390,'skip'],[390,'reduced'],[390,'fallback']]){
   const page=await browser.newPage({viewport:{width,height:844},reducedMotion:mode==='reduced'?'reduce':'no-preference'}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));let run=null,release;
   const loaded=new Promise(resolve=>release=resolve);
   await page.route('**/stadium_scene.js?*',async route=>{
    if(mode==='fallback')return route.abort();
    await loaded;await route.continue();
   });
   await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;let data,status=200;
    if(path==='/api/players/me'){status=401;data={detail:'Sign in'};}
    else if(path==='/api/solo/catalog')data={categories:[],topics:[{code:'ALL',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
    else if(path==='/api/solo/active')data={run:null,trial_available:true};
    else if(path==='/api/solo/runs'){
     run={run_id:'reveal-test',phase:'READY',position:0,role:'shooter',question:null,review:[],rules,
      difficulty:'easy',category:{label:'All clubs'},is_trial:true,total_xp:0,correct:0,base_xp:0,bonus_xp:0,multiplier:1,
      shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},attempts:[],round:1,next_role:'shooter',winner:null,sudden_death:false}};
     data=run;
    }else if(path==='/api/solo/runs/reveal-test')data=run;
    else throw Error('Unexpected API '+path);
    await route.fulfill({status,json:data===run?{...data,server_now:Date.now()}:data});
   });
   await page.goto(origin+'/penalties',{waitUntil:'domcontentloaded'});
   await page.locator('#start:enabled').click();await page.locator('#mode-intro button[value=play]').click();
   await page.locator('#quiz-run:not([hidden])').waitFor();
   if(mode!=='fallback'){
    assert(!await page.locator('#leave').isVisible(),'No Forfeit while the renderer loads');
    assert(!await page.locator('#shootout-board').isVisible());
   }
   await page.evaluate(()=>{
    window.hudFrames=[];window.recordHud=true;
    function alpha(id){
     let value=1;
     for(let e=document.getElementById(id);e;e=e.parentElement){
      const s=getComputedStyle(e);if(s.display==='none'||s.visibility==='hidden')return 0;
      value*=Number(s.opacity);
     }
     return value;
    }
    function frame(){
     hudFrames.push([alpha('shootout-board'),alpha('leave'),document.getElementById('shootout-hud').inert]);
     if(recordHud)requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
   });
   release();
   if(mode==='fallback'){
    await page.locator('#stadium-unavailable:not([hidden])').waitFor();
    assert(await page.locator('#leave').isVisible(),'Failed WebGL must retain an exit');
    assert(await page.locator('#shootout-board').isVisible());
   }else{
    if(mode!=='reduced'){
     await page.waitForFunction(()=>PointsStadium.inspect().entering);
     assert.equal(await page.locator('#shootout-hud').evaluate(e=>Number(getComputedStyle(e).opacity)),0);
     assert(await page.locator('#shootout-hud').evaluate(e=>e.inert));
     if(mode==='skip')await page.locator('#stadium-skip').click();
    }
    await page.waitForFunction(()=>PointsStadium.inspect().active&&!PointsStadium.inspect().entering);
    assert.equal(await page.locator('#shootout-hud').evaluate(e=>Number(getComputedStyle(e).opacity)),1);
    assert(!await page.locator('#shootout-hud').evaluate(e=>e.inert));
    assert(await page.locator('#leave').isVisible());
   }
   const frames=await page.evaluate(()=>{recordHud=false;return hudFrames;});
   assert(frames.every(([board,button])=>Math.abs(board-button)<.00001),'Score and Forfeit must share every reveal frame');
   if(mode==='full')assert(frames.some(([alpha,,inert])=>alpha>0&&alpha<1&&inert),'Fade should be progressive and noninteractive');
   await page.screenshot({path:`${out}/${width}-${mode}.png`});
   assert.deepEqual(errors,[]);await page.close();console.log(`PASS HUD reveal ${width} ${mode}`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
