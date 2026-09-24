/* Local disposable fixture only. Real APIs, including guest identity cookies. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright'),sharp=require('sharp');
const origin='http://127.0.0.1:8015',out='/tmp/on-the-dot-social';fs.mkdirSync(out,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
  const errors=[];
  try{
    const aCtx=await browser.newContext({viewport:{width:390,height:664},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    const bCtx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
    // Exercise the in-page fallback deterministically, not the host OS sheet.
    await aCtx.addInitScript(()=>Object.defineProperty(navigator,'share',{value:undefined,configurable:true}));
    const a=await aCtx.newPage(),b=await bCtx.newPage();for(const p of [a,b])p.on('pageerror',e=>errors.push(e.message));
    let publishes=0;a.on('request',r=>{if(r.url().endsWith('/api/shares/results'))publishes++;});
    await a.goto(origin+'/friends');await a.locator('#start:enabled').click();
    await a.locator('#mode-intro[open]').waitFor();
    assert.equal((await aCtx.request.get(origin+'/api/friends/active')).status(),200);
    assert.equal((await (await aCtx.request.get(origin+'/api/friends/active')).json()).code,null);
    await a.screenshot({path:out+'/first-game-rules-mobile.png'});
    await a.locator('#mode-intro button[value=cancel]').click();
    await a.locator('#start:enabled').click();await a.locator('#mode-intro button[value=play]').click();
    await a.locator('#friend-lobby:not([hidden])').waitFor();const invite=await a.locator('#invite-link').inputValue();
    await b.goto(invite);await b.locator('#friend-join').click();await b.locator('#mode-intro button[value=play]').click();
    await a.locator('#friend-ready:enabled').waitFor();await a.locator('#friend-ready').click();
    await a.locator('#question-title').filter({hasText:'Waiting for Friend'}).waitFor();
    await b.locator('#friend-ready:enabled').click();await a.locator('#choices button:enabled').first().waitFor();
    assert.equal(await a.locator('#name-player').textContent(),'You');assert.equal(await a.locator('#name-opponent').textContent(),'Friend');
    await a.screenshot({path:out+'/guest-duel-mobile.png'});
    await a.locator('#leave').click();await a.locator('#forfeit-confirm').click();await a.locator('#summary:not([hidden])').waitFor();
    assert.equal(publishes,0);await a.screenshot({path:out+'/guest-result-mobile.png'});
    await a.locator('#share-result').click();await a.locator('#share-dialog[open]').waitFor();
    assert.equal(publishes,1);const link=await a.locator('#share-link').inputValue();assert.match(link,/\/s\/[A-Za-z0-9_-]{32}$/);
    assert.equal(await a.locator('#share-card-link').getAttribute('href'),link);
    await a.waitForFunction(()=>document.getElementById('share-preview').naturalWidth===1200);
    await a.screenshot({path:out+'/share-dialog-mobile.png'});
    await a.locator('#share-card-link').click();assert.equal(a.url(),link);
    assert.equal(await a.locator('meta[property="og:url"]').getAttribute('content'),link);
    const png=await aCtx.request.get(link+'/image.png');assert(png.ok());fs.writeFileSync(out+'/result-preview.png',await png.body());
    assert((await sharp(await png.body()).stats()).channels.some(c=>c.stdev>20));
    await a.screenshot({path:out+'/public-result-mobile.png'});
    await a.goto(origin+'/');await a.locator('.page-return [data-share-game]').click();
    await a.locator('#game-share-dialog[open]').waitFor();assert.equal(await a.locator('#game-share-link').inputValue(),origin+'/');
    await a.screenshot({path:out+'/home-share-mobile.png'});
    // Registered friendship flow and simplified profile.
    const c1=await browser.newContext({viewport:{width:390,height:664}}),c2=await browser.newContext({viewport:{width:1440,height:900}});
    for(const [ctx,identifier,password] of [[c1,'player@example.com','test-only-password-1234'],[c2,'friend@example.com','test-password-1234']]){
      const r=await ctx.request.post(origin+'/api/players/login',{data:{identifier,password}});assert.equal(r.status(),200);
    }
    const p=await c1.newPage(),q=await c2.newPage();for(const x of [p,q])x.on('pageerror',e=>errors.push(e.message));
    await p.goto(origin+'/account');await p.locator('#own-profile:not([hidden])').waitFor();
    assert(!await p.locator('#password-edit').isVisible());assert(await p.locator('#add-team').isVisible());
    await p.screenshot({path:out+'/profile-mobile.png'});
    await p.locator('[data-profile-tab=friends]').click();await p.locator('#friend-username').fill('test_friend');await p.locator('#friend-add button').click();
    await p.locator('#friend-list').filter({hasText:'Sent requests'}).waitFor();
    await q.goto(origin+'/account');await q.locator('[data-profile-tab=friends]').click();await q.getByRole('button',{name:'Accept',exact:true}).click();
    await q.getByRole('link',{name:'Invite to duel'}).waitFor();await q.screenshot({path:out+'/friends-desktop.png'});
    await p.locator('[data-profile-tab=overview]').click();await p.locator('[data-profile-tab=friends]').click();
    await p.getByRole('link',{name:'Invite to duel'}).click();await p.locator('#start:enabled').click();await p.locator('#mode-intro button[value=play]').click();
    await p.locator('#lobby-status').filter({hasText:'Invitation sent to test_friend'}).waitFor();
    await q.locator('[data-profile-tab=overview]').click();await q.locator('[data-profile-tab=friends]').click();await q.getByRole('link',{name:'Join invitation'}).waitFor();
    await q.screenshot({path:out+'/friend-invitation-desktop.png'});
    await p.locator('#friend-leave').click();await p.locator('#forfeit-confirm').click();
    await p.goto(origin+'/account');await p.locator('[data-profile-tab=settings]').click();await p.locator('summary').filter({hasText:/^Password$/}).click();
    assert(await p.locator('#password-edit').isVisible());await p.screenshot({path:out+'/settings-mobile.png'});
    assert.deepEqual(errors,[]);console.log('PASS: first-use cancellation, guest duel, public result rich link, home logo card, friends request/accept/invite, compact profile/settings');
  }catch(e){for(const ctx of browser.contexts())for(const [i,p] of ctx.pages().entries())await p.screenshot({path:out+'/error-'+browser.contexts().indexOf(ctx)+'-'+i+'.png'}).catch(()=>{});throw e;}
  finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
