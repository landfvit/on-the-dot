/* Local visual checks for the transparent wordmark and rounded white tab icons. */
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
   for(const path of ['/','/penalties']){
    await page.goto(origin+path);
    await page.waitForFunction(()=>document.querySelector('.home-logo')?.complete&&document.querySelector('.home-logo').naturalWidth===432);
    if(path==='/penalties')await page.waitForFunction(()=>!document.getElementById('start').disabled);
    await page.waitForFunction(()=>[...document.querySelectorAll('.brand-word img')].every(e=>e.complete&&e.naturalWidth===432));
    const brand=page.getByRole('link',{name:'ON THE DOT. home',exact:true});
    assert.equal(await brand.getAttribute('href'),'/');
    assert.equal((await brand.textContent()).trim(),'','Header must use the artwork, not a second text wordmark');
    const menu=await page.locator('#menu-open').boundingBox(),brandBox=await brand.boundingBox();
    assert(menu.x+menu.width<brandBox.x);assert(brandBox.x+brandBox.width<=width-16);
    assert(brandBox.height>=44,'Keep the home link touch target');
    const words=await page.locator('.brand-word').evaluateAll(es=>es.map(e=>{
     const r=e.getBoundingClientRect(),img=e.querySelector('img');
     return {name:e.classList[1],x:r.x,y:r.y,width:r.width,height:r.height,image:img.getBoundingClientRect().width};
    }));
    assert.deepEqual(words.map(w=>w.name),['brand-word-on','brand-word-the','brand-word-dot']);
    for(let i=0;i<words.length;i++){
     assert.equal(words[i].height,width<=700?24:32);
     assert.equal(words[i].y,words[0].y,'All words must share one baseline');
     assert(Math.abs(words[i].image/words[i].height-432/110)<.01,'Never stretch the source letters');
     if(i)assert(words[i-1].x+words[i-1].width<words[i].x,'Words must not overlap');
    }
    await page.locator('#menu-open').click();assert(await page.locator('#menu-drawer').isVisible());
    await page.getByRole('button',{name:'Close menu',exact:true}).click();
    const logo=await page.locator('.home-logo').boundingBox(),heading=await page.locator('.brand-heading h1').boundingBox(),action=await page.locator('.brand-heading > a').boundingBox();
    assert.equal(logo.width,logo.height);assert(logo.width>=96);assert(logo.y+logo.height<height);
    assert(logo.x+logo.width<=heading.x);assert(heading.y+heading.height<=action.y+1);
    const logoStyle=await page.locator('.home-logo').evaluate(e=>({radius:getComputedStyle(e).borderRadius,background:getComputedStyle(e).backgroundColor}));
    assert.equal(logoStyle.radius,'0px');assert.equal(logoStyle.background,'rgba(0, 0, 0, 0)');
    const wordmark=await page.locator('.home-logo').evaluate(e=>{
     const canvas=document.createElement('canvas');canvas.width=canvas.height=96;
     const ctx=canvas.getContext('2d');ctx.drawImage(e,0,0,96,96);
     const data=ctx.getImageData(0,0,96,96).data;let transparent=0,green=0,black=0;
     for(let i=0;i<data.length;i+=4){
      if(data[i+3]===0)transparent++;
      if(data[i+3]>240&&data[i+1]>100&&data[i+1]>data[i]*2)green++;
      if(data[i+3]>240&&data[i]<40&&data[i+1]<40&&data[i+2]<40)black++;
     }
     return {cornerAlpha:data[3],transparent,green,black};
    });
    assert.equal(wordmark.cornerAlpha,0,'Wordmark background must be transparent');
    assert(wordmark.transparent>96*96*.3,'Background and gaps must have genuine alpha');
    assert(wordmark.green>96*96*.2,'Green discs must remain visible');
    assert(wordmark.black>96*96*.03,'Black lettering must remain opaque');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const favicons=await page.evaluate(async()=>{
     const results=[];
     for(const icon of document.querySelectorAll('link[rel=icon]'))for(const size of [16,32]){
      const img=new Image();img.src=icon.href;await img.decode();
      const canvas=document.createElement('canvas');canvas.width=canvas.height=size;
      const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,size,size);
      const data=ctx.getImageData(0,0,size,size).data;let green=0,white=0,dark=0,left=size,right=-1,top=size,bottom=-1;
      for(let i=0;i<data.length;i+=4)if(data[i+3]>240){
       if(data[i]>240&&data[i+1]>240&&data[i+2]>240)white++;
       if(data[i]<80&&data[i+1]<80&&data[i+2]<80)dark++;
      }
      for(let i=0;i<data.length;i+=4)if(data[i+1]>100&&data[i+1]>data[i]*2&&data[i+1]>data[i+2]*1.2){
       green++;const x=(i/4)%size,y=Math.floor(i/4/size);
       left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
      }
      results.push({src:icon.getAttribute('href'),green,size,left,right,top,bottom,white,dark,cornerAlpha:data[3]});
     }
     return results;
    });
    assert.equal(favicons.length,4);
    for(const f of favicons){
     assert(f.src.startsWith('/trivia-assets/brand/favicon.'));
     assert(f.green>f.size*f.size*.55,'Logo should fill most of the tab icon');
     assert(f.left<=1&&f.right>=f.size-2&&f.top<=2&&f.bottom>=f.size-3,JSON.stringify(f));
     assert(f.white>f.size*f.size*.1,'Favicon needs a white background: '+JSON.stringify(f));
     assert.equal(f.dark,0,'No black background remains');
     assert(f.cornerAlpha<160,'Rounded corners must be transparent: '+JSON.stringify(f));
    }
    await page.screenshot({path:`${output}/${path==='/'?'home':'penalties'}-${width}.png`});
   }
   console.log(`PASS ${width}: horizontal header logo, working menu, transparent wordmark and rounded favicon`);
  }
  const response=await page.request.get(origin+'/favicon.ico');assert(response.ok());assert.equal(response.headers()['content-type'],'image/png');
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
