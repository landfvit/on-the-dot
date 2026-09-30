/* Local-only appearance checks; account writes use challenge_preview's isolated schema. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin='http://127.0.0.1:8015',out='/tmp/on-the-dot-pills';
fs.mkdirSync(out,{recursive:true});
const controls='button,summary,.primary-link,.play-button,.top-navigation a,.page-return>a,.home-modes a,.home-rules-bottom a,.home-progress a,.game-mode-tabs a,.guide-jump a,.guide-guest>a,.solo-heading>a,.daily-ranking-link,.community-actions>a,.site-footer a,#public-profile,.team-rules-link,.period-tabs span,.guide-scenarios span,.difficulty-options label,.auth-options label,.team-options label';
async function check(page){
  const failures=await page.locator(controls).evaluateAll(es=>es.filter(e=>e.checkVisibility({checkVisibilityCSS:true})).flatMap(e=>{
    const s=getComputedStyle(e),r=e.getBoundingClientRect(),errors=[];
    const rectangle=e.matches('.difficulty-options label,.solo-choices button');
    if(s.borderRadius!==(rectangle?'6px':'999px'))errors.push('wrong control shape');
    if(s.borderTopColor!=='rgba(0, 0, 0, 0)'||s.backgroundColor==='rgba(0, 0, 0, 0)')errors.push('control needs fill without a visible border');
    if(s.backgroundColor==='rgb(136, 176, 75)'&&!e.matches('.play-button,.solo-choices .correct'))errors.push('unexpected green fill');
    // Navigation tooltips intentionally extend outside the button box.
    if(!e.matches('.top-navigation a')&&(e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1))errors.push('overflow');
    if(r.left<0||r.right>innerWidth+1)errors.push('outside viewport');
    return errors.length?[{text:e.textContent.trim(),id:e.id,label:e.getAttribute('aria-label'),x:r.x,right:r.right,errors}]:[];
  }));
  assert.deepEqual(failures,[],page.url());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const offCenter=await page.locator('.top-navigation a,.icon-button:not(:has(span)),.password-toggle').evaluateAll(es=>es.filter(e=>e.checkVisibility({checkVisibilityCSS:true})).flatMap(e=>{
    const img=e.querySelector('img');if(!img)return [];
    const a=e.getBoundingClientRect(),b=img.getBoundingClientRect();
    return Math.abs(a.x+a.width/2-b.x-b.width/2)>1||Math.abs(a.y+a.height/2-b.y-b.height/2)>1?[e.getAttribute('aria-label')]:[];
  }));
  assert.deepEqual(offCenter,[],'Icon centers must match their button centers');
}
async function aligned(page,selector){
  const rows=await page.locator(selector).evaluateAll(es=>es.filter(e=>e.checkVisibility()).map(e=>{const r=e.getBoundingClientRect();return {y:r.y,h:r.height,w:r.width};}));
  assert(rows.length>=2,selector);
  assert(rows.every(r=>Math.abs(r.y-rows[0].y)<1&&Math.abs(r.h-rows[0].h)<1&&Math.abs(r.w-rows[0].w)<1),selector+JSON.stringify(rows));
}
async function selected(page,selector){
  const dark=await page.evaluate(()=>document.documentElement.dataset.theme==='dark');
  assert.equal(await page.locator(selector).evaluate(e=>getComputedStyle(e).backgroundColor),dark?'rgb(246, 243, 235)':'rgb(17, 17, 17)');
  assert.equal(await page.locator(selector).evaluate(e=>getComputedStyle(e).color),dark?'rgb(17, 17, 17)':'rgb(246, 243, 235)');
}
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try{
    const ctx=await browser.newContext(),page=await ctx.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    for(const width of [320,390,1440]){
      await page.setViewportSize({width,height:900});
      for(const theme of ['light','dark']){
        await page.goto(origin+'/');
        await page.evaluate(theme=>{localStorage.setItem('onthedot.theme',theme);document.documentElement.dataset.theme=theme;},theme);
        await page.locator('#tab-solo').waitFor();
        const playStyle=await page.locator('.play-button').evaluate(e=>{
          const s=getComputedStyle(e);return {border:s.borderTopColor,background:s.backgroundColor,color:s.color};
        });
        assert.deepEqual(playStyle,{border:'rgba(0, 0, 0, 0)',background:'rgb(136, 176, 75)',color:'rgb(17, 17, 17)'});
        assert(!await page.locator('.page-return [data-back]').isVisible(),'Home must not reveal hidden Back');
        await page.locator('#tab-daily').click();await selected(page,'#tab-daily');await check(page);
        await aligned(page,'.rule-tabs button');
        assert.equal(await page.locator('.home-play .home-modes,.home-play .match-format').count(),0);
        assert.equal(await page.locator('.home-steps .step-index').count(),0);
        const toolbar=await page.locator('.page-return').boundingBox();assert(toolbar.height<=46,'Toolbar should stay on one row');
        const full=page.getByRole('link',{name:'Full rules',exact:true});await full.scrollIntoViewIfNeeded();
        await page.screenshot({path:`${out}/home-${width}-${theme}.png`,fullPage:true});
        await full.hover();await page.mouse.down();await selected(page,'.home-rules-bottom a');await page.mouse.up();
        await page.waitForURL('**/how-to-play');await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
        await check(page);
        for(const e of await page.locator('.guide-scene').all()){
          assert(await e.evaluate(e=>e.complete&&e.naturalWidth>0));
          assert.deepEqual(await e.evaluate(e=>[getComputedStyle(e).borderTopColor,getComputedStyle(e).borderTopWidth]),['rgb(17, 17, 17)','3px']);
        }
        await page.locator('.guide-scenarios label').last().click();await selected(page,'.guide-scenarios :checked+span');
        await page.screenshot({path:`${out}/rules-${width}-${theme}.png`,fullPage:true});
        await page.goto(origin+'/penalties');await page.locator('#start:enabled').waitFor();
        await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
        await page.locator('.difficulty-options label').nth(1).click();await selected(page,'.difficulty-options label:has(:checked)');await check(page);
        await aligned(page,'.game-mode-tabs a');
        await page.screenshot({path:`${out}/selection-${width}-${theme}.png`});
        await page.locator('#start').click();await page.locator('#mode-intro[open]').waitFor();
        assert.equal(await page.evaluate(()=>document.activeElement.id),'mode-intro-title');
        assert.equal(await page.locator('#mode-intro button[value=cancel]').evaluate(e=>getComputedStyle(e).outlineStyle),'none');
        await aligned(page,'#mode-intro .actions button');
        const previews=await page.locator('.mode-intro-scenes img').evaluateAll(es=>es.map(e=>({fit:getComputedStyle(e).objectFit,ratio:e.clientWidth/e.clientHeight})));
        assert(previews.every(p=>p.fit==='contain'&&Math.abs(p.ratio-1.5)<.03));
        await page.screenshot({path:`${out}/intro-${width}-${theme}.png`});
        await page.keyboard.press('Tab');assert(await page.locator('#mode-intro button[value=cancel]').evaluate(e=>e.matches(':focus-visible')),'Keep keyboard focus visible');
        await page.locator('#mode-intro button[value=cancel]').click();
        await page.goto(origin+'/account');await page.locator('#authenticate').waitFor();
        await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
        await check(page);await selected(page,'.auth-options label:has(:checked)');
        await page.goto(origin+'/leaderboard');await page.waitForFunction(()=>document.getElementById('community-status').textContent!=='Loading...');
        await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
        await page.locator('input[name=metric][value=wins]').check();await selected(page,'.ranking-tabs :checked+span');await check(page);
      }
      console.log('PASS '+width+': centered icons/images, aligned rows, theme-aware selection, rules dialog focus');
    }
    const username='pills_'+Date.now();
    const registered=await ctx.request.post(origin+'/api/players/register',{data:{username,email:username+'@example.com',password:'test-only-password'}});
    assert.equal(registered.status(),201,await registered.text());
    await page.setViewportSize({width:390,height:844});await page.goto(origin+'/account');
    await page.locator('#profile-tabs').waitFor();await page.locator('[data-profile-tab=settings]').click();
    await selected(page,'[data-profile-tab=settings]');
    await page.locator('[data-profile-dialog=password-dialog]').click();
    assert(await page.locator('#password-dialog').isVisible());await check(page);
    await page.locator('#password-dialog [data-close-dialog]').click();
    await page.locator('[data-profile-tab=overview]').click();await page.locator('#add-team').click();
    await page.locator('#team-options label').last().click();await selected(page,'#team-options label:has(:checked)');await check(page);
    assert.deepEqual(errors,[]);console.log('PASS profile settings, password toggles, team choices');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
