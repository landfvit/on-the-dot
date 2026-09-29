/* Exercise the public 3D bridge on real pages. Game APIs are stubbed; no writes. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const rules={format:'shootout',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
async function setup(browser,width=390){
    const page=await browser.newPage({viewport:{width,height:844}}),errors=[],writes=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',async route=>{
        const request=route.request(),path=new URL(request.url()).pathname;
        if(request.method()!=='GET')writes.push(path);
        if(path==='/api/players/me')return route.fulfill({status:401,json:{detail:'Sign in'}});
        if(path==='/api/solo/catalog')return route.fulfill({json:{categories:[],topics:[{code:'ALL',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules}});
        if(path==='/api/solo/active')return route.fulfill({json:{run:null,trial_available:true}});
        return route.fulfill({status:404,json:{detail:'Unexpected test request'}});
    });
    return {page,errors,writes};
}
async function enter(page){
    await page.waitForFunction(()=>!!window.PointsStadium);
    return page.evaluate(()=>PointsStadium.enter('shooter',{intro:false,maxDurationMs:0}));
}
(async()=>{
    const browser=process.env.TEST_BROWSER==='webkit'?await webkit.launch({headless:true}):await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
    try{
        {
            const {page,errors,writes}=await setup(browser);
            await page.addInitScript(()=>{
                const get=HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext=function(type,options){
                    if(type==='webgl2'&&options?.antialias)return null;
                    return get.call(this,type,options);
                };
            });
            await page.goto(origin+'/penalties');assert(await enter(page),'A context without MSAA must still load 3D');
            assert.equal(await page.locator('#stadium-layer canvas').count(),1);
            const pixels=await sharp(await page.locator('#stadium-layer canvas').screenshot()).stats();
            assert(pixels.channels.some(c=>c.stdev>10));
            assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);await page.close();
            console.log('PASS non-multisampled WebGL fallback');
        }
        {
            const {page,errors,writes}=await setup(browser);await page.goto(origin+'/penalties');assert(await enter(page));
            // A draw error happens on a later RAF, outside enter()'s try/catch.
            const result=await page.evaluate(async()=>{
                const proto=WebGL2RenderingContext.prototype,draw=proto.drawElements;
                let armed=false;
                proto.drawElements=function(...args){
                    if(armed){proto.drawElements=draw;throw Error('Test frame failure');}
                    return draw.apply(this,args);
                };
                const task=PointsStadium.shot('goal',PenaltyShots.plan('goal','frame-failure'));
                armed=true;
                return Promise.race([task.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),1200))]);
            });
            assert(result,'An asynchronous render error must release the pending shot, not freeze Next');
            assert.equal(await page.evaluate(()=>PointsStadium.inspect().lastError),'Test frame failure');
            await page.getByRole('button',{name:'Retry 3D',exact:true}).click();
            await page.waitForFunction(()=>PointsStadium.inspect().active&&PointsStadium.inspect().phase==='ready');
            assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);await page.close();
            console.log('PASS frame failure releases animation and allows recovery');
        }
        {
            const {page,errors,writes}=await setup(browser);await page.goto(origin+'/penalties');assert(await enter(page));
            await page.evaluate(async()=>{
                await PointsStadium.enter('keeper',{maxDurationMs:0});
                PointsAudio.play=()=>{window.cues=(window.cues||0)+1;};
                await PointsStadium.shot('save',PenaltyShots.plan('save','page-cache'));
                window.beforeCues=window.cues;
                dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
                dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
            });
            await page.waitForFunction(()=>PointsStadium.inspect().active&&PointsStadium.inspect().caught,{},{timeout:3000});
            const state=await page.evaluate(()=>({view:PointsStadium.inspect(),cues:window.cues,before:window.beforeCues}));
            assert.equal(state.view.role,'keeper');assert.equal(state.cues,state.before);
            assert.equal(await page.locator('#stadium-layer canvas').count(),1);
            assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);await page.close();
            console.log('PASS cached-page return restores current view and result silently');
        }
        {
            const {page,errors,writes}=await setup(browser);let requests=0;
            await page.route('**/stadium_scene.js?*',route=>++requests===1?route.abort():route.continue());
            const failed=page.waitForEvent('requestfailed',r=>r.url().includes('stadium_scene.js'));
            await page.goto(origin+'/penalties');await failed;
            // Wait for the preload rejection before attempting an actual game view.
            await page.evaluate(()=>PointsStadium.prepare());
            assert(await enter(page),'A failed preload must not permanently disable 3D');
            assert(requests>=2);assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
            await page.close();console.log('PASS failed preload recovers without reloading the page');
        }
        for(const asset of ['stadium_v6_world.js','stadium_config.js','stadium_motion.js','crowd_reaction.js','vendor/three/three.core.min.js']){
            const {page,errors,writes}=await setup(browser);let failedOnce=false,retried=false;
            await page.route('**/trivia-assets/**',route=>{
                const url=new URL(route.request().url());
                if(!url.pathname.endsWith('/'+asset))return route.continue();
                if(!failedOnce){failedOnce=true;return route.abort();}
                retried||=url.pathname.includes('/_retry/');return route.continue();
            });
            await page.goto(origin+'/penalties');await page.evaluate(()=>PointsStadium.prepare());
            assert(await enter(page),`Failed dependency ${asset} must not poison all future imports`);
            assert(failedOnce&&retried,'Retry must use a fresh namespace for dependencies, too');
            assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);await page.close();
            console.log('PASS dependency recovery: '+asset);
        }
        {
            const {page,errors,writes}=await setup(browser,1440);
            await page.route('**/stadium_scene.js?*',async route=>{await new Promise(resolve=>setTimeout(resolve,4200));await route.continue();});
            await page.goto(origin+'/penalties');
            assert(await enter(page),'A cold module load longer than 3.5 seconds is not a WebGL failure');
            assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
            await page.close();console.log('PASS slow cold load');
        }
        for(const width of [390,1440]){
            const {page,errors,writes}=await setup(browser,width);await page.goto(origin+'/penalties');assert(await enter(page));
            await page.evaluate(async()=>{
                await PointsStadium.enter('keeper',{intro:false,maxDurationMs:0});
                PointsAudio.play=()=>{window.cues=(window.cues||0)+1;};
                await PointsStadium.shot('save',PenaltyShots.plan('save','recovery-test'));
            });
            const before=await page.evaluate(()=>({cues:window.cues,state:PointsStadium.inspect()}));
            await page.locator('#stadium-layer canvas').evaluate(canvas=>canvas.dispatchEvent(new Event('webglcontextlost',{cancelable:true})));
            await page.locator('#stadium-unavailable:not([hidden])').waitFor();
            assert.equal(await page.locator('#stadium-layer canvas').count(),0,'Failed renderer must be disposed');
            assert.equal(await page.evaluate(()=>PointsStadium.inspect().lastError),'WebGL context lost');
            const retry=page.getByRole('button',{name:'Retry 3D',exact:true});
            assert((await retry.boundingBox()).height>=44,'Recovery must have a touch-sized control');
            await retry.click();
            await page.waitForFunction(()=>PointsStadium.inspect().active&&!PointsStadium.inspect().entering&&PointsStadium.inspect().caught);
            const after=await page.evaluate(()=>({cues:window.cues,state:PointsStadium.inspect()}));
            assert.equal(after.state.role,'keeper');assert.equal(after.state.lastError,null);
            assert.equal(after.cues,before.cues,'Recovery must not replay kick/save sounds');
            assert(after.state.ball.every((value,i)=>Math.abs(value-after.state.hands[i])<.001));
            assert.equal(await page.locator('#stadium-layer canvas').count(),1);
            const pixels=await sharp(await page.locator('#stadium-layer canvas').screenshot()).stats();
            assert(pixels.channels.some(c=>c.stdev>10),'Restored stadium must not be blank');
            await page.evaluate(()=>PointsStadium.leave());
            assert.equal(await page.evaluate(()=>PointsStadium.retry()),false,'Leaving the game must cancel recovery');
            assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
            await page.close();console.log(`PASS WebGL recovery ${width}: camera, catch, audio and nonblank canvas`);
        }
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
