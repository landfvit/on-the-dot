/* Public navigation and first-use rules. All game APIs are local mocks. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-navigation';fs.mkdirSync(output,{recursive:true});
const links=['/','/penalties','/daily','/friends','/leaderboard','/history','/account','/how-to-play'];
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>Object.defineProperty(navigator,'share',{value:undefined,configurable:true}));
  await page.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname;let data={},status=200;
   if(request.method()!=='GET'){writes.push(path);status=500;}
   else if(path==='/api/players/me'){status=401;data={detail:'Sign in'};}
   else if(path==='/api/solo/active')data={run:null,trial_available:true};
   else if(path==='/api/friends/active')data={code:null};
   else if(path==='/api/solo/catalog')data={categories:[],topics:[{code:'ALL',counts_by_team:{ALL:{easy:50,medium:50,hard:50}}}],
    rules:{format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}}};
   else {errors.push('Unexpected API '+path);status=404;}
   await route.fulfill({status,json:data});
  });
  for(const width of [320,390,768,1100,1440]){
   await page.setViewportSize({width,height:900});await page.goto(origin+'/penalties');
   assert.equal(await page.locator('#menu-open,#menu-drawer,.shell-drawer').count(),0);
   const nav=page.getByRole('navigation',{name:'Main navigation',exact:true});
   assert(await nav.isVisible());assert.equal(await nav.locator('img').count(),0);
   assert.deepEqual(await nav.locator('a').evaluateAll(es=>es.map(e=>e.getAttribute('href'))),links);
   const boxes=await nav.locator('a').evaluateAll(es=>es.map(e=>{
    const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,fits:e.scrollWidth<=e.clientWidth+1};
   }));
   for(const [i,r] of boxes.entries()){
    assert(r.x>=0&&r.x+r.w<=width+1&&r.h>=44&&r.fits,`${width}: link ${links[i]} must fit`);
    for(const s of boxes.slice(i+1))assert(r.x+r.w<=s.x+1||s.x+s.w<=r.x+1||r.y+r.h<=s.y+1||s.y+s.h<=r.y+1,'Navigation links overlap');
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:`${output}/navigation-${width}.png`});
   await page.locator('.header-sound > summary').click();
   assert(await page.locator('.header-sound .sound-settings').isVisible());
   await page.keyboard.press('Escape');assert.equal(await page.locator('.header-sound').getAttribute('open'),null);
   await page.locator('.header-sound > summary').click();await page.locator('.public-header').click({position:{x:4,y:4}});
   assert.equal(await page.locator('.header-sound').getAttribute('open'),null);
   await page.locator('[data-share-game]').click();assert(await page.locator('#game-share-dialog').isVisible());
   const share=await page.locator('#game-share-dialog').boundingBox();
   assert(share.x>=0&&share.x+share.width<=width+1);assert(Math.abs(share.x-(width-share.width)/2)<2);
   assert.equal(await page.locator('#game-share-link').inputValue(),origin+'/');
   await page.keyboard.press('Escape');assert(!(await page.locator('#game-share-dialog').isVisible()));
   console.log(`PASS navigation ${width}: visible links, no drawer/icons/overflow, sound and sharing`);
  }
  for(const path of ['/penalties','/daily','/friends']){
   await page.goto(origin+path);
   await page.locator('.game-rules-link').click();await page.waitForURL(origin+'/how-to-play');
   assert(await page.locator('.game-guide').isVisible());assert.equal(await page.locator('dialog[open]').count(),0);
   await page.locator('[data-back]').click();await page.waitForURL(origin+path);
   await page.locator('.top-navigation a[href="/how-to-play"]').click();await page.waitForURL(origin+'/how-to-play');
   console.log(`PASS ${path}: both help links reach full guide; Back returns to the mode`);
  }
  for(const path of ['/penalties','/friends']){
   await page.goto(origin+path);await page.locator('#start:not([disabled])').click();
   assert(await page.locator('#mode-intro').isVisible());assert.deepEqual(writes,[]);
   await page.keyboard.press('Escape');assert(!(await page.locator('#mode-intro').isVisible()));
   await page.waitForFunction(()=>!document.getElementById('start').disabled);assert.deepEqual(writes,[]);
  }
  assert.deepEqual(errors,[]);console.log('PASS first-use rules still appear before game creation; cancel creates no game');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
