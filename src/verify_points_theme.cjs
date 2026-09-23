// Read-only UI checks. The public profile response is a local test fixture;
// no account is created and no production profile is changed.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const out=path.resolve('data/private/stadium-ui-check');
fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'}),errors=[];
  try {
    const context=await browser.newContext();
    await context.route('**/api/players/profiles/visual-qa',route=>route.fulfill({json:{
      username:'visual-qa',bio:'Premier League supporter',accent:'green',total_xp:1240,level:4,
      level_xp:1000,next_level_xp:1600,completed_quizzes:16,
      streak:{current:3,longest:8,completed_today:true},
    }}));
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    for(const [name,url,ready] of [
      ['selection','/penalties','#start:not([disabled])'],
      ['pvp-lobby','/penalties/pvp','#create-game:not([disabled])'],
      ['account','/account','#authentication:not([hidden])'],
      ['profile','/u/visual-qa','#profile:not([hidden])'],
    ])for(const width of [1440,390,320]) {
      await page.setViewportSize({width,height:width>800?1000:844});
      await page.goto('http://127.0.0.1:8002'+url);await page.locator(ready).waitFor();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name} ${width}: horizontal overflow`);
      assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(9, 19, 22)');
      assert.doesNotMatch(await page.locator('body').innerText(),/Daily quiz (?:complete|not completed)|database-verified|Author-provided/i);
      const overflowing=await page.locator('button,select,input').evaluateAll(nodes=>nodes.filter(n=>
        n.getClientRects().length&&n.getBoundingClientRect().width&&n.getBoundingClientRect().right>innerWidth+1).map(n=>n.id));
      assert.deepEqual(overflowing,[],`${name} ${width}: controls outside viewport`);
      await page.screenshot({path:path.join(out,`theme-${name}-${width}.png`),fullPage:true});
    }
    assert.deepEqual(errors,[]);console.log('12 page/viewport checks passed; no overflow, source labels or daily-complete filler.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
