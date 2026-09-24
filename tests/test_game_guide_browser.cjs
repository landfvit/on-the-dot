/* Read-only guide checks plus a mocked profile. No real accounts or games. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-guide';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const requests=[];page.on('request',r=>requests.push(r.url()));
  for(const [width,height] of [[320,568],[390,844],[768,1024],[1440,1000]]){
   await page.setViewportSize({width,height});requests.length=0;await page.goto(origin+'/how-to-play');
   await page.waitForFunction(()=>[...document.querySelectorAll('.game-guide img')].every(i=>i.complete&&i.naturalWidth>0));
   assert(!requests.some(url=>url.includes('/api/')));assert(!requests.some(url=>url.includes('three.module')));
   assert.equal(await page.locator('.guide-example:visible').count(),1);
   assert(await page.locator('#example-early').isVisible());
   const original=await page.locator('.guide-kick-legend').boundingBox();
   const originalTop=original.y+await page.evaluate(()=>scrollY);
   for(const value of ['last','sudden','early']){
    await page.locator(`input[value="${value}"]`).check();assert(await page.locator('#example-'+value).isVisible());
    const box=await page.locator('.guide-kick-legend').boundingBox();
    assert(Math.abs(box.y+await page.evaluate(()=>scrollY)-originalTop)<2);
   }
   await page.locator('input[value="early"]').focus();await page.keyboard.press('ArrowRight');assert(await page.locator('#example-last').isVisible());
   const overflow=await page.evaluate(()=>[...document.querySelectorAll('.game-guide th,.game-guide td,.guide-scoreboard,.guide-scenarios span')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent));
   assert.deepEqual(overflow,[]);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:`${output}/guide-${width}.png`,fullPage:true});
   await page.locator('.guide-jump a[href="#teams"]').click();assert(page.url().endsWith('#teams'));
   assert(await page.locator('#teams').isVisible());
   await page.locator('.site-footer a[href="/how-to-play"]').click();
   assert(new URL(page.url()).pathname==='/how-to-play');
   console.log(`PASS guide ${width}: images, keyboard examples, team explanation and no overflow`);
  }
  const noJS=await browser.newContext({javaScriptEnabled:false});const plain=await noJS.newPage();await plain.goto(origin+'/how-to-play');
  assert.equal(await plain.locator('.guide-example:visible').count(),3);await noJS.close();
  // Profile help remains in the existing account flow and reaches the team section.
  await page.route('**/api/**',route=>{
   const url=new URL(route.request().url()).pathname;
   if(url==='/api/players/me')return route.fulfill({json:{username:'example_player',email:'example@example.com',bio:'',club:null,
    level:1,total_xp:0,level_xp:0,next_level_xp:200,streak:{current:0},stats:{wins:0,losses:0,played:0,win_rate:null},preferences:{animations:true,reduced_motion:false}}});
   if(url==='/api/players/settings')return route.fulfill({json:{password_reset_available:false}});
   if(url==='/api/players/friends')return route.fulfill({json:{friends:[],incoming:[],outgoing:[]}});
   throw Error('Unexpected API '+url);
  });
  await page.goto(origin+'/account');await page.locator('.team-rules-link').click();await page.waitForURL('**/how-to-play#teams');
  assert.deepEqual(errors,[]);console.log('PASS no-JS fallback and profile team-help link');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
