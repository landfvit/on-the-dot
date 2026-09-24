/* Capture the actual game renderer, not a separate illustration. Local use only:
 * NODE_PATH=<Playwright + Sharp modules> node tools/capture_guide_assets.cjs
 * Re-run after changing stadium/keeper/ball graphics. No game API is called. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright'),sharp=require('sharp');
const origin=process.env.GUIDE_CAPTURE_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output=path.resolve(__dirname,'../trivia_app/static/guide');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:900,height:600},deviceScaleFactor:1});
  await page.route('**/guide-capture',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><style>html,body{margin:0;background:#222326}#scene,#frame{position:fixed;inset:0}#frame{pointer-events:none}canvas{display:block}</style></head><body><div id="scene"></div><div id="frame"></div></body></html>'}));
  await page.goto(origin+'/guide-capture');await page.addScriptTag({url:origin+'/trivia-assets/penalty_shots.js'});
  await page.evaluate(async()=>{const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=13');window.sceneFailure=false;
   window.guideScene=createStadium(document.getElementById('scene'),document.getElementById('frame'),()=>{window.sceneFailure=true;});});
  for(const role of ['shooter','keeper']){
   await page.evaluate(async role=>{
    await guideScene.setView(role,{intro:false,duration:0});guideScene.reset();
    if(role==='keeper')await guideScene.shot('save',false,{outcome:'save',target:{side:1,high:false},keeper:{side:1,high:false}});
   },role);
   await page.waitForTimeout(150);
   const state=await page.evaluate(()=>({failed:sceneFailure,...guideScene.inspect()}));assert(!state.failed);assert.equal(state.role,role);
   if(role==='keeper')assert(state.caught&&state.ballVisible&&state.keeperVisible);
   const png=await page.screenshot(),stats=await sharp(png).stats();
   assert(stats.channels.slice(0,3).some(c=>c.stdev>10),'Blank scene');
   fs.writeFileSync(path.join(output,role+'.png'),png);console.log('Captured',role,state.caught?'ball held in gloves':'penalty spot');
  }
  await page.evaluate(()=>guideScene.dispose());
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
