/* Real routes on the disposable tests.challenge_preview server only. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright'),sharp=require('sharp');
const origin='http://127.0.0.1:8015',out='/tmp/on-the-dot-survival';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const ctx=await browser.newContext({viewport:{width:390,height:664},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const username='survival_'+Date.now();
  const registration=await ctx.request.post(origin+'/api/players/register',{data:{username,email:username+'@example.com',password:'test-only-password'}});
  assert.equal(registration.status(),201,await registration.text());
  for(const route of ['/','/how-to-play']){
   await page.goto(origin+route);assert.equal(await page.locator('.brand-mark').count(),1);
   assert.equal(await page.locator('.home-logo,.brand-wordmark').count(),0);
   assert(await page.locator('.brand-mark').evaluate(e=>e.complete&&e.naturalWidth>0));
  }
  await page.goto(origin+'/daily');await page.locator('#start:enabled').click();
  await page.locator('#mode-intro button[value=play]').click();await page.locator('#next:enabled').waitFor();
  await page.waitForFunction(()=>PointsAudio.inspect().crowdReady);
  await page.evaluate(()=>{window.cues=[];const play=PointsAudio.play;PointsAudio.play=n=>{const ok=play(n);cues.push({name:n,ok});return ok;};});
  const active=(await (await ctx.request.get(origin+'/api/daily/active')).json()).run;assert(active.survival.ranked);
  const path=origin+'/api/daily/runs/'+active.run_id;
  for(const theme of ['light','dark']){
   await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;window.dispatchEvent(new CustomEvent('points-theme',{detail:{theme}}));},theme);
   for(const size of [[390,664],[1440,900]]){
    await page.setViewportSize({width:size[0],height:size[1]});
    await page.waitForTimeout(200);
    const state=await page.evaluate(()=>PointsStadium.inspect());assert.equal(state.goalColor,0xffffff);assert.equal(state.netColor,0xffffff);assert.equal(state.markingsColor,0xffffff);
    const canvas=await page.locator('#stadium-layer canvas').screenshot(),stats=await sharp(canvas).stats();assert(stats.channels.some(c=>c.stdev>5));
    await page.screenshot({path:`${out}/ready-${theme}-${size[0]}.png`});
   }
  }
  await page.setViewportSize({width:390,height:664});
  let result=active,previous=0;
  for(let i=0;i<30&&!['FINISHED','ABANDONED'].includes(result.phase);i++){
   await page.locator('#next:enabled').click();await page.locator('#choices button:enabled').first().waitFor();
   const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollHeight>innerHeight+1||document.documentElement.scrollWidth>innerWidth+1,
    next:document.getElementById('leave').getBoundingClientRect().bottom,roles:document.getElementById('run-position').textContent}));
   assert(!geometry.overflow,JSON.stringify(geometry));assert(geometry.next<=664);assert(!geometry.roles.includes('Defending'));
   assert.equal(await page.locator('#name-opponent').isVisible(),false);assert.equal(await page.locator('.daily-life').count(),3);
   assert.match(await page.locator('#seconds').textContent(),/^\d+ s$/);
   assert.equal(await page.locator('#stadium-clock,#stadium-score,#stadium-role').count(),0);
   await page.locator('#choices button').first().click();
   await page.waitForFunction(()=>!document.getElementById('summary').hidden||!document.getElementById('next').disabled);
   result=await (await ctx.request.get(path)).json();assert.equal(result.role,'shooter');
   if(result.phase==='REVIEW'){
    const answer=result.review.at(-1),correct=answer.options.find(o=>o.id===answer.correct).text;
    assert.equal(await page.locator('#feedback').textContent(),'');
    assert.equal(await page.locator('#choices .correct').textContent(),correct);
    assert.equal(await page.locator('.answer-selection').count(),0);
   }
   assert(result.survival.goals>=previous);previous=result.survival.goals;
   assert.equal(result.survival.lives,3-result.review.filter(a=>!a.is_correct).length);
  }
  assert.equal(result.phase,'FINISHED');assert.equal(result.end_reason,'lives_exhausted');
  await page.locator('#summary:not([hidden])').waitFor();await page.waitForFunction(()=>document.getElementById('result-heading')===document.activeElement);
  assert.equal(await page.locator('#result-heading').textContent(),'Daily Challenge complete');
  assert(!await page.locator('#summary').evaluate(e=>e.scrollHeight>e.clientHeight+1));
  await page.screenshot({path:out+'/results-mobile.png'});
  const cues=await page.evaluate(()=>cues.filter(c=>c.name.startsWith('crowd-')));
  assert(cues.some(c=>c.name==='crowd-groan'&&c.ok));assert(cues.every(c=>c.ok));
  const best=result.highscore;assert.equal(best,result.survival.goals);
  await page.locator('#another').click();await page.locator('#start:enabled').waitFor();
  assert.equal(await page.locator('#start').textContent(),'Play practice');assert.equal(await page.locator('#shootout-board').isVisible(),false);
  await page.locator('#start').click();await page.locator('#next:enabled').waitFor();
  const practice=(await (await ctx.request.get(origin+'/api/daily/active')).json()).run;assert(!practice.survival.ranked);assert.equal(practice.survival.lives,3);
  await page.locator('#leave').click();await page.locator('#summary:not([hidden])').waitFor();
  const rankings=await (await ctx.request.get(origin+'/api/community/leaderboard?metric=daily_highscore')).json();
  assert.equal(rankings.me.daily_highscore,best);assert.equal(rankings.period,'all');
  await page.goto(origin+'/leaderboard?metric=daily_highscore');await page.locator('#ranking-rows tr').first().waitFor();
  assert(await page.locator('input[name=period][value=all]').isChecked());assert(await page.locator('input[name=period][value=today]').isDisabled());
  assert.deepEqual(errors,[]);console.log('PASS real Daily: 3 lives, shooter only, one ranked attempt, practice, highscore, real audio, white goal/net, mobile/desktop, both themes.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
