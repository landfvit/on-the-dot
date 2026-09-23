// Opt-in real-browser test. Creates isolated anonymous test games and ends them.
// Run against the existing development server; it never publishes trivia content.
const {chromium} = require('playwright');
const {PNG} = require('pngjs');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = 'http://127.0.0.1:8002';
const out = path.resolve('data/private/stadium-ui-check');
fs.mkdirSync(out, {recursive:true});

async function screenshot(page, name) {
    const bytes = await page.screenshot({path:path.join(out,name+'.png')});
    const png=PNG.sync.read(bytes), rect=await page.locator('#stadium-framing').boundingBox();
    let lit=0,count=0;
    for(let y=Math.ceil(rect.y);y<Math.min(png.height,rect.y+rect.height);y++){
        for(let x=Math.ceil(rect.x);x<Math.min(png.width,rect.x+rect.width);x++){
            const i=(y*png.width+x)*4;
            if(png.data[i]+png.data[i+1]+png.data[i+2]>280)lit++;
            count++;
        }
    }
    assert(lit>150&&lit<count*.75,`${name}: v6 canvas must contain lit geometry on a dark pitch (${lit}/${count})`);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}: horizontal overflow`);
    return {name,litPixels:lit,totalPixels:count};
}

(async()=>{
    const browser=await chromium.launch({headless:true,channel:'chrome'}),errors=[],results=[];
    const contexts=[];
    let soloRun=null,soloContext=null,room=null,host=null,guest=null;
    async function context(options={}) {
        const c=await browser.newContext({viewport:{width:1440,height:1000},...options});contexts.push(c);
        c.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));return c;
    }
    try {
        soloContext=await context();const page=await soloContext.newPage();
        await page.goto(base+'/penalties');await page.locator('#start:not([disabled])').waitFor();
        const started=page.waitForResponse(r=>r.url().endsWith('/api/solo/runs')&&r.request().method()==='POST');
        await page.locator('#start').click();const data=await(await started).json();soloRun=data.run_id;
        assert.equal(data.phase,'READY');
        await page.waitForFunction(()=>window.PointsStadium?.inspect().entering);
        const from=await page.evaluate(()=>PointsStadium.inspect().camera);
        await page.waitForTimeout(900);
        const moving=await page.evaluate(()=>PointsStadium.inspect().camera);
        assert.notDeepEqual(moving,from,'Intro camera must move');
        const before=(await soloContext.request.get(base+'/api/solo/runs/'+soloRun));
        assert.equal((await before.json()).phase,'READY','Intro must not start the question clock');
        results.push(await screenshot(page,'solo-tunnel'));
        await page.waitForFunction(()=>PointsStadium.inspect().camera[2]<35&&PointsStadium.inspect().focus===0);
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().standsSolid),true);
        assert.equal(await page.locator('.solo-questions').evaluate(el=>getComputedStyle(el).opacity),'0');
        results.push(await screenshot(page,'solid-stands'));
        await page.waitForFunction(()=>{const s=PointsStadium.inspect();return s.focus>.25&&s.focus<.7;});
        const transition=await page.evaluate(()=>{
            const s=PointsStadium.inspect(),panel=document.querySelector('.solo-questions'),style=getComputedStyle(panel);
            return {focus:s.focus,reveal:+document.body.style.getPropertyValue('--stadium-reveal'),opacity:+style.opacity,mask:style.maskImage,inert:panel.inert,progress:s.progress};
        });
        assert.equal(transition.reveal,transition.focus);
        assert(Math.abs(transition.opacity-transition.focus)<.00001);
        assert.equal(transition.inert,true);assert.equal(transition.progress,1);
        assert.match(transition.mask,/linear-gradient/);
        results.push(await screenshot(page,'synchronized-panel-reveal'));
        await page.waitForFunction(()=>PointsStadium.inspect().phase==='ready'&&!PointsStadium.inspect().entering,{},{timeout:15000});
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().role),'shooter');
        assert.deepEqual(await page.evaluate(()=>{
            const s=PointsStadium.inspect();return [s.reference,s.focus,s.environmentVisible,s.panels];
        }),['v6',1,false,{pentagons:12,hexagons:20}]);
        results.push(await screenshot(page,'solo-desktop'));
        assert.equal(await page.locator('#stadium-exit,#stadium-return,.penalty-stage,svg.pitch').count(),0);
        assert.equal(await page.locator('.solo-questions').evaluate(el=>el.inert),false);
        assert((await page.locator('.solo-questions').boundingBox()).width>=550,'Desktop panel must be larger');
        for(const size of [{width:1024,height:768},{width:844,height:390},{width:320,height:740}]) {
            await page.setViewportSize(size);await page.waitForTimeout(100);
            results.push(await screenshot(page,`solo-${size.width}x${size.height}`));
            const panel=await page.locator('.solo-questions').boundingBox();
            assert(panel.x>=0&&panel.x+panel.width<=size.width+1&&panel.y+panel.height<=size.height+1);
        }
        await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);
        results.push(await screenshot(page,'solo-mobile'));
        // Next is still the only command that opens the timed question.
        await page.locator('#next').click();await page.locator('#choices button:not([disabled])').first().waitFor();
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().entering),false);
        const deadline=(await(await soloContext.request.get(base+'/api/solo/runs/'+soloRun)).json()).deadline;
        await page.reload();await page.locator('#choices button:not([disabled])').first().waitFor();
        await page.waitForFunction(()=>PointsStadium.inspect().active);
        assert.equal(await page.evaluate(()=>PointsStadium.inspect().entering),false);
        assert.equal((await(await soloContext.request.get(base+'/api/solo/runs/'+soloRun)).json()).deadline,deadline);
        results.push(await screenshot(page,'solo-question-mobile'));
        await page.locator('#choices button').first().click();
        await page.locator('#stadium-outcome:not([hidden])').waitFor();
        const ballBefore=await page.evaluate(()=>PointsStadium.inspect().ball);
        await page.waitForTimeout(400);
        assert.notDeepEqual(await page.evaluate(()=>PointsStadium.inspect().ball),ballBefore,'Ball must animate a server-resolved result');
        await page.waitForTimeout(900);
        await page.locator('#leave').click();
        await page.locator('#summary:not([hidden])').waitFor();
        assert.equal(await page.locator('#question-panel').isVisible(),false);
        assert.equal(await page.locator('#stadium-layer').isVisible(),false);
        assert.match(await page.locator('#result-metrics').innerText(),/\/ 10/);
        assert.match(await page.locator('#result-completion').innerText(),/9 unplayed/);
        assert.equal(await page.locator('#result-level').isVisible(),false,'Trial cannot claim saved level progress');
        for(const size of [{width:390,height:844},{width:1440,height:1000}]) {
            await page.setViewportSize(size);
            await page.screenshot({path:path.join(out,`summary-${size.width}.png`)});
            assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
        }
        soloRun=null;
        await soloContext.close();

        host=await context();guest=await context();const a=await host.newPage(),b=await guest.newPage();
        await a.goto(base+'/penalties/pvp');await a.locator('#create-game:not([disabled])').waitFor();
        await a.locator('#player-name').fill('Stadium QA A');
        const created=a.waitForResponse(r=>r.url().endsWith('/api/penalties/rooms')&&r.request().method()==='POST');
        await a.locator('#create-game').click();room=(await(await created).json()).code;
        await a.locator('#ready-game').waitFor({state:'visible'});
        await b.goto(base+'/penalties/pvp');await b.locator('#player-name').fill('Stadium QA B');
        await b.locator('#room-code').fill(room);await b.locator('#join-form button').click();
        await b.locator('#ready-game').waitFor({state:'visible'});
        const lobby=await(await host.request.get(base+'/api/penalties/rooms/'+room)).json();
        const roleA=lobby.initial_shooter===lobby.me?'shooter':'keeper',roleB=roleA==='shooter'?'keeper':'shooter';
        await a.locator('#ready-game').click();await b.locator('#ready-game').click();
        await a.waitForFunction(()=>PointsStadium.inspect().entering);
        await b.waitForFunction(()=>PointsStadium.inspect().entering);
        const waiting=await(await host.request.get(base+'/api/penalties/rooms/'+room)).json();
        assert.equal(waiting.phase,'LOBBY');assert.equal(waiting.question,null);
        await a.waitForFunction(()=>PointsStadium.inspect().phase==='ready'&&!PointsStadium.inspect().entering,{},{timeout:15000});
        await b.waitForFunction(()=>PointsStadium.inspect().phase==='ready'&&!PointsStadium.inspect().entering,{},{timeout:15000});
        assert.equal(await a.evaluate(()=>PointsStadium.inspect().role),roleA);
        assert.equal(await b.evaluate(()=>PointsStadium.inspect().role),roleB);
        results.push(await screenshot(a,'pvp-'+roleA+'-desktop'));
        results.push(await screenshot(b,'pvp-'+roleB+'-desktop'));
        const keeper=roleA==='keeper'?a:b;await keeper.setViewportSize({width:390,height:844});await keeper.waitForTimeout(150);
        results.push(await screenshot(keeper,'pvp-keeper-mobile'));
        await a.locator('#answers button:not([disabled])').first().waitFor();
        await b.locator('#answers button:not([disabled])').first().waitFor();
        assert.match(await a.locator('#stadium-score').innerText(),/\d+ : \d+/);
        await a.waitForFunction(()=>document.getElementById('stadium-clock').textContent.endsWith(' s'));
        results.push(await screenshot(roleA==='keeper'?b:a,'pvp-question-desktop'));
        results.push(await screenshot(keeper,'pvp-question-mobile'));
        await a.locator('#answers button').first().click();await b.waitForTimeout(250);await b.locator('#answers button').first().click();
        await a.locator('#stadium-outcome:not([hidden])').waitFor();
        const result=await(await host.request.get(base+'/api/penalties/rooms/'+room)).json();
        if(result.round.outcome!=='replay') {
            await a.waitForFunction(old=>PointsStadium.inspect().role!==old,roleA,{timeout:10000});
            await b.waitForFunction(old=>PointsStadium.inspect().role!==old,roleB,{timeout:10000});
        }
        await host.request.post(base+'/api/penalties/rooms/'+room+'/leave',{data:{}});room=null;

        // Separate read-only presentation checks do not consume another trial.
        const reduced=await context({reducedMotion:'reduce',viewport:{width:390,height:844}}),r=await reduced.newPage();
        await r.goto(base+'/penalties');await r.waitForFunction(()=>!!window.PointsStadium);
        await r.evaluate(()=>PointsStadium.enter('keeper',{intro:true}));
        assert.equal(await r.evaluate(()=>PointsStadium.inspect().entering),false);
        assert.equal(await r.evaluate(()=>PointsStadium.inspect().progress),1);
        assert.equal(await r.evaluate(()=>+document.body.style.getPropertyValue('--stadium-reveal')),1);
        // Every target/outcome is checked at its final physical location.
        await r.evaluate(()=>PointsStadium.enter('shooter',{maxDurationMs:0}));
        for(const outcome of ['goal','save'])for(const zone of ['low-left','low-center','low-right','high-left','high-center','high-right']) {
            const state=await r.evaluate(({outcome,zone})=>{
                const target=PenaltyShots.zones.find(z=>z.id===zone);
                const keeper=outcome==='save'?target:PenaltyShots.zones.find(z=>target.side?z.side===-target.side:z.side!==0);
                PointsStadium.shot(outcome,{outcome,target,keeper});return PointsStadium.inspect();
            },{outcome,zone});
            assert.equal(state.caught,outcome==='save');
            if(state.lastPlan.target.side===0)assert(Math.abs(state.ball[2])<.001);
            else assert.equal(Math.sign(state.ball[2]),state.lastPlan.target.side);
            if(outcome==='goal')assert(Math.abs(state.ball[1]-.195)<.001,'Goal settles on the turf');
            else assert(state.ball[1]>=.195&&state.ball[1]<1.1,'Keeper lands with the held ball');
            assert(outcome==='save'?state.ball[0]<52.5:state.ball[0]>52.5);
            if(outcome==='save')assert(Math.hypot(...state.ball.map((n,i)=>n-state.hands[i]))<.001,'Saved ball must be held between both hands');
            results.push(await screenshot(r,`${outcome}-${zone}-mobile`));
        }
        // A lost graphics context cannot trap the player behind the 3D layer.
        const lost=await r.evaluate(()=>{
            const ext=document.querySelector('#stadium-layer canvas').getContext('webgl2').getExtension('WEBGL_lose_context');
            if(ext)ext.loseContext();return !!ext;
        });
        if(lost){await r.waitForFunction(()=>!PointsStadium.inspect().active);assert.equal(await r.locator('#stadium-layer').isHidden(),true);}
        else await r.evaluate(()=>PointsStadium.leave());
        assert.equal(await r.locator('#stadium-layer').isHidden(),true);
        const failure=await context();await failure.route('**/trivia-assets/vendor/three/**',route=>route.abort());
        const f=await failure.newPage();await f.goto(base+'/penalties');await f.waitForFunction(()=>!!window.PointsStadium);
        assert.equal(await f.evaluate(()=>PointsStadium.enter('shooter',{intro:true})),false);
        assert.equal(await f.locator('#stadium-layer').isHidden(),true);
        assert.equal(await f.locator('#stadium-unavailable').isVisible(),true);
        assert.equal(await f.locator('.penalty-stage,svg.pitch,#stadium-return,#stadium-exit').count(),0);
        assert.equal(await f.locator('.solo-questions').evaluate(el=>el.inert),false);
        const skipping=await context(),skipPage=await skipping.newPage();
        await skipPage.goto(base+'/penalties');await skipPage.waitForFunction(()=>!!window.PointsStadium);
        await skipPage.evaluate(()=>{void PointsStadium.enter('shooter',{intro:true});});
        await skipPage.waitForFunction(()=>PointsStadium.inspect().entering);
        await skipPage.keyboard.press('Escape');
        assert.deepEqual(await skipPage.evaluate(()=>[PointsStadium.inspect().focus,+document.body.style.getPropertyValue('--stadium-reveal'),document.querySelector('.solo-questions').inert]),[1,1,false]);
        // Real RAF frames: keeper rises and falls; a caught ball follows hands
        // throughout descent, not just in the final reduced-motion pose.
        for(const outcome of ['goal','save']) {
            await skipPage.evaluate(outcome=>{
                const target=PenaltyShots.zones.find(z=>z.id==='high-right');
                const keeper=PenaltyShots.zones.find(z=>z.id===(outcome==='save'?'high-right':'high-left'));
                PointsStadium.shot(outcome,{outcome,target,keeper});
            },outcome);
            const samples=[];
            for(let i=0;i<28;i++) {
                await skipPage.waitForTimeout(85);
                const state=await skipPage.evaluate(()=>PointsStadium.inspect());samples.push(state);
                if(state.caught)assert(Math.hypot(...state.ball.map((n,j)=>n-state.hands[j]))<.001);
                assert(state.ball[1]>=.194);
                if(i===5)results.push(await screenshot(skipPage,`${outcome}-airborne`));
            }
            const final=samples.at(-1),apex=Math.max(...samples.map(s=>s.keeper[1]));
            assert(apex>1.4&&final.keeper[1]<.8,'High dive must land after the apex');
            assert.equal(final.phase,'ready');
            if(outcome==='goal')assert(Math.abs(final.ball[1]-.195)<.001);
            results.push(await screenshot(skipPage,`${outcome}-landed`));
        }
        // Read-only account-result fixture: the real XP transaction is covered
        // by test_solo_database; this checks its desktop/mobile presentation.
        const accountResult=await context(),summaryPage=await accountResult.newPage();
        const progress={level:3,total_xp:920,level_xp:750,next_level_xp:1500};
        await accountResult.route('**/api/players/me',route=>route.fulfill({json:{username:'Summary preview',...progress}}));
        await accountResult.route('**/api/solo/active',route=>route.fulfill({json:{run:{...data,
            server_now:Date.now(),phase:'ABANDONED',position:2,is_trial:false,xp_saved:true,correct:2,
            total_xp:20,base_xp:20,bonus_xp:0,multiplier:1,player_progress:progress,
            review:[1,2].map(position=>({position,option_id:'0',correct:'0',is_correct:true,text:'Preview question',explanation:'Preview answer'})),
        }}}));
        await summaryPage.goto(base+'/penalties');await summaryPage.locator('#result-level:not([hidden])').waitFor();
        assert.equal(await summaryPage.locator('#result-level-remaining').innerText(),'580 XP to level 4');
        assert.equal(await summaryPage.locator('#question-panel').isVisible(),false);
        for(const width of [1440,320]) {
            await summaryPage.setViewportSize({width,height:900});
            await summaryPage.screenshot({path:path.join(out,`account-summary-${width}.png`)});
            assert.equal(await summaryPage.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
            const heading=await summaryPage.locator('.solo-heading h1').boundingBox(),actions=await summaryPage.locator('.solo-heading .actions').boundingBox();
            assert(heading.y+heading.height<=actions.y||heading.x+heading.width<=actions.x,'Summary header cannot overlap account controls');
        }
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({results,roles:{host:roleA,guest:roleB},errors,output:out}));
    } finally {
        if(soloRun&&soloContext)await soloContext.request.post(base+'/api/solo/runs/'+soloRun+'/leave',{data:{}}).catch(()=>{});
        if(room&&host)await host.request.post(base+'/api/penalties/rooms/'+room+'/leave',{data:{}}).catch(()=>{});
        for(const c of contexts)await c.close().catch(()=>{});
        await browser.close();
    }
})().catch(e=>{console.error(e);process.exitCode=1;});
