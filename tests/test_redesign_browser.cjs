/* Full public-page visual sweep. Test fixtures only; no production traffic. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/tmp/on-the-dot-redesign';fs.mkdirSync(out,{recursive:true});
const controls='button,summary,.primary-link,.top-navigation a,.page-return>a,.home-modes a,.home-rules-bottom a,.home-progress a,.game-mode-tabs a,.guide-jump a,.guide-guest>a,.solo-heading>a,.daily-ranking-link,.community-actions>a,.site-footer a,#public-profile,.team-rules-link,.period-tabs span,.guide-scenarios span,.difficulty-options label,.difficulty-options label>span,.auth-options label,.team-options label';
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const [width,height] of [[320,568],[390,844],[768,1024],[1440,1000]]){
   await page.setViewportSize({width,height});
   for(const path of ['/','/penalties','/daily','/friends','/leaderboard','/history','/account','/how-to-play']){
    console.log(`Checking ${width} ${path}`);
    // Pages may poll their game APIs. Wait for layout resources, not an idle
    // network that an active game deliberately never guarantees.
    await page.goto(origin+path);await page.evaluate(()=>document.fonts.ready);
    await page.locator('.site-footer').waitFor({state:'attached'});
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(246, 243, 235)');
    assert.equal(await page.locator('#menu-open,#menu-drawer').count(),0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow ${width} ${path}`);
    const clipped=await page.locator('button:visible,a:visible,input:visible').evaluateAll(es=>es.filter(e=>!e.hasAttribute('data-label')&&e.scrollWidth>e.clientWidth+2).map(e=>e.id||e.textContent));
    assert.deepEqual(clipped,[],`Clipped controls ${width} ${path}`);
    const inconsistentControls=await page.locator(controls).evaluateAll(es=>es.filter(e=>
      e.checkVisibility({checkVisibilityCSS:true})&&
      (getComputedStyle(e).fontWeight!=='700'||getComputedStyle(e).fontFamily!==getComputedStyle(document.body).fontFamily)
    ).map(e=>({tag:e.tagName,id:e.id,text:e.textContent.trim().slice(0,70),weight:getComputedStyle(e).fontWeight})));
    assert.deepEqual(inconsistentControls,[],`Controls must share the same bold font: ${width} ${path}`);
    assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).fontWeight),'400','Ordinary text must remain unchanged');
    for(const copy of await page.locator('.home-steps p,.guide-intro,.difficulty-options small').all()){
     assert.equal(await copy.evaluate(e=>getComputedStyle(e).fontWeight),'400');
    }
    await page.screenshot({path:`${out}/${path.slice(1)||'home'}-${width}.png`,fullPage:true});
    if(path==='/'){
     assert.equal(await page.locator('.play-button').getAttribute('href'),'/penalties');
     assert.equal(await page.locator('.play-button').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(136, 176, 75)');
     assert.equal(await page.locator('.play-button span').evaluate(e=>getComputedStyle(e).fontWeight),'900');
     const next=await page.locator('.home-section-heading').boundingBox();assert(next.y<height,'Hint of next section must be visible');
     for(const mode of ['daily','duel','solo']){
      await page.locator(`[data-mode=${mode}]`).click();
      assert.equal(await page.locator('#rules-panel').getAttribute('aria-labelledby'),'tab-'+mode);
     }
     await page.locator('#tab-solo').focus();await page.keyboard.press('ArrowRight');
     assert.equal(await page.locator('#tab-daily').getAttribute('aria-selected'),'true');
    }
   }
   console.log(`PASS public redesign ${width}: 8 pages, cream palette, fixed controls, tabs and no overflow`);
  }
  const noJS=await browser.newContext({javaScriptEnabled:false}),plain=await noJS.newPage();await plain.goto(origin+'/');
  assert(await plain.locator('.play-button').isVisible());assert.equal(await plain.locator('.home-steps li').count(),3);await noJS.close();
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
