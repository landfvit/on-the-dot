/* Actual Three.js frames. Static spectator reactions must agree for both Duel
 * clients and never change the camera, ball physics or server game state. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/tmp/on-the-dot-crowd';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/crowd-check',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><style>html,body{margin:0;background:#f6f3eb}#host,#frame{position:fixed;inset:0}#frame{pointer-events:none}canvas{display:block}</style><div id="host"></div><div id="frame"></div>'}));
  for(const [width,height] of [[390,664],[1440,900]]){
   await page.setViewportSize({width,height});await page.goto(origin+'/crowd-check');
   await page.addScriptTag({url:origin+'/trivia-assets/penalty_shots.js'});
   await page.evaluate(async()=>{
    const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=14');
    window.engine=createStadium(document.querySelector('#host'),document.querySelector('#frame'),()=>{throw Error('WebGL lost');});
   });
   let initial;
   for(const role of ['shooter','keeper'])for(const outcome of ['goal','save','miss','replay']){
    const states=[];
    for(const viewerSeat of [0,1]){
     const state=await page.evaluate(async({viewerSeat,role,outcome})=>{
      engine.supporters({viewerSeat,names:['Home end','Away end']});
      await engine.setView(viewerSeat===0?role:role==='shooter'?'keeper':'shooter');
      await engine.shot(outcome,false,PenaltyShots.plan(outcome,'same-duel-round'));
      return engine.inspect();
     },{viewerSeat,role,outcome});states.push(state);
     assert(state.crowd.count>2000);assert(state.crowd.teamCounts.every(n=>n>1000));
     assert(state.crowd.drawCalls<=14);assert(state.crowd.staticPose);assert.equal(state.crowd.maxLift,0);
     assert(state.markingsVisible&&state.standsSolid&&state.environmentVisible);
     if(outcome==='save')assert(state.caught&&state.ball.every((n,i)=>Math.abs(n-state.hands[i])<.001));
     if(viewerSeat===0){
      const bytes=await page.screenshot({path:`${out}/${width}-${role}-${outcome}.png`});
      const {data,info}=await sharp(bytes).raw().toBuffer({resolveWithObject:true});let green=0,white=0,ink=0;
      for(let i=0;i<data.length;i+=info.channels){if(data[i+1]>data[i]*1.15&&data[i+1]>data[i+2]*1.4)green++;if(data[i]>248&&data[i+1]>248&&data[i+2]>248)white++;if(data[i]<45&&data[i+1]<45&&data[i+2]<45)ink++;}
      assert(green>width*height*.05&&ink>100&&white>20,'Pitch, white markings and ink geometry must render');
      if(role==='shooter'&&outcome==='goal')initial=state;
     }
    }
    assert.deepEqual(states[0].crowd.moods,states[1].crowd.moods,'Duel sides must see identical physical stand reactions');
    assert.equal(states[0].crowd.winner,states[1].crowd.winner);
   }
   await page.evaluate(()=>engine.reset());assert.deepEqual(await page.evaluate(()=>engine.inspect().crowd.moods),['neutral','neutral']);
   // The actual shot still moves with a static audience; reducing crowd motion
   // must not disable the football, goalkeeper or end-of-game camera.
   await page.evaluate(()=>{window.moving=engine.shot('save',true,PenaltyShots.plan('save','animated'));});
   await page.waitForTimeout(150);const a=await page.evaluate(()=>engine.inspect());
   await page.waitForFunction(ball=>engine.inspect().ball.some((n,i)=>Math.abs(n-ball[i])>.01),a.ball);
   const b=await page.evaluate(()=>engine.inspect());assert.notDeepEqual(a.ball,b.ball);
   await page.evaluate(()=>moving);
   await page.evaluate(()=>engine.finish(0));const end=await page.evaluate(()=>engine.inspect());assert(end.camera[1]>100&&end.focus===0);
   await page.screenshot({path:`${out}/${width}-stadium-overhead.png`});
   await page.evaluate(()=>engine.dispose());
   console.log(`PASS crowd ${width}: ${initial.crowd.count} colored supporters, opposing static reactions, ball/catch/outro and pixel checks`);
  }
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
