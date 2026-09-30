/* Local UI only: scripted API responses never consume a real game or account. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const question={text:'Which team plays at Old Trafford?',options:[{id:'a',text:'Manchester United'},{id:'b',text:'Arsenal'},{id:'c',text:'Chelsea'},{id:'d',text:'Everton'}]};
const rect=locator=>locator.evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};});
(async()=>{
  const engine=process.env.TEST_BROWSER||'chrome';
  const browser=engine==='webkit'?await webkit.launch({headless:true}):await chromium.launch({channel:'chrome',headless:true});
  try{
    for(const [mode,outcome] of [['solo','correct'],['daily','wrong'],['solo','timeout'],['daily','resume']]){
      const page=await browser.newPage({viewport:mode==='daily'?{width:390,height:700}:{width:1440,height:900}});
      const base=`/api/${mode}`,errors=[];
      let nextRequests=0,answerRequests=0,failRefresh=false,pendingNext=null,releaseNext;
      let run={run_id:'next-target-test',phase:'ANSWERING',position:1,role:'shooter',question,review:[],rules,deadline:Date.now()+60000,
        difficulty:'easy',category:{label:'Mixed topics'},is_trial:false,total_xp:0,correct:0,base_xp:0,bonus_xp:0,multiplier:1,
        ...(mode==='daily'?{survival:{ranked:true,goals:0,mistakes:0,lives:3,max_lives:3,next_role:'shooter',attempts:[]}}:
          {shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},round:1,next_role:'shooter',attempts:[]}})};
      function review(option){
        const correct=option==='a';
        run={...run,phase:'REVIEW',deadline:null,review:[{position:1,option_id:option,correct:'a',is_correct:correct,outcome:correct?'goal':'save',text:question.text,options:question.options}]};
        if(run.shootout)run.shootout={...run.shootout,next_role:'keeper'};
      }
      if(outcome==='resume')review('a');
      page.on('pageerror',e=>errors.push(e.message));
      await page.route('**/api/**',async route=>{
        const req=route.request(),path=new URL(req.url()).pathname;let data;
        if(path==='/api/players/me')data={username:'NextTester',preferences:{animations:false}};
        else if(path===base+'/catalog')data=mode==='daily'?{remaining:1000,ranked_available:true,rules}:{topics:[{code:'ALL',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
        else if(path===base+'/active')data={run:{...run,server_now:Date.now()}};
        else if(path===base+'/runs/next-target-test/answers'){
          answerRequests++;review(req.postDataJSON().option_id);data=run;
        }else if(path===base+'/runs/next-target-test/next'){
          nextRequests++;
          assert.equal(req.postDataJSON().previous,1);
          pendingNext=new Promise(resolve=>{releaseNext=resolve;});
          await pendingNext;
          if(nextRequests===1){failRefresh=true;return route.fulfill({status:503,json:{detail:'Try reconnecting'}});}
          run={...run,phase:'ANSWERING',position:2,deadline:Date.now()+60000};data=run;
        }else if(path===base+'/runs/next-target-test'){
          if(failRefresh)return route.fulfill({status:503,json:{detail:'Try reconnecting'}});
          data=run;
        }else throw Error('Unexpected mocked API '+path);
        await route.fulfill({json:data===run?{...data,server_now:Date.now()}:data});
      });
      try{
        await page.goto(origin+(mode==='daily'?'/daily':'/penalties'));
        await page.locator('#quiz-run:not([hidden])').waitFor();
        const original=await rect(page.locator('#answer-slot'));
        if(outcome==='timeout'){
          review(null); // The next poll delivers the authoritative timeout.
        }else if(outcome!=='resume'){
          const answer=page.locator('#choices button').nth(outcome==='correct'?0:1);
          await answer.focus();await answer.press('Enter');
        }
        if(outcome!=='resume'){
          await page.locator('#choices button.correct').waitFor();
          assert(!await page.locator('#next').isVisible(),'Even without motion, feedback is readable before Continue');
          if(outcome==='wrong')assert(await page.locator('#choices button.incorrect').isVisible());
        }
        const next=page.getByRole('button',{name:'Next penalty',exact:true});
        await next.waitFor();
        assert.equal(await next.count(),1);
        assert.deepEqual(await rect(next),original);
        assert.equal(await page.locator('#choices').evaluate(e=>e.inert),true);
        assert.equal(await page.getByRole('button',{name:'Manchester United, correct answer',exact:true}).count(),0);
        assert(await next.evaluate(e=>e===document.activeElement),'Keyboard focus follows the replacement');
        assert.equal(await next.evaluate(e=>e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',repeat:true,cancelable:true,bubbles:true}))),false);
        assert.equal(nextRequests,0,'Holding Enter must not advance');
        // Reuse a former answer's click position. Pending requests must retain
        // the large target and ignore repeated clicks, even after a failure.
        const x=original.x+original.width*.75,y=original.y+original.height*.75;
        await page.mouse.dblclick(x,y,{delay:40});
        await page.waitForFunction(()=>document.querySelector('#next').disabled);
        assert.equal(nextRequests,1);assert.deepEqual(await rect(next),original);
        releaseNext();
        await page.locator('#retry:not([hidden])').waitFor();
        assert(await next.isVisible());assert.deepEqual(await rect(next),original);
        failRefresh=false;await page.locator('#retry').click();
        await page.locator('#retry').waitFor({state:'hidden'});
        await next.click();await page.waitForFunction(()=>document.querySelector('#next').disabled);
        assert.equal(nextRequests,2);releaseNext();
        await page.locator('#choices button:enabled').first().waitFor();
        assert(!await next.isVisible());assert.deepEqual(await rect(page.locator('#choices')),original);
        assert.equal(await page.locator('#choices').evaluate(e=>e.inert),false);
        assert.equal(answerRequests,['timeout','resume'].includes(outcome)?0:1);
        assert.deepEqual(errors,[]);
        console.log(`PASS ${engine} ${mode} ${outcome}: same target, feedback, keyboard, double click, reconnect`);
      }finally{releaseNext?.();await page.close();}
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
