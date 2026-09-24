/* Run only against tests.challenge_preview: two real accounts, no API mocks. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright'),sharp=require('sharp');
const origin='http://127.0.0.1:8015',out='/tmp/on-the-dot-challenges';fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
  const errors=[];
  try{
    const host=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
    const guest=await browser.newContext({viewport:{width:390,height:664},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    const anon=await browser.newContext({viewport:{width:390,height:664}}),anonymous=await anon.newPage();
    await anonymous.goto(origin+'/daily');await anonymous.locator('#mode-auth:not([hidden])').waitFor();
    assert.equal(await anonymous.locator('#quiz-start').isVisible(),false);
    assert((await anonymous.locator('#mode-register').getAttribute('href')).includes('next=/daily'));
    await anonymous.screenshot({path:out+'/daily-guest.png'});
    for(const [ctx,identifier,password] of [[host,'player@example.com','test-only-password-1234'],[guest,'friend@example.com','test-password-1234']]){
      const r=await ctx.request.post(origin+'/api/players/login',{data:{identifier,password}});assert.equal(r.status(),200,await r.text());
    }
    const a=await host.newPage(),b=await guest.newPage();
    for(const p of [a,b])p.on('pageerror',e=>errors.push(e.message));
    await a.goto(origin+'/friends');await a.locator('#start:enabled').waitFor();await a.locator('#start').click();
    await a.locator('#friend-lobby:not([hidden])').waitFor();
    const invite=await a.locator('#invite-link').inputValue();assert(invite.startsWith(origin+'/friends/'));
    await b.goto(invite);await b.locator('#friend-join:not([hidden])').click();
    await a.locator('#friend-ready:not([hidden]):enabled').waitFor();
    await b.locator('#friend-ready:not([hidden]):enabled').waitFor();
    await b.screenshot({path:out+'/lobby-mobile.png'});
    await a.locator('#friend-ready').click();await b.locator('#friend-ready').click();
    await a.locator('#choices button:enabled').first().waitFor();await b.locator('#choices button:enabled').first().waitFor();
    assert.equal(await a.locator('#question-title').textContent(),await b.locator('#question-title').textContent());
    for(const [p,name] of [[a,'desktop'],[b,'mobile']]){
      await p.waitForFunction(()=>window.PointsStadium?.inspect().active&&!window.PointsStadium.inspect().entering);
      await p.screenshot({path:out+'/friend-'+name+'.png'});
      const fits=await p.evaluate(()=>({overflow:document.documentElement.scrollHeight>innerHeight+1||document.documentElement.scrollWidth>innerWidth+1,
        options:[...document.querySelectorAll('#choices button')].every(e=>e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth+1),
        bottom:document.querySelector('#leave').getBoundingClientRect().bottom,height:innerHeight}));
      assert(!fits.overflow&&fits.options&&fits.bottom<=fits.height,JSON.stringify(fits));
      const canvas=await p.locator('#stadium-layer canvas').screenshot();
      const stats=await sharp(canvas).stats();assert(stats.channels.some(c=>c.stdev>5),'Stadium must not be blank');
    }
    await a.locator('#choices button').first().click();
    await a.locator('#feedback').filter({hasText:'Answer locked'}).waitFor();
    assert.equal(await b.locator('#choices .correct').count(),0);
    await b.locator('#choices button').nth(1).click();
    await a.waitForFunction(()=>/Goal|Saved|Replay/.test(document.getElementById('feedback').textContent));
    await b.waitForFunction(()=>/Goal|Saved|Replay/.test(document.getElementById('feedback').textContent));
    const before=await host.request.get(origin+'/api/players/me');const xp=(await before.json()).total_xp;
    await a.locator('#leave').click();await a.locator('#summary:not([hidden])').waitFor();await b.locator('#summary:not([hidden])').waitFor();
    assert((await a.locator('#result-metrics').textContent()).includes('No XP or rating'));
    assert((await b.locator('#result-heading').textContent()).includes('won'));
    await b.screenshot({path:out+'/friend-result-mobile.png'});
    assert.equal((await (await host.request.get(origin+'/api/players/me')).json()).total_xp,xp);
    await a.locator('#another').click();assert.equal(await a.locator('#shootout-board').isVisible(),false);
    await a.goto(origin+'/daily');await a.locator('#start:enabled').waitFor();await a.locator('#start').click();
    await a.locator('#next:not([hidden]):enabled').waitFor();await a.locator('#next').click();
    await a.locator('#choices button:enabled').first().waitFor();await a.screenshot({path:out+'/daily-desktop.png'});
    await a.locator('#leave').click();await a.locator('#summary:not([hidden])').waitFor();
    await a.goto(origin+'/leaderboard?metric=daily_wins');assert(await a.locator('input[value="daily_wins"]').isChecked());
    assert.deepEqual(errors,[]);console.log('PASS: registered Daily, real two-player invitation/answers, private answers, zero Friend XP, mobile/desktop geometry, nonblank stadium, results and Daily leaderboard');
  }catch(e){for(const ctx of browser.contexts())for(const [i,p] of ctx.pages().entries())await p.screenshot({path:out+'/error-'+ctx.pages().length+'-'+i+'.png'}).catch(()=>{});throw e;}
  finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
