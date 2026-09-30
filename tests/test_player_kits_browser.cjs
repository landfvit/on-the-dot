/* Mock accounts and writes; real local catalogue, pixel painter and WebGL. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin='http://127.0.0.1:8009',out='/private/tmp/on-the-dot-kits';fs.mkdirSync(out,{recursive:true});
const base={username:'kit_player',bio:'',accent:'green',email:'kit@example.invalid',club:{team_id:64,name:'Hull City',season:2026},
 outfit:{kit_id:'64-2026-home',number:27},stats:{wins:3,losses:2,played:5,win_rate:60},total_xp:130,level:2,level_xp:100,next_level_xp:300,
 streak:{current:2,longest:3},completed_quizzes:5,team_change:{can_change:true,next_change_at:null},preferences:{animations:true,reduced_motion:false}};
(async()=>{
 const kind=process.env.TEST_BROWSER||'chrome',browser=kind==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[320,700],[390,844],[1440,960]]){
   const page=await browser.newPage({viewport:{width,height}}),errors=[],writes=[];let user=structuredClone(base);
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    const request=route.request(),p=new URL(request.url()).pathname;let data;
    if(p==='/api/players/me')data=user;
    else if(p==='/api/players/settings')data={password_reset_available:false};
    else if(p==='/api/players/friends')data={friends:[]};
    else if(p==='/api/players/me/outfit'){
      writes.push(request.postDataJSON());user.outfit=request.postDataJSON();data={outfit:user.outfit};
    }else throw Error('Unexpected API '+p);
    await route.fulfill({json:data});
   });
   await page.goto(origin+'/account');await page.locator('#kit-form:not([hidden])').waitFor();
   assert.equal(await page.locator('#kit-options input').count(),3);
   assert.equal(await page.locator('#kit-sources,.profile-kit details').count(),0,'No references disclosure in the kit picker');
   assert(await page.locator('#kit-options label').evaluateAll(es=>es.every(e=>!e.textContent.trim()&&!!e.querySelector('input').getAttribute('aria-label'))),'Thumbnails have accessible names but no visible captions');
   assert((await page.locator('#kit-options input').evaluateAll(es=>es.map(e=>e.value))).every(id=>id.startsWith('64-')));
   assert.equal(await page.locator('#kit-team').count(),0,'No selector for another member club');
   await page.locator('#kit-options label').nth(1).click();await page.locator('#kit-number').fill('99');
   await page.locator('#kit-save').click();await page.getByText('Kit saved.',{exact:true}).waitFor();
   assert.deepEqual(writes,[{kit_id:'64-2026-away',number:99}]);
   await page.reload();await page.locator('#kit-form:not([hidden])').waitFor();
   assert.equal(await page.locator('#kit-number').inputValue(),'99');
   assert.equal(await page.locator('#kit-options :checked').inputValue(),'64-2026-away');
   await page.locator('#kit-options label').first().click();await page.locator('#kit-number').fill('27');
   await page.locator('.profile-kit').scrollIntoViewIfNeeded();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const artwork=await page.locator('.profile-kit canvas').evaluateAll(es=>es.map(e=>e.toDataURL()));
   for(const theme of ['light','dark']){
    await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
    assert.deepEqual(await page.locator('.profile-kit canvas').evaluateAll(es=>es.map(e=>e.toDataURL())),artwork,'Theme does not recolor the kits');
    assert(await page.locator('.kit-options label,.kit-preview-images').evaluateAll(es=>es.every(e=>getComputedStyle(e).backgroundColor==='rgb(231, 234, 226)'&&getComputedStyle(e).backgroundImage==='none')),'Every preview uses the same plain display surface');
    assert.equal(await page.locator('.kit-preview-images').evaluate(e=>getComputedStyle(e,'::after').content),'none','No line beneath the large kit preview');
    const footerGap=await page.evaluate(()=>document.querySelector('.site-footer').getBoundingClientRect().top-document.querySelector('.profile-links').getBoundingClientRect().bottom);
    assert(footerGap>=16&&footerGap<=24,'Profile footer follows the buttons without the old stacked margins: '+footerGap);
    if(width>600)assert(await page.evaluate(()=>Math.abs(document.querySelector('#kit-options').getBoundingClientRect().top-document.querySelector('.kit-preview-images').getBoundingClientRect().top)<1),'Thumbnail row and large preview share a top edge');
    assert(await page.locator('.kit-preview canvas,.kit-options canvas').evaluateAll(es=>es.every(e=>{const a=e.getBoundingClientRect(),b=e.parentElement.getBoundingClientRect();return a.left>=b.left&&a.right<=b.right&&a.top>=b.top&&a.bottom<=b.bottom;})),'All kits fit their backdrop');
    await page.locator('.profile-kit').screenshot({path:`${out}/${kind}-${width}-profile-${theme}.png`});
    await page.screenshot({path:`${out}/${kind}-${width}-account-${theme}.png`,fullPage:true});
   }
   const pixelTests=await page.evaluate(async()=>{
    const {loadKits,kitPixels}=await import('/trivia-assets/kit_pixels.js?v=4'),data=await loadKits();
    const signatures=new Set(Array.from({length:99},(_,i)=>JSON.stringify(kitPixels(data.kits.find(k=>k.id==='64-2026-home'),'back',i+1))));
    const all=data.kits.every(k=>['front','back','sleeve','shorts','sock'].every(part=>{
      const p=kitPixels(k,part,99);return p.rows.every(row=>[...row].every(key=>key==='.'||Number.isInteger(p.colors[key])));
    }));
    return {unique:signatures.size,all};
   });assert.deepEqual(pixelTests,{unique:99,all:true});
   user={...user,club:null,outfit:{kit_id:null,number:10}};await page.reload();await page.getByText('Join a team to choose its kit.',{exact:true}).waitFor();
   assert(!await page.locator('#kit-form').isVisible());assert.deepEqual(errors,[]);await page.close();
   console.log(`PASS ${kind} profile ${width}: own team only, three sets, save/reload, 99 numbers, no team, all pixel palettes`);
  }
  for(const [width,height] of [[748,270],[366,170]]){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/kit-scene-test',r=>r.fulfill({contentType:'text/html',body:'<style>body{margin:0;background:#f6f3eb}#host{position:fixed;inset:0}#frame{position:fixed;inset:8px}</style><div id="host"></div><div id="frame"></div>'}));
   await page.goto(origin+'/kit-scene-test');
   await page.evaluate(async()=>{
    const {loadKits}=await import('/trivia-assets/kit_pixels.js?v=4');const data=await loadKits();window.kits=data.kits;
    const {createStadium}=await import('/trivia-assets/stadium_scene.js?v=36');
    window.engine=createStadium(document.querySelector('#host'),document.querySelector('#frame'),e=>{throw e;});
    window.pair=[{kit:kits.find(k=>k.id==='64-2026-home'),number:27},{kit:kits.find(k=>k.id==='33-2026-home'),number:11}];
    engine.setOutfits(pair);await engine.setView('shooter');
   });
   const camera=(await page.evaluate(()=>engine.inspect())).camera;
   for(const role of ['shooter','keeper']){
    await page.evaluate(role=>engine.setView(role),role);const s=await page.evaluate(()=>engine.inspect());
    assert.deepEqual(s.camera,camera);assert.equal(s.strikerOutfit,role==='shooter'?'64-2026-home':'33-2026-home');
    assert.equal(s.keeperOutfit,role==='keeper'?'64-2026-home':'33-2026-home');
    assert.equal(s.strikerNumber,role==='shooter'?27:11);
    assert(s.framing.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1));
    // Every pair spans the pitch width at the same depth and elevation.
    // Horizontal screen coordinates catch accidental yaw/roll, not only a
    // camera that happens to stay stationary between the two roles.
    for(const [left,right] of [[0,2],[1,3],[4,6],[5,7],[8,10],[9,11]]){
      assert(Math.abs(s.framing[left][1]-s.framing[right][1])<1e-8,'Pitch edges must be parallel to the UI rules');
    }
    const bytes=await page.screenshot({path:`${out}/${kind}-${width}-${role}.png`});
    assert((await sharp(bytes).stats()).channels.some(c=>c.stdev>15));
   }
   await page.evaluate(()=>engine.shot('save',false,{target:{side:1,high:true},keeper:{side:1,high:true}}));
   const saved=await page.evaluate(()=>engine.inspect());assert(saved.caught);assert(saved.ball.every((v,i)=>Math.abs(v-saved.hands[i])<.001));
   const counts=await page.evaluate(()=>{
    const values=[];for(let i=0;i<100;i++){engine.setOutfits([{kit:kits[i%kits.length],number:i%99+1},pair[1]]);values.push(engine.inspect().spriteTextures);}return values;
   });assert(Math.max(...counts)-Math.min(...counts)<8,'Cosmetic changes do not leak textures');
   await page.evaluate(()=>{engine.setOutfits(pair);engine.setOutfits([null,null]);engine.setOutfits(pair);engine.setView('shooter');});
   await page.screenshot({path:`${out}/${kind}-${width}-restored.png`});
   assert.deepEqual(errors,[]);await page.evaluate(()=>engine.dispose());await page.close();
   console.log(`PASS ${kind} scene ${width}: patterned kits, role swapping, fixed rear camera, saves and 100 outfit changes`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
