/* Audience is AUDIO ONLY. Render actual stadium pixels in both UI themes. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/tmp/on-the-dot-stadium-audio';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/scene-check',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><style>html,body{margin:0;background:#f6f3eb}html[data-theme=dark],html[data-theme=dark] body{background:#191c1a}#host,#frame{position:fixed;inset:0}#frame{pointer-events:none}canvas{display:block}</style><div id="host"></div><div id="frame"></div>'}));
  for(const [width,height] of [[390,664],[1440,900]]){
   await page.setViewportSize({width,height});await page.goto(origin+'/scene-check');
   await page.addScriptTag({url:origin+'/trivia-assets/penalty_shots.js'});
   await page.evaluate(async()=>{
    const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=15');
    window.engine=createStadium(document.querySelector('#host'),document.querySelector('#frame'),()=>{throw Error('WebGL lost');});
   });
   for(const theme of ['light','dark']){
    await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;dispatchEvent(new CustomEvent('points-theme'));},theme);
    for(const role of ['shooter','keeper'])for(const outcome of ['goal','save','miss','replay']){
     const {state,cues}=await page.evaluate(async({role,outcome})=>{
      await engine.setView(role);const cues=[];
      await engine.shot(outcome,false,PenaltyShots.plan(outcome,'same-duel-round'),name=>cues.push(name));
      return {state:engine.inspect(),cues};
     },{role,outcome});
     assert.equal(state.theme,theme);assert.equal(state.markingsColor,0xffffff);
     assert(!('crowd' in state));assert(state.markingsVisible&&state.standsSolid&&state.focus===1);
     if(outcome==='replay')assert.deepEqual(cues,[]);
     else assert.equal(cues.at(-1),(role==='shooter'?outcome==='goal':outcome!=='goal')?'crowd-cheer':'crowd-groan');
     if(outcome==='save')assert(state.caught&&state.ball.every((n,i)=>Math.abs(n-state.hands[i])<.001));
     if(['goal','save'].includes(outcome)){
      const bytes=await page.screenshot({path:`${out}/${width}-${theme}-${role}-${outcome}.png`});
      const {data,info}=await sharp(bytes).raw().toBuffer({resolveWithObject:true});let green=0,white=0;
      for(let i=0;i<data.length;i+=info.channels){if(data[i+1]>data[i]*1.15&&data[i+1]>data[i+2]*1.4)green++;if(data[i]>248&&data[i+1]>248&&data[i+2]>248)white++;}
      assert(green>width*height*.05&&white>20,'Pitch and white markings must render in both themes');
     }
    }
    await page.evaluate(()=>engine.finish(0));const end=await page.evaluate(()=>engine.inspect());assert(end.camera[1]>100&&end.focus===0);
    await page.screenshot({path:`${out}/${width}-${theme}-overhead.png`});
   }
   await page.evaluate(()=>engine.dispose());console.log(`PASS stadium ${width}: both themes, white paint, background blur, audio reactions, no crowd and overhead`);
  }
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
