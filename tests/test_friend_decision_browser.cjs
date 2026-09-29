/* Two isolated viewers, mocked game APIs. No account, room or score DB writes. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/tmp/on-the-dot-friend-decision';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
const question={text:'Who was Manchester United\'s top Premier League scorer in 2017/18?',options:[{id:'a',text:'Romelu Lukaku'},{id:'b',text:'Marcus Rashford'},{id:'c',text:'Anthony Martial'},{id:'d',text:'Paul Pogba'}]};
function fresh(){return {run_id:'test-duel',phase:'ANSWERING',version:1,initial_shooter:0,code:'test-duel',rules:{tie_ms:150,answer_ms:15000},
    players:[{name:'Alex',ready:true,is_guest:false},{name:'Sam',ready:true,is_guest:false}],score:[0,0],attempts:[0,0],history:[],winner:null,reason:null,
    stats:[{correct:0},{correct:0}],round:{id:1,shooter:0,pair:1,slot:0,opens_at:Date.now()-1000,deadline:Date.now()+60000},question};}
(async()=>{
    const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
    try{
        for(const [width,height] of [[320,568],[390,700],[844,390],[1440,900]]){
            let state=fresh(),submitted=[false,false];const pages=[],errors=[];
            for(const me of [0,1]){
                const page=await browser.newPage({viewport:{width,height}});pages.push(page);
                page.on('pageerror',e=>errors.push(e.message));
                await page.route('**/api/**',route=>{
                    const req=route.request(),url=new URL(req.url()).pathname;
                    if(url==='/api/players/me')return route.fulfill({json:{username:state.players[me].name}});
                    if(url.startsWith('/api/friends/invites/'))return route.fulfill({json:{member:true}});
                    if(url==='/api/friends/rooms/test-duel/answers'){
                        submitted[me]=true;state.version++;
                    }else assert.equal(req.method(),'GET','No real writes in presentation test');
                    if(url.startsWith('/api/friends/rooms/test-duel'))return route.fulfill({json:{...state,me,server_now:Date.now(),round:{...state.round,own_option:submitted[me]?'a':null}}});
                    return route.fulfill({status:404,json:{detail:'Unexpected mocked request'}});
                });
                await page.goto(origin+'/friends/test-duel');
                await page.waitForFunction(()=>PointsStadium.inspect().active&&!PointsStadium.inspect().entering);
            }
            const answerBefore=await pages[0].locator('#choices').boundingBox();
            await pages[0].getByRole('button',{name:'Romelu Lukaku',exact:true}).click();
            await pages[0].getByText('Answer locked. Waiting for Sam...',{exact:true}).waitFor();
            assert(!await pages[0].locator('#friend-round-result').isVisible());
            assert(!await pages[1].locator('#friend-round-result').isVisible());
            submitted=[true,true];state={...state,phase:'RESOLVED',version:3,score:[1,0],attempts:[1,0],history:[{shooter:0,outcome:'goal'}],
                question:{...question,correct:'a'},round:{...state.round,outcome:'goal',next_at:Date.now()+60000,
                    answers:[{option_id:'a',correct:true,elapsed_ms:2200},{option_id:'a',correct:true,elapsed_ms:3000}]}};
            for(const [me,page] of pages.entries()){
                await page.locator('#friend-round-result:not([hidden])').waitFor();
                assert.equal(await page.locator('#friend-round-result .friend-answer-name').first().textContent(),state.players[me].name);
                assert.equal(await page.locator('#friend-round-result .friend-answer-time').count(),2);
                assert.equal(await page.locator('#friend-round-result p').count(),0,'No explanatory caption');
                assert.equal(await page.locator('#friend-round-result .is-winner .friend-answer-time').textContent(),'2.20 s');
                if(me===0)assert.deepEqual(await page.locator('#choices').boundingBox(),answerBefore,'Result must not move the answer choices');
                // Wait for the shot and camera to settle, then verify the real canvas.
                await page.waitForFunction(role=>PointsStadium.inspect().role===role&&PointsStadium.inspect().phase==='ready',me===0?'keeper':'shooter');
                const pixels=await sharp(await page.locator('#stadium-layer canvas').screenshot()).stats();assert(pixels.channels.some(c=>c.stdev>10));
                for(const theme of ['light','dark']){
                    await page.evaluate(t=>{document.documentElement.dataset.theme=t;dispatchEvent(new CustomEvent('points-theme'));},theme);
                    assert(await page.locator('#friend-round-result').evaluate(e=>{
                        const r=e.getBoundingClientRect();return r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth&&e.scrollHeight<=e.clientHeight+1;
                    }),'Decision must fit without internal scrolling');
                    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
                    await page.screenshot({path:`${out}/${width}-seat-${me}-${theme}.png`});
                }
            }
            state={...state,phase:'COUNTDOWN',version:4,question:null,round:{id:2,shooter:1,pair:1,slot:1,opens_at:Date.now()+60000,deadline:Date.now()+75000}};submitted=[false,false];
            await pages[0].getByText('Get ready to save',{exact:true}).waitFor();
            assert(await pages[0].locator('#friend-round-result').isVisible(),'Keep the decision readable during countdown');
            state={...state,phase:'ANSWERING',version:5,question,round:{...state.round,opens_at:Date.now()}};
            await pages[0].locator('#friend-round-result').waitFor({state:'hidden'});
            await pages[1].locator('#friend-round-result').waitFor({state:'hidden'});
            // The final penalty must explain speed on the results screen, too.
            state={...state,phase:'FINISHED',version:6,winner:0,reason:'shootout_complete',question:{...question,correct:'a'},
                round:{...state.round,outcome:'save',next_at:Date.now(),answers:[{option_id:'a',correct:true,elapsed_ms:2200},{option_id:'a',correct:true,elapsed_ms:3000}]}};
            for(const page of pages){
                await page.locator('#summary:not([hidden])').waitFor();
                await page.waitForFunction(()=>!document.body.classList.contains('stadium-playing')||PointsStadium.inspect().phase==='finished');
                assert.equal(await page.locator('#friend-final-result .is-winner .friend-answer-time').textContent(),'2.20 s');
                assert.equal(await page.locator('#friend-final-result p').count(),0);
                assert(await page.locator('#friend-final-result .friend-answer').evaluateAll(rows=>rows.every(row=>row.scrollWidth<=row.clientWidth+1)),'Times must not overflow');
                assert(await page.locator('#summary').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight&&e.scrollHeight<=e.clientHeight+1),'Results must not scroll');
                await page.screenshot({path:`${out}/${width}-final.png`});await page.close();
            }
            assert.deepEqual(errors,[]);console.log(`PASS ${width}: both seats, privacy, timing, stable layout, countdown and final decision`);
        }
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
