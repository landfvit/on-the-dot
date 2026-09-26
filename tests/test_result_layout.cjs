/* Local-only layout regression. API mocks leave player records untouched.
 * Run with RESULT_TEST_URL=http://127.0.0.1:8013 and Playwright on NODE_PATH. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.RESULT_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-results';fs.mkdirSync(output,{recursive:true});
const rules={answer_ms:15000,xp_per_correct:10,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4},bonus_mode:'win',format:'shootout'};
const catalog={categories:[{code:'ALL',label:'All clubs',counts:{easy:100,medium:100,hard:100}}],topics:[{code:'ALL',label:'Mixed topics',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
let guest=true,variant='win',run;
function result(){
  const total=variant==='empty'?0:16;
  return {run_id:'result-layout',server_now:Date.now(),phase:['abandoned','empty'].includes(variant)?'ABANDONED':'FINISHED',position:total,
    category:{label:'All clubs'},difficulty:'easy',rules,role:'keeper',question:null,correct:9,total_xp:180,base_xp:90,bonus_xp:90,multiplier:2,is_trial:guest,
    end_reason:variant==='exhausted'?'question_pool_exhausted':null,
    player_progress:guest?null:{level:12,total_xp:24680,level_xp:24000,next_level_xp:25000},
    review:Array.from({length:total},(_,i)=>({position:i+1,option_id:i%3?'0':null,is_correct:Boolean(i%3),correct:'0',outcome:'goal',
      text:`${i+1}. What was the outcome of Brighton & Hove Albion's home Premier League meeting with Wolverhampton Wanderers in 2022/23: a Brighton & Hove Albion win, a draw, or a Wolverhampton Wanderers win?`,
      explanation:'Brighton & Hove Albion. Recorded result: Brighton & Hove Albion 6-0 Wolverhampton Wanderers, 2022/23 Premier League. Home club is written first.'})),
    shootout:{player:4,opponent:3,attempts:[],kicks:{player:8,opponent:8},round:8,winner:variant==='win'?'player':variant==='exhausted'?null:'opponent',sudden_death:true}};
}
async function check(page){
  const issues=await page.evaluate(()=>{
    const issues=[];
    const visible=e=>e.checkVisibility();
    const elements=[document.querySelector('.solo-questions'),...document.querySelectorAll('#summary, #summary h2, #summary p, #summary .metric, #summary button, #summary a')].filter(visible);
    for(const e of elements){
      const r=e.getBoundingClientRect(),name=e.id||e.className;
      if(r.top<-1||r.bottom>innerHeight+1||r.left<-1||r.right>innerWidth+1)issues.push([name,'outside viewport',{top:r.top,bottom:r.bottom,width:r.width},[innerWidth,innerHeight]]);
      if(e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1)issues.push([name,'overflows',[e.scrollWidth,e.scrollHeight],[e.clientWidth,e.clientHeight]]);
      if(e.matches('button,a')&&r.height<44)issues.push([name,'small tap target',r.height]);
    }
    const button=document.getElementById('share-result'),b=button.getBoundingClientRect();
    const icon=button.querySelector('img').getBoundingClientRect(),label=button.querySelector('span').getBoundingClientRect();
    if(Math.abs((icon.left+label.right)/2-(b.left+b.right)/2)>1)issues.push(['Share contents not centered']);
    const boxes=[...document.querySelectorAll('#summary button,#summary a')].filter(visible).map(e=>({id:e.id||e.textContent,r:e.getBoundingClientRect()}));
    boxes.forEach((a,i)=>boxes.slice(i+1).forEach(b=>{if(a.r.left<b.r.right-1&&a.r.right>b.r.left+1&&a.r.top<b.r.bottom-1&&a.r.bottom>b.r.top+1)issues.push(['buttons overlap',a.id,b.id]);}));
    if(document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight)issues.push(['page scrolls']);
    return issues;
  });
  assert.deepEqual(issues,[],`${JSON.stringify(page.viewportSize())}, guest=${guest}, ${variant}: ${JSON.stringify(issues)}`);
}
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try{
    const page=await browser.newPage({viewport:{width:402,height:700},isMobile:true,hasTouch:true,reducedMotion:'reduce'}),errors=[];
    // Exercise our fallback without opening the operating system's share UI.
    await page.addInitScript(()=>Object.defineProperty(navigator,'share',{value:undefined,configurable:true}));
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/players/me')return route.fulfill({status:guest?401:200,json:guest?{detail:'Sign in'}:{username:'Tester',total_xp:24680,level:12}});
      if(path==='/api/solo/catalog')return route.fulfill({json:catalog});
      if(path==='/api/solo/active')return route.fulfill({json:{run,trial_available:true}});
      if(path==='/api/shares/results')return route.fulfill({json:{title:'Shootout result',url:origin+'/s/test-result',image_url:origin+'/share/brand.png'}});
      throw new Error(`Unexpected ${path}`);
    });
    for(const [width,height] of [[320,480],[320,568],[375,620],[390,664],[402,700],[430,780],[768,1024],[568,320],[667,375],[844,390],[1280,720],[1440,1000]]){
      await page.setViewportSize({width,height});
      for(guest of [true,false])for(variant of ['win','loss','abandoned','empty','exhausted']){
        run=result();await page.goto(origin+'/penalties?ad_preview=1');
        await page.waitForSelector('#summary:not([hidden])');
        await page.waitForFunction(()=>!document.getElementById('share-result').disabled);
        await check(page);
        // Same card during/after the live stadium outro, not just a history load.
        await page.evaluate(()=>{document.body.classList.add('stadium-playing','stadium-ending');document.body.style.setProperty('--stadium-result','1');});
        await check(page);
        if(guest&&variant==='win')await page.screenshot({path:`${output}/${width}x${height}-guest.png`});
        if(!guest&&variant==='win'&&width===402)await page.screenshot({path:`${output}/member.png`});
        if(guest&&variant==='win'){
          await page.locator('#result-review').click();
          assert.equal(await page.locator('#review .review-item').count(),1);
          assert.equal(await page.locator('#review-position').textContent(),'1 / 16');
          await page.locator('#review-next').click();assert.equal(await page.locator('#review-position').textContent(),'2 / 16');
          await page.locator('#review-previous').click();assert.equal(await page.locator('#review-position').textContent(),'1 / 16');
          await page.locator('#review-close').click();await check(page);
          await page.locator('#share-result').click();
          await page.waitForSelector('#share-dialog[open]');
          const overflow=await page.locator('#share-dialog').evaluate(e=>e.scrollHeight>e.clientHeight+1||e.getBoundingClientRect().bottom>innerHeight);
          assert(!overflow,'Share dialog overflows');
          await page.locator('#share-close').click();await check(page);
          await page.mouse.wheel(0,500);assert.equal(await page.evaluate(()=>scrollY),0);
        }
      }
      console.log(`PASS ${width}x${height}: guest/member, win/loss/end/empty/pool exhausted, history + outro`);
    }
    await page.locator('#another').click();assert(await page.locator('#selection').isVisible());
    assert(!await page.locator('#summary').isVisible());assert(!await page.locator('#shootout-board').isVisible());
    assert.deepEqual(errors,[]);
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
