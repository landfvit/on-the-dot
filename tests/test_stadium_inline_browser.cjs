/* Real local Three.js, mocked gameplay. Verify geometry AND stable UI slots. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/tmp/on-the-dot-inline';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const question={text:'At which ground did Cardiff City stage their home Premier League matches in 2018/19?',options:[{id:'a',text:'Cardiff City Stadium'},{id:'b',text:"St Mary's Stadium"},{id:'c',text:'Riverside Stadium'},{id:'d',text:'bet365 Stadium'}]};
const longQuestion={...question,text:'Which of these Aston Villa players was a goalkeeper in the 2023/24 Premier League season: Youri Tielemans, Emiliano Martinez, Douglas Luiz or John McGinn?',options:[{id:'a',text:'Emiliano Martinez'},{id:'b',text:'Youri Tielemans'},{id:'c',text:'Douglas Luiz'},{id:'d',text:'John McGinn'}]};
function fresh(){return {run_id:'inline-test',phase:'ANSWERING',position:1,role:'shooter',question,review:[],rules,deadline:Date.now()+60000,
    difficulty:'easy',category:{label:'Mixed topics'},is_trial:true,total_xp:0,correct:0,base_xp:0,bonus_xp:0,multiplier:1,
    shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},round:1,next_role:'shooter',attempts:[]}};}
const bounds=page=>page.evaluate(()=>Object.fromEntries(['#stadium-stage','#question-title','#choices','#question-panel > .actions'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return[s,[r.x,r.y,r.width,r.height]];})));
const headerBounds=page=>page.evaluate(()=>Object.fromEntries(['.public-header','.brand-mark','[data-nav-slot=leaderboard]','[data-nav-slot=profile]','[data-theme-toggle]','[data-sound-toggle]'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return[s,[r.x,r.y,r.width,r.height]];})));
async function fits(page){
    // Text fitting runs on RAF after the controller replaces the options.
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    const issues=await page.evaluate(()=>{
        const problems=[];
        for(const selector of ['#stadium-stage','#question-title','#choices button','#next','#question-panel > .actions','#leave'])for(const e of document.querySelectorAll(selector)){
            const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;
            if(r.left<0||r.right>innerWidth+1||r.top<0||r.bottom>innerHeight+1||e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1)problems.push(selector);
        }
        if(document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight+1)problems.push('page overflow');
        return problems;
    });assert.deepEqual(issues,[]);
    const alignment=await page.evaluate(()=>{
        const header=document.querySelector('.public-header').getBoundingClientRect(),problems=[];
        const selectors=['.solo-page','.solo-heading'];
        if(!matchMedia('(min-width:600px) and (max-height:600px)').matches)selectors.push('#stadium-stage','#question-title','#answer-slot');
        for(const selector of selectors){
            const r=document.querySelector(selector).getBoundingClientRect();
            if(Math.abs(r.left-header.left)>1||Math.abs(r.right-header.right)>1)problems.push(selector);
        }
        return problems;
    });assert.deepEqual(alignment,[],'Navigation, Back, stadium and answers share both content edges');
}
(async()=>{
 const engine=process.env.TEST_BROWSER||'chrome';
 const gpuArgs=process.env.TEST_GPU==='native'?[]:['--enable-unsafe-swiftshader','--use-angle=swiftshader'];
 const browser=engine==='webkit'?await webkit.launch({headless:true}):await chromium.launch({channel:'chrome',headless:true,args:gpuArgs});
 try{
  for(const [width,height] of [[320,568],[390,700],[800,900],[845,813],[844,390],[1440,900],[2560,1440]]){
   if(process.env.TEST_WIDTH&&width!==Number(process.env.TEST_WIDTH))continue;
   const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:2}),errors=[],writes=[];
   let run=fresh();page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;let data;
    if(req.method()!=='GET')writes.push(path);
    if(path==='/api/players/me')return process.env.TEST_KIT
      ?route.fulfill({json:{username:'kit_player',outfit:{kit_id:'64-2026-home',number:27}}})
      :route.fulfill({status:401,json:{detail:'Sign in'}});
    if(path==='/api/solo/catalog')data={topics:[{code:'ALL',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
    else if(path==='/api/solo/active')data={run:run?{...run,server_now:Date.now()}:null};
    else if(path==='/api/solo/runs/inline-test/answers'){
     const answer={position:run.position,option_id:'a',is_correct:true,correct:'a',outcome:run.role==='shooter'?'goal':'save',text:run.question.text,options:run.question.options};
     const done=run.position===2;
     run={...run,phase:done?'FINISHED':'REVIEW',correct:run.correct+1,total_xp:done?40:10,review:[...run.review,answer],deadline:null,
       shootout:{...run.shootout,player:1,next_role:'keeper',kicks:{player:1,opponent:done?1:0},winner:done?'player':null,
       attempts:[{side:'player',goal:true},...(done?[{side:'opponent',goal:false}]:[])]}};data=run;
    }else if(path==='/api/solo/runs/inline-test/next'){
     run={...run,phase:'ANSWERING',position:2,role:'keeper',question:longQuestion,deadline:Date.now()+60000};data=run;
    }else if(path==='/api/solo/runs/inline-test')data=run;
    else if(path==='/api/shares/results')data={title:'Test result',url:origin+'/r/test',image_url:origin+'/share/brand.png?v=4'};
    else throw Error('Unexpected test request '+path);
    await route.fulfill({json:data===run?{...data,server_now:Date.now()}:data});
   });
   try{
    await page.goto(origin+'/penalties');
    await page.waitForFunction(()=>PointsStadium?.inspect().active&&!PointsStadium.inspect().entering);
    if(process.env.TEST_KIT)await page.waitForFunction(()=>PointsStadium.inspect().strikerOutfit==='64-2026-home');
    await fits(page);const original=await bounds(page),header=await headerBounds(page);
    const scene=await page.evaluate(()=>PointsStadium.inspect());
    if(process.env.TEST_KIT)assert.equal(scene.strikerNumber,27,'Account outfit reaches the actual game bridge');
    assert.equal(scene.presentation,'compact');assert(scene.strikerVisible);
    assert(scene.framing.every(([x,y,z])=>Math.abs(x)<1&&Math.abs(y)<1&&Math.abs(z)<1),'Goal, net and both players must fit');
    if(process.env.TEST_GPU==='native')console.log('Renderer:',await page.locator('#stadium-layer canvas').evaluate(canvas=>{
     const gl=canvas.getContext('webgl2'),info=gl.getExtension('WEBGL_debug_renderer_info');
     return gl.getParameter(info?info.UNMASKED_RENDERER_WEBGL:gl.RENDERER);
    }));
    assert(scene.renderSize[0]*scene.renderSize[1]<=1600000);assert(scene.renderSize[1]>50);
    assert.equal(scene.goalColor,0xffffff);assert.equal(scene.netColor,0xffffff);assert(scene.markingsVisible);
    assert(!await page.evaluate(()=>document.body.classList.contains('stadium-playing')));
    assert.equal(await page.locator('[data-theme-toggle]:visible').count(),1);
    assert.equal(await page.locator('[data-sound-toggle]:visible').count(),1);
    assert.equal(await page.getByRole('link',{name:'How to play',exact:true}).count(),1);
    const pixelStats=await sharp(await page.locator('#stadium-layer canvas').screenshot()).stats();assert(pixelStats.channels.some(c=>c.stdev>10));
    await page.screenshot({path:`${out}/${engine}-${width}-shooter.png`});
    await page.locator('#choices button').first().click();
    await page.waitForFunction(()=>PointsStadium.inspect().phase==='shot');
    assert(!await page.locator('#next').isVisible(),'Answer feedback stays visible during the kick');
    assert(await page.locator('#choices button.correct').isVisible());
    const initial=await page.evaluate(()=>PointsStadium.inspect());
    await page.waitForFunction(ball=>PointsStadium.inspect().ball.some((n,i)=>Math.abs(n-ball[i])>.1),initial.ball);
    await page.locator('#next:enabled:not([hidden])').waitFor();
    assert.equal(await page.locator('#next').textContent(),'Next penalty');
    assert(!await page.locator('#choices').isVisible(),'Continue replaces the answers');
    assert.deepEqual(await page.locator('#next').boundingBox(),await page.locator('#choices').boundingBox(),'Continue fills the entire answer slot');
    await fits(page);
    await page.screenshot({path:`${out}/${engine}-${width}-next-penalty.png`});
    assert.deepEqual(await bounds(page),original,'Camera, clock and result must not move question controls');
    assert.equal((await page.evaluate(()=>PointsStadium.inspect())).role,'keeper');
    if(process.env.TEST_KIT){
     const dressed=await page.evaluate(()=>PointsStadium.inspect());
     assert.equal(dressed.keeperOutfit,'64-2026-home');assert.equal(dressed.keeperNumber,27);
    }
    assert((await page.evaluate(()=>PointsStadium.inspect())).framing.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1));
    await page.locator('#next').click();await page.locator('#choices button:enabled').first().waitFor();
    assert.equal(await page.locator('#question-title').textContent(),'Which of these Aston Villa players was a goalkeeper in the 2023/24 Premier League season?');
    await fits(page);assert.deepEqual(await bounds(page),original,'Long question uses the same slots');
    for(const theme of ['light','dark']){
     await page.evaluate(t=>{document.documentElement.dataset.theme=t;dispatchEvent(new CustomEvent('points-theme'));},theme);
     await page.screenshot({path:`${out}/${engine}-${width}-keeper-${theme}.png`});
    }
    await page.evaluate(()=>{
     window.outroFrames=[];const r=document.querySelector('#stadium-layer').getBoundingClientRect();
     window.preOutroBounds=[r.left,r.top,r.width,r.height];
     const sample=()=>{
      const stage=document.querySelector('#stadium-stage');
      if(stage.hidden)return;
      if(stage.dataset.ending){const b=document.querySelector('#stadium-layer').getBoundingClientRect();outroFrames.push([b.left,b.top,b.width,b.height]);}
      requestAnimationFrame(sample);
     };requestAnimationFrame(sample);
    });
    await page.locator('#choices button').first().click();
    await page.waitForFunction(()=>PointsStadium.inspect().caught);
    assert.deepEqual(await bounds(page),original,'The last kick must finish before replacing the game layout');
    const catchState=await page.evaluate(()=>PointsStadium.inspect());
    assert(catchState.ball.every((n,i)=>Math.abs(n-catchState.hands[i])<.001));
    await page.locator('#stadium-stage').waitFor({state:'hidden',timeout:15000});
    const outro=await page.evaluate(()=>({frames:outroFrames,bounds:preOutroBounds}));
    assert(outro.frames.length>0,'Observe the result crossfade');
    for(const frame of outro.frames)assert(frame.every((n,i)=>Math.abs(n-outro.bounds[i])<1),'Crossfade must not resize or move the view');
    await page.locator('#summary').waitFor();
    assert.deepEqual(await headerBounds(page),header,'Result must not move the header');
    assert(await page.locator('#summary').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight&&e.scrollHeight<=e.clientHeight+1),'Result must fit');
    assert(await page.locator('.public-header').isVisible(),'Navigation survives the outro');
    const contentEdges=async selector=>page.locator(selector).evaluate(e=>{const r=e.getBoundingClientRect();return [r.left,r.right];});
    assert.deepEqual(await contentEdges('#summary'),await contentEdges('.public-header'),'Results keep the shared content width');
    await page.screenshot({path:`${out}/${engine}-${width}-result.png`});
    await page.locator('#result-review').click();await page.locator('#review-next').click();
    assert.equal(await page.locator('#review h3').textContent(),'Which of these Aston Villa players was a goalkeeper in the 2023/24 Premier League season?');
    assert(await page.locator('#review-dialog').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}));
    await page.locator('#review-close').click();
    await page.evaluate(()=>Object.defineProperty(navigator,'share',{value:undefined,configurable:true}));
    await page.locator('#share-result').click();await page.locator('#share-dialog').waitFor();
    assert(await page.locator('#share-dialog').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight&&e.scrollWidth<=e.clientWidth+1;}));
    const shareActions=await page.locator('#share-dialog .actions button').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return [r.y,r.height];}));
    assert.deepEqual(shareActions[0],shareActions[1],'Share actions align even when one label wraps');
    await page.screenshot({path:`${out}/${engine}-${width}-share.png`});await page.locator('#share-close').click();
    await page.locator('#another').click();assert(!await page.locator('#stadium-stage').isVisible());
    assert.deepEqual(await headerBounds(page),header,'Restart must not move the header');
    assert(await page.locator('#selection').isVisible());
    for(const selector of ['#selection','.solo-heading','.site-footer'])assert.deepEqual(await contentEdges(selector),await contentEdges('.public-header'),`${selector} aligns after restart`);
    assert.deepEqual(writes,['/api/solo/runs/inline-test/answers','/api/solo/runs/inline-test/next','/api/solo/runs/inline-test/answers','/api/shares/results']);
    assert.deepEqual(errors,[]);console.log(`PASS ${engine} inline ${width}: pixels, motion, stable slots, catch, result, restart`);
   }catch(e){await page.screenshot({path:`${out}/${engine}-${width}-failure.png`});throw e;}
   finally{await page.close();}
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
