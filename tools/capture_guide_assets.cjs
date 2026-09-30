/* Capture the actual game renderer, not a separate illustration. Local use only:
 * NODE_PATH=<Playwright + Sharp modules> node tools/capture_guide_assets.cjs
 * Re-run after changing stadium/keeper/ball graphics. No game API is called. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright'),sharp=require('sharp');
const origin=process.env.GUIDE_CAPTURE_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output=process.env.GUIDE_CAPTURE_OUTPUT||path.resolve(__dirname,'../trivia_app/static/guide');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:800,height:360},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',()=>{throw Error('Guide capture must not use account or game APIs');});
  await page.route('**/guide-capture',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html data-theme="light"><head><style>html,body{margin:0;background:#f6f3eb}#scene,#frame{position:fixed;inset:0}#frame{inset:8px;pointer-events:none}canvas{display:block}</style></head><body><div id="scene"></div><div id="frame"></div></body></html>'}));
  await page.goto(origin+'/guide-capture');await page.addScriptTag({url:origin+'/trivia-assets/penalty_shots.js'});
  await page.evaluate(async()=>{
   const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=36');
   const {loadKits,paintKit}=await import('/trivia-assets/kit_pixels.js?v=4');
   window.guideKits=(await loadKits()).kits;window.paintGuideKit=paintKit;window.sceneFailure=false;
   window.guideScene=createStadium(document.getElementById('scene'),document.getElementById('frame'),()=>{window.sceneFailure=true;});
   const find=id=>{const kit=guideKits.find(k=>k.id===id);if(!kit)throw Error('Missing example kit '+id);return kit;};
   guideScene.setOutfits([{kit:find('64-2026-home'),number:27},{kit:find('33-2026-home'),number:11}]);
  });
  for(const role of ['shooter','keeper']){
   await page.evaluate(async role=>{
    await guideScene.setView(role,{intro:false,duration:0});guideScene.reset();
    if(role==='keeper')await guideScene.shot('save',false,{outcome:'save',target:{side:1,high:false},keeper:{side:1,high:false}});
   },role);
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
   const state=await page.evaluate(()=>({failed:sceneFailure,...guideScene.inspect()}));assert(!state.failed);assert.equal(state.role,role);
   if(role==='keeper')assert(state.caught&&state.ballVisible&&state.keeperVisible);
   assert.equal(state.presentation,'compact');
   assert.equal(role==='keeper'?state.keeperOutfit:state.strikerOutfit,'64-2026-home');
   const png=await page.screenshot(),stats=await sharp(png).stats();
   assert(stats.channels.slice(0,3).some(c=>c.stdev>10),'Blank scene');
   fs.writeFileSync(path.join(output,role+'.png'),png);console.log('Captured',role,state.caught?'ball held in gloves':'penalty spot');
  }
  // These transparent sprites use the profile/game painter at its native
  // resolution; CSS scales them with nearest-neighbour pixels in the guide.
  for(const [name,type,back] of [['kit-home','home',false],['kit-away','away',false],['kit-third','third',false],['kit-number','home',true]]){
   const url=await page.evaluate(({type,back})=>{
    const kit=guideKits.find(k=>k.id===`64-2026-${type}`);if(!kit)throw Error('Missing kit '+type);
    const canvas=document.createElement('canvas');paintGuideKit(canvas,kit,27,back);return canvas.toDataURL('image/png');
   },{type,back});
   const png=Buffer.from(url.split(',')[1],'base64');
   assert((await sharp(png).stats()).channels.some(c=>c.stdev>10));fs.writeFileSync(path.join(output,name+'.png'),png);
  }
  assert.deepEqual(errors,[]);
  await page.evaluate(()=>guideScene.dispose());
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
