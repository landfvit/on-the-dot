/* Real Daily UI + WebGL; mocked account/game API, never consumes a real attempt. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/tmp/on-the-dot-daily-ready';
assert(['127.0.0.1','localhost'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
const rules={format:'daily_survival',version:'daily-survival-v2',lives:3,ranked:true,questions:1000,answer_ms:15000,bonus_mode:'none',xp_by_difficulty:{easy:10,medium:20,hard:30}};
const question={text:'Which team plays at Old Trafford?',options:[{id:'a',text:'Manchester United'},{id:'b',text:'Arsenal'}]};
function fresh(ranked=true){return {run_id:'daily-ready-test',phase:'READY',position:0,role:'shooter',question:null,review:[],rules,deadline:null,
    difficulty:'mixed',category:{label:'Daily Challenge'},is_trial:false,total_xp:0,correct:0,base_xp:0,bonus_xp:0,multiplier:1,highscore:0,
    survival:{ranked,goals:0,mistakes:0,lives:3,max_lives:3,next_role:'shooter',attempts:[]}};}
(async()=>{
    const engine=process.env.TEST_BROWSER||'chrome';
    const browser=engine==='webkit'?await webkit.launch({headless:true}):await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
    const cases=[['stalled',390,700],['full',390,700],['full',1440,900],['skip',320,568],['reduced',390,664],['motion-off',844,390],['load-failure',390,700],['context-loss',390,700],['resume',390,700],['forfeit',390,700],['practice',390,700]];
    try{
        for(const [mode,width,height] of cases.filter(([m])=>!process.env.CASE||process.env.CASE===m)){
            let run=mode==='resume'?fresh():null;const writes=[],errors=[];
            const page=await browser.newPage({viewport:{width,height},reducedMotion:mode==='reduced'?'reduce':'no-preference'});
            page.on('pageerror',e=>errors.push(e.message));
            // Reproduce the missing last RAF after the camera has reached the
            // spot. Only alter this test response, never the source on disk.
            if(mode==='stalled'){
                await page.route('**/stadium_scene.js?*',async route=>{
                    const r=await route.fetch(),source=await r.text();
                    assert(source.includes("if(elapsed>=duration){phase='ready';render();stop();}"));
                    await route.fulfill({response:r,body:source.replace("if(elapsed>=duration){phase='ready';render();stop();}","if(t===1){focus(0);return;} if(elapsed>=duration){phase='ready';render();stop();}")});
                });
            }
            // Keep one normal-speed intro per viewport. Other lifecycle cases
            // use the real renderer with a shorter intro to keep the suite fast.
            if(!['full','skip','context-loss'].includes(mode))await page.route('**/stadium_config.js?*',async route=>{
                const r=await route.fetch();await route.fulfill({response:r,body:(await r.text())+'\nSTADIUM.introMs=600;STADIUM.focusMs=120;STADIUM.outroMs=500;'});
            });
            if(mode==='load-failure')await page.route('**/stadium_scene.js?*',route=>route.abort());
            await page.route('**/api/**',async route=>{
                const req=route.request(),path=new URL(req.url()).pathname;let data;
                if(req.method()!=='GET')writes.push(path);
                if(path==='/api/players/me')data={username:'DailyTester',preferences:{animations:mode!=='motion-off',reduced_motion:false}};
                else if(path==='/api/daily/catalog')data={remaining:1000,ranked_available:mode!=='practice',rules,resets_at:new Date(Date.now()+86400000).toISOString()};
                else if(path==='/api/daily/active')data={run:run?{...run,server_now:Date.now()}:null};
                else if(path==='/api/daily/runs'){run=fresh(mode!=='practice');data=run;}
                else if(path==='/api/daily/runs/daily-ready-test/next'){
                    assert.equal(req.postDataJSON().previous,0);
                    assert.equal(run.phase,'READY');run={...run,phase:'ANSWERING',position:1,question,deadline:Date.now()+15000};data=run;
                }else if(path==='/api/daily/runs/daily-ready-test/leave'){
                    run={...run,phase:'ABANDONED',end_reason:'forfeit'};data=run;
                }else if(path==='/api/daily/runs/daily-ready-test')data=run;
                else throw Error('Unexpected mocked API '+path);
                await route.fulfill({json:data===run?{...data,server_now:Date.now()}:data});
            });
            try{
                await page.goto(origin+'/daily');
                if(mode!=='resume'){
                    await page.locator('#start:enabled').click();
                    await page.locator('#mode-intro button[value=play]').click();
                }
                await page.locator('#quiz-run:not([hidden])').waitFor();
                if(['skip','context-loss'].includes(mode)){
                    await page.waitForFunction(()=>PointsStadium.inspect().entering);
                    if(mode==='skip'){
                        assert(await page.locator('#stadium-skip').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;}),'Skip intro must fit in the mobile header');
                        await page.locator('#stadium-skip').click();
                    }
                    else await page.locator('#stadium-layer canvas').evaluate(e=>e.dispatchEvent(new Event('webglcontextlost',{cancelable:true})));
                }
                await page.locator('#next:not([hidden]):enabled').waitFor({timeout:mode==='full'?18000:5000});
                await page.waitForFunction(()=>!document.querySelector('.solo-questions').inert&&!document.body.classList.contains('stadium-entering'));
                assert.equal(run.phase,'READY');assert.equal(run.deadline,null);assert.equal(run.survival.lives,3);
                assert(!writes.some(path=>path.endsWith('/next')),'Intro/recovery must never start the answer clock');
                const ready=page.getByRole('button',{name:'Take first shot',exact:true});
                assert(await ready.isVisible());assert(await page.locator('#leave').isVisible());
                const panel=await page.locator('.solo-questions').evaluate(e=>({opacity:Number(getComputedStyle(e).opacity),mask:getComputedStyle(e).maskImage}));
                assert.equal(panel.opacity,1,'Ready must not stay transparent after the intro');
                for(const control of [ready,page.locator('#leave')])assert(await control.evaluate(e=>{
                    const r=e.getBoundingClientRect();return r.top>=0&&r.left>=0&&r.bottom<=innerHeight&&r.right<=innerWidth;
                }),'Ready and Forfeit must be on screen');
                if(!['load-failure','context-loss'].includes(mode)){
                    const pixels=await sharp(await page.locator('#stadium-layer canvas').screenshot()).stats();
                    assert(pixels.channels.some(c=>c.stdev>10));
                }
                await page.screenshot({path:`${out}/${engine}-${mode}-${width}-ready.png`});
                if(mode==='forfeit'){
                    await page.locator('#leave').click();await page.locator('#summary:not([hidden])').waitFor();
                    assert.equal(run.phase,'ABANDONED');assert.equal(run.position,0);
                    assert(await page.locator('#summary a[href="/"]').isVisible());
                }else{
                    await ready.click();await page.locator('#choices button:enabled').first().waitFor();
                    assert.equal(writes.filter(path=>path.endsWith('/next')).length,1);
                    assert.equal(run.phase,'ANSWERING');assert(run.deadline>Date.now()+10000);
                    assert.equal(run.survival.lives,3);
                }
                assert.deepEqual(errors,[]);console.log(`PASS ${engine} Daily ${mode} ${width}: Ready, exit and clock`);
            }catch(e){await page.screenshot({path:`${out}/${engine}-${mode}-${width}-failure.png`}).catch(()=>{});throw e;}
            finally{await page.close();}
        }
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
