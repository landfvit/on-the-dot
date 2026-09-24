const test=require('node:test'),assert=require('node:assert/strict');
const {prepare,share}=require('../trivia_app/static/result_share.js');
const card={data:{url:'https://onthedot.gg/s/opaque',title:'3 : 0 | ON THE DOT.'}};
test('native share receives only a clickable result link and title',async()=>{
  let sent;assert.equal(await share(card,{share:async data=>{sent=data;}}),'shared');
  assert.deepEqual(sent,{title:card.data.title,url:card.data.url});
  assert(!('files' in sent));assert(!('text' in sent));
});
test('fallback and cancellation do not force another share',async()=>{
  assert.equal(await share(card,{}),'fallback');
  assert.equal(await share(card,{share:async()=>{throw {name:'AbortError'};}}),'cancelled');
  assert.equal(await share(card,{share:async()=>{throw {name:'NotAllowedError'};}}),'fallback');
});
test('publishing asks the server for scores and never submits client answers',async()=>{
  const old=global.fetch;let sent;
  try{
    global.fetch=async(url,options)=>{sent={url,...options};return {ok:true,json:async()=>({...card.data,image_url:card.data.url+'/image.png'})};};
    const result=await prepare({run_id:'id',mode:'friend',score:[999,0],email:'secret',review:['answer']});
    assert.deepEqual(JSON.parse(sent.body),{run_id:'id',mode:'friend'});
    assert.equal(result.imageUrl,card.data.url+'/image.png');assert(!result.file);
  }finally{global.fetch=old;}
});
