/* Local visual checks for individual logo circles and transparent tab icons. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
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
    if(path==='/')await page.waitForFunction(()=>document.querySelector('.home-logo')?.complete&&document.querySelector('.home-logo').naturalWidth===432);
    if(path==='/penalties')await page.waitForFunction(()=>!document.getElementById('start').disabled);
    assert.equal(await page.locator('.brand-word img').count(),0,'No raster crop may leak neighboring rows');
    const brand=page.getByRole('link',{name:'ON THE DOT. home',exact:true});
    assert.equal(await brand.getAttribute('href'),'/');
    assert.equal((await brand.textContent()).trim(),'','Header must use the artwork, not a second text wordmark');
    const brandBox=await brand.boundingBox();
    assert(brandBox.x>=16);assert(brandBox.x+brandBox.width<=width-16);
    assert(brandBox.height>=44,'Keep the home link touch target');
    const words=await page.locator('.brand-word').evaluateAll(es=>es.map(e=>{
     const r=e.getBoundingClientRect();
     return {name:e.dataset.word,x:r.x,y:r.y,width:r.width,height:r.height};
    }));
    assert.deepEqual(words.map(w=>w.name),['ON','THE','DOT']);
    for(let i=0;i<words.length;i++){
     assert.equal(words[i].height,width<=700?24:32);
     assert.equal(words[i].y,words[0].y,'All words must share one baseline');
     if(i)assert(words[i-1].x+words[i-1].width<words[i].x,'Words must not overlap');
    }
    const letters=await page.locator('.brand-letter').evaluateAll(es=>es.map(e=>{
     const r=e.getBoundingClientRect(),glyph=e.querySelector('path'),bounds=glyph.getBBox(),style=getComputedStyle(glyph);
     return {letter:e.dataset.letter,width:r.width,height:r.height,y:r.y,path:glyph.getAttribute('d'),cap:bounds.y,baseline:bounds.y+bounds.height,
      center:bounds.x+bounds.width/2,stroke:style.strokeWidth,fill:getComputedStyle(e.querySelector('circle')).fill};
    }));
    assert.equal(letters.map(l=>l.letter).join(''),'ONTHEDOT');
    for(const letter of letters){
     assert.equal(letter.width,width<=700?24:32);assert.equal(letter.height,letter.width);
     assert.equal(letter.y,letters[0].y);assert.equal(letter.cap,27);assert.equal(letter.baseline,73);
     assert.equal(letter.center,50);assert.equal(letter.stroke,'9px');assert.equal(letter.fill,'rgb(136, 176, 75)');
    }
    assert.equal(letters[0].path,letters[6].path,'Both O glyphs must be identical');
    assert.equal(letters[2].path,letters[7].path,'Both T glyphs must be identical');
    // Render the actual styled SVG nodes. Transparent corners detect the crop
    // artifact, and pixel counts catch missing circles or invisible lettering.
    if(path==='/'){
     const svgs=await page.locator('.brand-letter,.brand-dot').evaluateAll(es=>es.map(e=>{
      const clone=e.cloneNode(true);clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
      clone.setAttribute('width','64');clone.setAttribute('height','64');
      for(const [i,child] of [...clone.children].entries()){
       const style=getComputedStyle(e.children[i]);
       for(const key of ['fill','stroke','stroke-width','stroke-linecap','stroke-linejoin'])child.setAttribute(key,style.getPropertyValue(key));
      }
      return clone.outerHTML;
     }));
     assert.equal(svgs.length,9);
     for(const svg of svgs){
      const {data,info}=await sharp(Buffer.from(svg)).ensureAlpha().raw().toBuffer({resolveWithObject:true});
      let green=0,black=0;
      for(let i=0;i<data.length;i+=4)if(data[i+3]>240){
       if(data[i]===136&&data[i+1]===176&&data[i+2]===75)green++;
       if(data[i]<10&&data[i+1]<10&&data[i+2]<10)black++;
      }
      for(const [x,y] of [[0,0],[63,0],[0,63],[63,63]])assert.equal(data[(y*info.width+x)*4+3],0,'No stray fragments outside the circle');
      assert(green>64*64*.4);assert(black>30,'Every circle must include a visible glyph');
     }
    }
    assert.equal(await page.locator('#menu-open,#menu-drawer').count(),0);
    assert(await page.locator('.top-navigation').isVisible());
    if(path==='/'){
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
    }else{
     assert.equal(await page.locator('.home-logo').count(),0,'Penalties must not have a duplicate logo');
     const heading=await page.locator('.solo-heading h1').boundingBox(),help=await page.locator('.game-rules-link').boundingBox();
     assert(heading.x+heading.width<=help.x||heading.y+heading.height<=help.y,'Heading and help must not overlap');
    }
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const favicons=await page.evaluate(async()=>{
     const results=[];
     for(const icon of document.querySelectorAll('link[rel=icon]'))for(const size of [16,32]){
      const img=new Image();img.src=icon.href;await img.decode();
      const canvas=document.createElement('canvas');canvas.width=canvas.height=size;
      const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,size,size);
      const data=ctx.getImageData(0,0,size,size).data;let green=0,white=0,dark=0,transparent=0,left=size,right=-1,top=size,bottom=-1;
      for(let i=0;i<data.length;i+=4)if(data[i+3]===0)transparent++;
      for(let i=0;i<data.length;i+=4)if(data[i+3]>240){
       if(data[i]>240&&data[i+1]>240&&data[i+2]>240)white++;
       if(data[i]<80&&data[i+1]<80&&data[i+2]<80)dark++;
      }
      for(let i=0;i<data.length;i+=4)if(data[i+3]>128&&Math.abs(data[i]-136)<8&&Math.abs(data[i+1]-176)<8&&Math.abs(data[i+2]-75)<8){
       green++;const x=(i/4)%size,y=Math.floor(i/4/size);
       left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
      }
      results.push({src:icon.getAttribute('href'),green,size,left,right,top,bottom,white,dark,transparent,cornerAlpha:data[3]});
     }
     return results;
    });
    assert.equal(favicons.length,4);
    for(const f of favicons){
     assert(f.src.startsWith('/trivia-assets/brand/favicon.'));
     assert(f.green>f.size*f.size*.55,'Logo should fill most of the tab icon');
     assert(f.left<=1&&f.right>=f.size-2&&f.top<=2&&f.bottom>=f.size-3,JSON.stringify(f));
     assert.equal(f.white,0,'No white background remains');
     assert.equal(f.dark,0,'No black background remains');
     assert.equal(f.cornerAlpha,0,'The favicon must have no background');
     assert(f.transparent>f.size*f.size*.1,'Transparent gaps must exist between circles');
    }
    await page.screenshot({path:`${output}/${path==='/'?'home':'penalties'}-${width}.png`});
   }
   console.log(`PASS ${width}: separate palette-green circles, uniform glyphs, clean Penalties heading and transparent favicon`);
  }
  const response=await page.request.get(origin+'/favicon.ico');assert(response.ok());assert.equal(response.headers()['content-type'],'image/png');
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
