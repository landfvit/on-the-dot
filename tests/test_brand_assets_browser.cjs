/* Local visual checks. Original PNGs stay intact; the browser scales them. */
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
  for(const [width,height] of [[320,568],[390,844],[1440,1000]]){
   await page.setViewportSize({width,height});
   for(const path of ['/','/penalties']){
    await page.goto(origin+path);
    await page.waitForFunction(()=>document.querySelector('.home-logo')?.complete&&document.querySelector('.home-logo').naturalWidth===2000);
    if(path==='/penalties')await page.waitForFunction(()=>!document.getElementById('start').disabled);
    const logo=await page.locator('.home-logo').boundingBox(),heading=await page.locator('.brand-heading h1').boundingBox(),action=await page.locator('.brand-heading > a').boundingBox();
    assert.equal(logo.width,logo.height);assert(logo.width>=96);assert(logo.y+logo.height<height);
    assert(logo.x+logo.width<=heading.x);assert(heading.y+heading.height<=action.y+1);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const favicons=await page.evaluate(async()=>{
     const results=[];
     for(const icon of document.querySelectorAll('link[rel=icon]'))for(const size of [16,32]){
      const img=new Image();img.src=icon.href;await img.decode();
      const canvas=document.createElement('canvas');canvas.width=canvas.height=size;
      const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,size,size);
      const data=ctx.getImageData(0,0,size,size).data;let green=0,left=size,right=-1,top=size,bottom=-1;
      for(let i=0;i<data.length;i+=4)if(data[i+1]>100&&data[i+1]>data[i]*2&&data[i+1]>data[i+2]*1.2){
       green++;const x=(i/4)%size,y=Math.floor(i/4/size);
       left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
      }
      results.push({src:icon.getAttribute('href'),green,size,left,right,top,bottom});
     }
     return results;
    });
    assert.equal(favicons.length,4);
    for(const f of favicons){
     assert(f.src.startsWith('/trivia-assets/brand/favicon.'));
     assert(f.green>f.size*f.size*.55,'Logo should fill most of the tab icon');
     assert(f.left<=1&&f.right>=f.size-2&&f.top<=2&&f.bottom>=f.size-3,JSON.stringify(f));
    }
    await page.screenshot({path:`${output}/${path==='/'?'home':'penalties'}-${width}.png`});
   }
   console.log(`PASS ${width}: original wordmark, compact heading, loaded and nonblank favicon`);
  }
  const response=await page.request.get(origin+'/favicon.ico');assert(response.ok());assert.equal(response.headers()['content-type'],'image/png');
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
