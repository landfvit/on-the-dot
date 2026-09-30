const test=require('node:test'),assert=require('node:assert/strict');
const kits=require('../trivia_app/static/player-kits/catalog.json').kits;
const painter=import('../trivia_app/static/kit_pixels.js');

test('smaller shirt numbers keep all 99 values distinct and inside the jersey',async()=>{
  const {kitPixels}=await painter;
  for(const kit of kits){
    const signatures=new Set();
    for(let number=1;number<=99;number++){
      const {rows}=kitPixels(kit,'back',number),ink=[];
      rows.forEach((row,y)=>[...row].forEach((key,x)=>{if(key==='N')ink.push([x,y]);}));
      assert(ink.length>0);
      const xs=ink.map(p=>p[0]),ys=ink.map(p=>p[1]);
      assert.equal(Math.max(...ys)-Math.min(...ys)+1,5);
      assert(Math.max(...xs)-Math.min(...xs)+1<=(number<10?3:7));
      assert(ink.every(([x,y])=>x>=5&&x<=11&&y>=7&&y<=11));
      assert.equal(rows.length,20);assert(rows.every(row=>row.length===18));
      signatures.add(JSON.stringify(ink));
    }
    assert.equal(signatures.size,99,kit.id);
  }
});

test('one has a single-pixel stem alone and in either position of two-digit numbers',async()=>{
  const {kitPixels}=await painter,expected=['010','110','010','010','111'];
  for(const number of [1,10,11,12,13,14,15,16,17,18,19,21,31,41,51,61,71,81,91]){
    const value=String(number),x0=Math.floor((18-(value.length*4-1))/2);
    const {rows}=kitPixels(kits[0],'back',number);
    [...value].forEach((digit,index)=>{
      if(digit==='1')assert.deepEqual(rows.slice(7,12).map(row=>[...row.slice(x0+index*4,x0+index*4+3)].map(p=>p==='N'?'1':'0').join('')),expected,String(number));
    });
  }
});

test('numbers never alter the front, sleeves, shorts or socks',async()=>{
  const {kitPixels}=await painter;
  for(const kit of kits)for(const part of ['front','sleeve','shorts','sock']){
    assert.deepEqual(kitPixels(kit,part,1),kitPixels(kit,part,99));
  }
});
