/* Read-only guide checks plus a mocked profile. No real accounts or games. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',engine=process.env.TEST_BROWSER||'chrome';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-guide';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=engine==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const requests=[];page.on('request',r=>requests.push(r.url()));
  for(const [width,height] of [[320,568],[390,844],[768,1024],[1440,1000]])for(const theme of ['light','dark']){
   await page.setViewportSize({width,height});requests.length=0;await page.goto(origin+'/how-to-play');
   await page.evaluate(theme=>{
    document.documentElement.dataset.theme=theme;
    document.querySelectorAll('.game-guide img').forEach(img=>img.loading='eager');
   },theme);
   await page.waitForFunction(()=>[...document.querySelectorAll('.game-guide img')].every(i=>i.complete&&i.naturalWidth>0));
   assert(!requests.some(url=>url.includes('/api/')));assert(!requests.some(url=>url.includes('three.module')));
   assert.deepEqual(await page.locator('.guide-scene').evaluateAll(es=>es.map(e=>[e.naturalWidth,e.naturalHeight])),[[800,360],[800,360]]);
   assert.equal(await page.locator('.guide-club-options img').count(),6);
   assert.equal(await page.locator('.guide-kit-example img').count(),4);
   assert(await page.locator('.guide-kit-example img').evaluateAll(es=>es.every(e=>e.naturalWidth===40&&e.naturalHeight===44)));
   assert.equal(await page.locator('.guide-example:visible').count(),1);
   assert(await page.locator('#example-early').isVisible());
   const original=await page.locator('.guide-kick-legend').boundingBox();
   assert((await page.locator('.guide-example-stage').boundingBox()).height<(width<=600?240:180),'No oversized fixed example spacer');
   const originalTop=original.y+await page.evaluate(()=>scrollY);
   for(const value of ['last','sudden','early']){
    await page.locator(`input[value="${value}"]`).check();assert(await page.locator('#example-'+value).isVisible());
    const box=await page.locator('.guide-kick-legend').boundingBox();
    assert(Math.abs(box.y+await page.evaluate(()=>scrollY)-originalTop)<2);
   }
   await page.locator('input[value="early"]').focus();await page.keyboard.press('ArrowRight');assert(await page.locator('#example-last').isVisible());
   const overflow=await page.evaluate(()=>[...document.querySelectorAll('.game-guide th,.game-guide td,.guide-scoreboard,.guide-scenarios span')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent));
   assert.deepEqual(overflow,[]);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const illustrations=await page.locator('.guide-roles img,.guide-club-example,.guide-kit-example').evaluateAll(es=>es.every(e=>{
    const r=e.getBoundingClientRect(),parent=e.parentElement.getBoundingClientRect();return r.left>=parent.left-1&&r.right<=parent.right+1;
   }));assert(illustrations,'Illustrations stay inside their aligned columns');
   await page.screenshot({path:`${output}/${engine}-guide-${width}-${theme}.png`,fullPage:true});
   await page.locator('.guide-jump a[href="#teams"]').click();assert(page.url().endsWith('#teams'));
   assert(await page.locator('#teams').isVisible());
   await page.locator('#teams').screenshot({path:`${output}/${engine}-teams-${width}-${theme}.png`});
   const footerGap=await page.evaluate(()=>document.querySelector('.site-footer').getBoundingClientRect().top-document.querySelector('#teams').getBoundingClientRect().bottom);
   assert(footerGap>=16&&footerGap<=24,'Compact footer gap: '+footerGap);
   console.log(`PASS guide ${engine} ${width} ${theme}: current images, kits, stable keyboard examples, compact layout and no overflow`);
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
  await page.goto(origin+'/account');await page.locator('.team-rules-link[href="/how-to-play#teams"]').click();await page.waitForURL('**/how-to-play#teams');
  assert.deepEqual(errors,[]);console.log('PASS no-JS fallback and profile team-help link');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
