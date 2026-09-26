/* Screenshot the actual production scene, not a separate illustration. */
const {chromium}=require('playwright'),path=require('node:path');
const origin=process.env.GUIDE_ORIGIN||'http://127.0.0.1:8015';
if(!['127.0.0.1','localhost'].includes(new URL(origin).hostname))throw Error('Local preview only');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:900,height:600},deviceScaleFactor:1});
  await page.route('**/guide-capture',route=>route.fulfill({contentType:'text/html',body:'<html data-theme="light"><style>html,body{margin:0;background:#f6f3eb}#scene{width:900px;height:600px}canvas{display:block}</style><div id="scene"></div></html>'}));
  await page.goto(origin+'/guide-capture');
  await page.addScriptTag({url:origin+'/trivia-assets/penalty_shots.js?v=1'});
  await page.evaluate(async()=>{
   const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=16');
   const host=document.getElementById('scene');window.captureScene=createStadium(host,host,()=>{throw Error('WebGL failed');});
  });
  for(const role of ['shooter','keeper']){
   await page.evaluate(async role=>{
    await captureScene.setView(role);
    if(role==='keeper')await captureScene.shot('save',false,{target:{side:1,high:false},keeper:{side:1,high:false}});
   },role);
   await page.locator('canvas').screenshot({path:path.join(__dirname,'../trivia_app/static/guide/'+role+'.png')});
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
