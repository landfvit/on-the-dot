/* Local-only presentation tests: no account, game API or database writes. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/tmp/on-the-dot-compact';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browserName=process.env.TEST_BROWSER||'chrome';
 const browser=browserName==='webkit'?await webkit.launch({headless:true}):await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[748,260],[366,158],[296,100]]){
   const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:2}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   await page.route('**/compact-check',route=>route.fulfill({contentType:'text/html',body:
    '<!doctype html><style>body{margin:0;background:#f6f3eb}#host{position:fixed;inset:0}#frame{position:fixed;inset:6px 10px}canvas{display:block}</style><div id="host"></div><div id="frame"></div>'}));
   try{
    await page.goto(origin+'/compact-check');
    await page.evaluate(async()=>{
     const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=28');
     const {COMPACT_STADIUM}=await import('/trivia-assets/stadium_config.js?v=23');
     window.config=COMPACT_STADIUM;
     window.engine=createStadium(document.querySelector('#host'),document.querySelector('#frame'),e=>{throw e;},()=>{},{presentation:'compact'});
     window.record=async task=>{
      const start=performance.now(),frames=[];let done=false;
      function sample(){const s=engine.inspect();frames.push({camera:s.camera,focus:s.focus,framing:s.framing,ball:s.ball});if(!done)requestAnimationFrame(sample);}
      requestAnimationFrame(sample);await task();done=true;
      return {ms:performance.now()-start,frames,state:engine.inspect()};
     };
    });
    const intro=await page.evaluate(()=>record(()=>engine.setView('shooter',{intro:true,duration:config.introMs})));
    assert(intro.ms<500);assert.equal(intro.state.phase,'ready');
    assert.equal(intro.state.characterStyle,'pixel-art');assert(intro.state.spriteTextures>0);
    assert.equal(intro.state.stadiumObjects,0);assert.equal(intro.state.renderPasses,1);
    assert(intro.state.drawCalls<90,'Small scene stays within its draw-call budget');
    assert(intro.state.renderSize[0]>=Math.min(width,480));
    assert(intro.state.renderSize[0]<=480&&intro.state.renderSize[1]<=270,'Keep the deliberate pixel grid');
    assert.equal(intro.state.ballStyle,'pixel-art');
    let fixedCamera=intro.state.camera;
    for(const role of ['shooter','keeper']){
     const travel=await page.evaluate(role=>record(()=>engine.setView(role,{duration:config.roleChangeMs})),role);
     assert(travel.ms<500);assert.deepEqual(travel.state.camera,fixedCamera);
     assert.equal(travel.state.keeperShirt,role==='keeper'?0x92a8d1:0x6f2c91);
     assert.equal(travel.state.strikerShirt,role==='shooter'?0x92a8d1:0x6f2c91);
     fixedCamera=travel.state.camera;
     assert(travel.state.framing.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1),'Players and goal stay framed');
     await page.screenshot({path:`${out}/${browserName}-${width}-${role}-ready.png`});
     const outcome=role==='shooter'?'goal':'save';
     const shot=await page.evaluate(async({role,outcome})=>{
      const plan={target:{side:1,high:true},keeper:{side:outcome==='save'?1:-1,high:true}},cues=[];
      const result=await record(()=>engine.shot(outcome,true,plan,cue=>cues.push(cue)));
      return {...result,cues};
     },{role,outcome});
     assert(shot.ms>=1530&&shot.ms<2600,'Compact shot includes landing but no long result hold');
     for(const frame of shot.frames)assert.deepEqual(frame.camera,fixedCamera,'No camera travel during the penalty');
     assert(shot.frames.some(s=>Math.abs(s.ball[0]-41.5)>1),'The ball must actually move');
     assert.deepEqual(shot.cues,['kick',outcome==='save'?'catch':'net','crowd-cheer']);
     assert(shot.state.strikerVisible&&shot.state.keeperVisible&&shot.state.markingsVisible);
     assert(shot.state.keeper[1]<1,'Keeper must land before the next angle');
     if(outcome==='save')assert(shot.state.ball.every((n,i)=>Math.abs(n-shot.state.hands[i])<.001));
     assert(shot.state.ballDiameterPx>=5,'A catch must remain legible on the shortest phone viewport');
     assert(shot.state.ballScreen.slice(0,2).every(n=>Math.abs(n)<1),'Resolved ball must stay in frame');
     const bytes=await page.screenshot({path:`${out}/${browserName}-${width}-${role}.png`});
     const pixels=await sharp(bytes).stats();assert(pixels.channels.some(c=>c.stdev>10));
     // Every high/low target must remain visible and saves stay in the hands.
     const states=await page.evaluate(()=>{
      const result=[];
      for(const outcome of ['goal','save'])for(const side of [-1,0,1])for(const high of [false,true]){
       engine.shot(outcome,false,{target:{side,high},keeper:{side:outcome==='save'?side:side===0?1:-side,high}});
       result.push(engine.inspect());
      }
      return result;
     });
     for(const state of states){
      assert(state.framing.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1));
      assert(state.ball.every(Number.isFinite)&&state.ball[1]>=.195);
      if(state.lastOutcome==='save')assert(state.caught&&state.ball.every((n,i)=>Math.abs(n-state.hands[i])<.001));
     }
    }
    const outro=await page.evaluate(async()=>{
     const fades=[];const result=await record(()=>engine.finish(config.outroMs,t=>fades.push(t)));
     return {...result,fades};
    });
    assert(outro.ms>=140&&outro.ms<1000);assert.equal(outro.fades.at(-1),1);
    assert(outro.fades.every((n,i)=>i===0||n>=outro.fades[i-1]));
    for(const frame of outro.frames)assert.deepEqual(frame.camera,fixedCamera,'Results do not trigger a flyover');
    await page.evaluate(()=>engine.dispose());assert.equal(await page.locator('canvas').count(),0);
    assert.deepEqual(errors,[]);
    console.log(`PASS ${browserName} compact ${width}x${height}: intro ${Math.round(intro.ms)} ms, goals, saves, six targets, outro ${Math.round(outro.ms)} ms`);
   }finally{await page.close();}
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
