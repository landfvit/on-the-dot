/* Public appearance and preferences only. Never starts a production game. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8015';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/tmp/on-the-dot-dark';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({colorScheme:'dark'}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin+'/');assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:900});
   for(const path of ['/','/penalties','/friends','/daily','/leaderboard','/account','/how-to-play']){
    await page.goto(origin+path);
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(25, 28, 26)');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${path} ${width}`);
    await page.screenshot({path:`${out}/${width}-${path.slice(1)||'home'}.png`,fullPage:true});
   }
   const pixels=await sharp(await page.locator('.guide-kick-legend').screenshot()).raw().toBuffer({resolveWithObject:true});
   let ink=0,white=0;for(let i=0;i<pixels.data.length;i+=pixels.info.channels){const [r,g,b]=pixels.data.subarray(i,i+3);if(r<22&&g<22&&b<22)ink++;if(r>245&&g>245&&b>245)white++;}
   assert(ink>20&&white>20,'White balls must retain black panels and an outline');
   console.log(`PASS dark UI ${width}: 7 pages and outlined white balls`);
  }
  await page.locator('.page-return [data-theme-toggle]').click();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'light');await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  await page.emulateMedia({colorScheme:'dark'});assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  const tab=await context.newPage();await tab.goto(origin+'/');
  await page.locator('.page-return [data-theme-toggle]').focus();await page.keyboard.press('Enter');
  await tab.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  assert.deepEqual(errors,[]);await context.close();
  const denied=await browser.newContext();await denied.addInitScript(()=>{Object.defineProperty(window,'localStorage',{get(){throw Error('blocked');}});});
  const fallback=await denied.newPage();await fallback.goto(origin+'/');await fallback.locator('[data-theme-toggle]').click();
  assert.equal(await fallback.locator('html').getAttribute('data-theme'),'dark');await denied.close();
  console.log('PASS system default, saved choice, keyboard, cross-tab sync and blocked storage');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
