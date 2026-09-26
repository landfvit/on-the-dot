/* Local checks: symbol-only header, no duplicate guide logo, transparent favicon. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const output='/tmp/on-the-dot-brand';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname;let data,status=200;
   if(path==='/api/players/me'){status=401;data={detail:'Sign in'};}
   else if(path==='/api/solo/active')data={run:null,trial_available:true};
   else if(path==='/api/solo/catalog')data={categories:[],topics:[{code:'ALL',counts_by_team:{ALL:{easy:50,medium:50,hard:50}}}],
    rules:{format:'shootout',bonus_mode:'win',answer_ms:15000,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}}};
   else throw Error('Unexpected API '+path);
   await route.fulfill({status,json:data});
  });
  for(const [width,height] of [[320,568],[390,844],[700,1000],[768,1024],[1440,1000]]){
   await page.setViewportSize({width,height});
   for(const path of ['/','/how-to-play','/penalties']){
    await page.goto(origin+path);
    await page.waitForFunction(()=>document.querySelector('.brand-mark')?.complete);
    const brand=page.getByRole('link',{name:'ON THE DOT. home',exact:true});
    assert.equal(await brand.getAttribute('href'),'/');
    assert.equal((await brand.textContent()).trim(),'');
    assert.equal(await page.locator('.brand-wordmark,.home-logo,.brand-letter').count(),0);
    assert.equal(await page.locator('.brand-mark:visible').count(),1);
    const box=await brand.boundingBox();assert(box.x>=0&&box.x+box.width<=width);assert(box.height>=44);
    const icon=page.locator('.brand-mark');assert((await icon.getAttribute('src')).includes('/brand/favicon.svg'));
    assert(await icon.evaluate(e=>e.naturalWidth>0));
    const nav=await page.locator('.top-navigation').boundingBox();
    assert((await page.locator('.top-navigation a').first().locator('img').getAttribute('src')).includes('football-outline.svg'));
    for(const theme of ['dark','light']){
     await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
     const styles=await page.locator('.top-navigation a').evaluateAll(es=>es.map(e=>{
      const s=getComputedStyle(e);return {selected:e.hasAttribute('aria-current'),bg:s.backgroundColor,radius:s.borderRadius,filter:getComputedStyle(e.querySelector('img')).filter};
     }));
     assert(styles.every(s=>s.bg===(s.selected?(theme==='dark'?'rgb(246, 243, 235)':'rgb(17, 17, 17)'):'rgba(0, 0, 0, 0)')&&s.radius==='999px'&&s.filter===`invert(${s.selected?(theme==='dark'?0:1):(theme==='dark'?1:0)})`),JSON.stringify(styles));
    }
    if(path==='/how-to-play')assert((await page.locator('main').innerText()).split(/\s+/).length<650,'Keep Full Rules concise');
    assert(box.x+box.width<=nav.x||box.y+box.height<=nav.y,JSON.stringify({width,box,nav}));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const pixels=await icon.evaluate(e=>{
     const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d');x.drawImage(e,0,0,64,64);
     const d=x.getImageData(0,0,64,64).data;let green=0,transparent=0,letter=0;
     for(let i=0;i<d.length;i+=4){
      if(d[i+3]===0)transparent++;
      if(d[i+3]>240&&Math.abs(d[i]-136)<8&&Math.abs(d[i+1]-176)<8&&Math.abs(d[i+2]-75)<8)green++;
      if(d[i+3]>240&&d[i]>235&&d[i+1]>235)letter++;
     }
     return {green,transparent,letter,corner:d[3]};
    });
    assert(pixels.green>64*64*.55);assert(pixels.transparent>64*64*.1);assert.equal(pixels.letter,0);assert.equal(pixels.corner,0);
    const favicons=await page.locator('link[rel=icon]').evaluateAll(es=>es.map(e=>e.getAttribute('href')));
    assert.equal(favicons.length,2);assert(favicons.every(x=>x.includes('/brand/favicon.')));
    await page.screenshot({path:output+'/'+(path==='/'?'home':path.slice(1))+'-'+width+'.png'});
   }
   console.log('PASS '+width+': one symbol in the top-left header, no guide duplicate or overflow');
  }
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
