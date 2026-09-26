/* Local-only ad layout checks. API fixtures never create a real game. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-ads';fs.mkdirSync(output,{recursive:true});
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_per_correct:10,
  xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const catalog={categories:[{code:'ALL',label:'All clubs',counts:{easy:100,medium:100,hard:100}}],
  topics:[{code:'ALL',label:'Mixed topics',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
const question={text:'What was the outcome of Brighton & Hove Albion\u2019s home Premier League meeting with Wolverhampton Wanderers in 2022/23: a Brighton & Hove Albion win, a draw, or a Wolverhampton Wanderers win?',
  options:['Brighton & Hove Albion','Wolverhampton Wanderers','Manchester United','Draw'].map((text,i)=>({id:String(i),text}))};
let run=null;
function start(){run={run_id:'ad-test',phase:'ANSWERING',position:1,deadline:Date.now()+120000,
  question,rules,category:{label:'All clubs',topic_label:'Mixed topics'},difficulty:'easy',role:'shooter',review:[],
  total_xp:0,base_xp:0,bonus_xp:0,multiplier:1,correct:0,is_trial:true,
  shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},attempts:[],round:1,next_role:'keeper',winner:null,sudden_death:false}};}
async function boxes(page){return page.evaluate(()=>Object.fromEntries(['question-title','choices','next','leave'].map(id=>{
  const r=document.getElementById(id).getBoundingClientRect();return [id,{x:r.x,y:r.y,width:r.width,height:r.height}];
})));}
function stable(before,after){for(const id of Object.keys(before))for(const key of ['x','y','width','height'])
  assert(Math.abs(before[id][key]-after[id][key])<1,`${id}.${key} moved when filling ad`);}
function separate(a,b){return a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y;}

(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage({reducedMotion:'reduce'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname;let data={},status=200;
   if(path==='/api/players/me'){data={detail:'Sign in'};status=401;}
   else if(path==='/api/players/settings')data={password_reset_available:false};
   else if(path==='/api/friends/active')data={code:null};
   else if(path==='/api/solo/catalog')data=catalog;
   else if(path==='/api/solo/active')data={run:run?{...run,server_now:Date.now()}:null,trial_available:true};
   else if(path.endsWith('/leave')){run.phase='ABANDONED';run.shootout.winner='opponent';data={...run,server_now:Date.now()};}
   else if(path==='/api/solo/runs/ad-test')data={...run,server_now:Date.now()};
   else if(path==='/api/community/leaderboard')data={entries:[],participants:0,distribution:[],period:'all',metric:'level',signed_in:false};
   else {errors.push('Unexpected API '+path);status=404;}
   await route.fulfill({status,json:data});
  });
  for(const [width,height] of [[390,844],[844,390],[1024,768],[1280,720],[1280,800],[1440,900],[1920,1080]]){
   await page.setViewportSize({width,height});await page.goto(origin+'/penalties?ad_preview=1');
   await page.waitForSelector('#start:not([disabled])');
   const rails=width>=1280&&height>=780;
   assert.equal(await page.locator('.ad-rail:visible').count(),rails?2:0);
   assert.equal(await page.locator('.ad-gameplay:visible').count(),0);
   assert.equal(await page.locator('[data-ad-slot]:visible').count(),rails?3:1);
   for(const rail of await page.locator('.ad-rail:visible').all()){
    const box=await rail.boundingBox(),content=await page.locator('main').boundingBox();
    assert(separate(box,content));assert(box.x>=0&&box.x+box.width<=width&&box.y+box.height<=height);
    const creative=await rail.locator('.ad-creative').boundingBox();assert.equal(creative.width,160);assert.equal(creative.height,600);
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   if(width===1440)await page.screenshot({path:output+'/selection.png',fullPage:true});
   console.log(`PASS selection rails ${width}x${height}`);
  }
  for(const width of [1024,1280,1440,1920]){
   await page.setViewportSize({width,height:900});
   for(const path of ['/','/how-to-play','/daily','/friends','/account']){
    await page.goto(origin+path+'?ad_preview=1');
    const content=await page.locator('main').boundingBox();assert(content.width<=800);
    assert(Math.abs(content.x-(width-content.width)/2)<1,'Content must stay centered');
    for(const selector of ['.public-header','.page-return','.site-footer']){
     const box=await page.locator(selector).boundingBox();assert(box.width<=800);
     assert(Math.abs(box.x-(width-box.width)/2)<1,selector+' must stay centered');
    }
    const rails=page.locator('.ad-rail:visible');assert.equal(await rails.count(),width>=1280&&path!='/account'?2:0);
    for(const rail of await rails.all()){
     const box=await rail.boundingBox();assert(separate(box,content));
     assert(box.x+box.width<=content.x-23||box.x>=content.x+content.width+23,'Ad gutter must be at least 24px');
    }
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(width===1440&&path==='/')await page.screenshot({path:output+'/home-rails.png',fullPage:true});
   }
   console.log(`PASS shared 800px column, centered headers and safe rails at ${width}`);
  }
  await page.setViewportSize({width:1440,height:900});await page.goto(origin+'/leaderboard?ad_preview=1');
  assert.equal(await page.locator('.ad-rail:visible').count(),2);
  await page.goto(origin+'/penalties');assert.equal(await page.locator('[data-ad-slot]:visible').count(),0);
  for(const [width,height] of [[1280,800],[1440,900],[1920,1080],[1024,768],[844,390],[390,844]]){
   start();await page.setViewportSize({width,height});await page.goto(origin+'/penalties?ad_preview=1');
   await page.waitForFunction(()=>window.PointsStadium?.inspect().active&&!window.PointsStadium.inspect().entering);
   const shown=width>=1101&&height>=760,ad=page.locator('.ad-gameplay');
   assert.equal(await ad.isVisible(),shown);assert.equal(await page.locator('.ad-rail:visible').count(),0);
   if(shown){
    const bounds=await ad.boundingBox(),panel=await page.locator('#question-panel').boundingBox();
    assert(bounds.y>=panel.y+panel.height+31);assert(bounds.x>=panel.x&&bounds.x+bounds.width<=panel.x+panel.width+1);
    const before=await boxes(page);
    await ad.locator('.ad-creative').evaluate(e=>{e.textContent='Sponsored '.repeat(600);});
    stable(before,await boxes(page));
    const creative=await ad.locator('.ad-creative').boundingBox();assert.equal(creative.width,320);assert.equal(creative.height,50);
    await ad.locator('.ad-creative').evaluate(e=>{e.textContent='';});
    if(width===1440)await page.screenshot({path:output+'/gameplay.png'});
   }
   console.log(`PASS gameplay banner ${width}x${height}`);
  }
  await page.setViewportSize({width:1440,height:900});
  await page.locator('#leave').click();await page.waitForFunction(()=>document.body.classList.contains('stadium-ending'));
  assert.equal(await page.locator('.ad-gameplay:visible').count(),0);
  assert.equal(await page.locator('.ad-rail:visible').count(),2);
  assert.equal(await page.locator('[data-ad-slot]:visible').count(),3);
  await page.locator('#another').click();assert.equal(await page.locator('.ad-gameplay:visible').count(),0);
  // A wide touch device is not treated as a desktop ad surface.
  const touch=await browser.newContext({viewport:{width:1366,height:1024},hasTouch:true,isMobile:true});
  const touchPage=await touch.newPage();await touchPage.route('**/api/**',route=>route.fulfill({status:401,json:{detail:'Sign in'}}));
  await touchPage.goto(origin+'/penalties?ad_preview=1');assert.equal(await touchPage.locator('.ad-rail:visible').count(),0);
  await touch.close();assert.deepEqual(errors,[]);console.log('PASS results, restart, touch devices and no layout shifts from ad content');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
