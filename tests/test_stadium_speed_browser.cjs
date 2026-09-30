/* Real WebGL playback: timings, contact cues and pixels on mobile/desktop. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/tmp/on-the-dot-stadium-speed';fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
  try{
    const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/speed-check',route=>route.fulfill({contentType:'text/html',body:
      '<!doctype html><style>html,body{margin:0;background:#f6f3eb}html[data-theme=dark] body{background:#191c1a}#host,#frame{position:fixed;inset:0}canvas{display:block}</style><div id="host"></div><div id="frame"></div>'}));
    for(const [width,height] of [[1440,900],[390,700]]){
      await page.setViewportSize({width,height});await page.goto(origin+'/speed-check');
      await page.addScriptTag({url:origin+'/trivia-assets/penalty_shots.js'});
      await page.evaluate(async()=>{
        const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=28');
        const {STADIUM}=await import('/trivia-assets/stadium_config.js?v=23');
        window.config=STADIUM;
        window.engine=createStadium(document.querySelector('#host'),document.querySelector('#frame'),()=>{throw Error('WebGL lost');});
        await engine.setView('shooter');
      });
      for(const role of ['shooter','keeper']){
        const outcome=role==='shooter'?'goal':'save',theme=role==='shooter'?'light':'dark';
        const result=await page.evaluate(async({role,outcome,theme})=>{
          document.documentElement.dataset.theme=theme;dispatchEvent(new CustomEvent('points-theme'));
          const cameraBefore=engine.inspect().camera;
          const travelStarted=performance.now();
          await engine.setView(role,{duration:config.roleChangeMs});
          const travelMs=performance.now()-travelStarted,cameraAfter=engine.inspect().camera;
          const initial=engine.inspect().ball,cues=[];let frames=0,moved=false,finished=false;
          function sample(){frames++;const view=engine.inspect();moved||=view.ball.some((n,i)=>Math.abs(n-initial[i])>.01);if(!finished)requestAnimationFrame(sample);}
          requestAnimationFrame(sample);
          const started=performance.now();
          await engine.shot(outcome,true,PenaltyShots.plan(outcome,'speed:'+role),cue=>cues.push(cue));
          finished=true;
          return {travelMs,elapsedMs:performance.now()-started,frames,moved,cameraBefore,cameraAfter,cues,state:engine.inspect()};
        },{role,outcome,theme});
        const movementMs=(1500+280)/1.3;
        assert(result.elapsedMs>=movementMs+200-40);
        assert(result.elapsedMs<movementMs+650,'Only a short hold plus frame overhead may follow the movement');
        assert(result.frames>2&&result.moved,'The ball must actually animate');
        assert(result.travelMs<500);
        assert.deepEqual(result.cameraBefore,result.cameraAfter);
        assert.deepEqual(result.cues,['kick',outcome==='save'?'catch':'net','crowd-cheer']);
        assert(result.state.markingsVisible&&result.state.keeperVisible&&result.state.ballVisible&&result.state.focus===1);
        assert.equal(result.state.markingsColor,0xffffff);assert.equal(result.state.phase,'ready');
        if(outcome==='save')assert(result.state.caught&&result.state.ball.every((n,i)=>Math.abs(n-result.state.hands[i])<.001));
        const bytes=await page.screenshot({path:`${out}/${width}-${role}-${outcome}.png`});
        const {data,info}=await sharp(bytes).raw().toBuffer({resolveWithObject:true});let green=0,white=0;
        for(let i=0;i<data.length;i+=info.channels){if(data[i+1]>data[i]*1.15&&data[i+1]>data[i+2]*1.4)green++;if(data[i]>248&&data[i+1]>248&&data[i+2]>248)white++;}
        assert(green>width*height*.05&&white>20,'Nonblank pitch, white goal and markings must render');
        console.log(JSON.stringify({width,role,shotMs:Math.round(result.elapsedMs),cameraMs:Math.round(result.travelMs),frames:result.frames,cues:result.cues}));
      }
      await page.evaluate(()=>engine.dispose());
    }
    assert.deepEqual(errors,[]);
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
