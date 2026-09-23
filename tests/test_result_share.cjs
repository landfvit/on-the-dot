const test=require('node:test'),assert=require('node:assert/strict');
const {snapshot,draw,share}=require('../trivia_app/static/result_share.js');
const run={run_id:'private-id',phase:'FINISHED',difficulty:'hard',correct:6,total_xp:720,multiplier:4,rules:{bonus_mode:'win'},
  review:Array.from({length:6},()=>({text:'Private question',correct:'answer-secret'})),
  shootout:{player:3,opponent:0,winner:'player',attempts:[{side:'player',goal:true},{side:'opponent',goal:false}]}};
const user={username:'tester',email:'private@example.com',club:{name:'Manchester United'}};
test('share snapshot contains score and deployment URL but no private data',()=>{
  const data=snapshot(run,user,'https://example.com');
  assert.equal(data.url,'https://example.com/penalties');assert.equal(data.score,'3 : 0');
  assert.equal(data.status,'Shootout won');assert.equal(data.xp,720);assert.equal(data.team,'Manchester United');
  for(const secret of ['private-id','Private question','answer-secret','private@example.com'])assert(!JSON.stringify(data).includes(secret));
});
test('abandonment, trial and legacy cards retain honest result labels',()=>{
  const ended=snapshot({...run,phase:'ABANDONED',is_trial:true,shootout:{...run.shootout,player:0,opponent:0,winner:null}},null,'http://127.0.0.1:8004');
  assert.equal(ended.status,'Shootout ended');assert.equal(ended.player,'You');assert.equal(ended.team,'');assert.match(ended.text,/trial XP/);
  const legacy=snapshot({...run,shootout:undefined,rules:{questions:10}},user,'https://example.com');
  assert.equal(legacy.score,'6 / 10');assert.equal(legacy.attempts,null);
});
test('native share receives the actual PNG file and public URL',async()=>{
  const file={name:'result.png',type:'image/png'},card={data:snapshot(run,user,'https://example.com'),file};let sent;
  const result=await share(card,{canShare:data=>data.files[0]===file,share:data=>{sent=data;return Promise.resolve();}});
  assert.equal(result,'shared');assert.equal(sent.files[0],file);assert.equal(sent.url,card.data.url);
  assert.deepEqual(Object.keys(sent).sort(),['files','text','title','url']);
});
test('unsupported file sharing uses fallback and cancellation does not send again',async()=>{
  const card={data:snapshot(run,user,'https://example.com'),file:{}};
  assert.equal(await share(card,{}),'fallback');
  assert.equal(await share(card,{canShare:()=>false,share:()=>assert.fail('Must not send unsupported files')}),'fallback');
  assert.equal(await share(card,{canShare:()=>true,share:async()=>{throw Object.assign(new Error('Cancelled'),{name:'AbortError'});}}),'cancelled');
});
test('card is fixed size and text stays within measured lanes',()=>{
  const labels=[];const context={measureText:text=>({width:text.length*24}),fillText:(...args)=>labels.push(args),fillRect(){},beginPath(){},arc(){},stroke(){},fill(){},moveTo(){},lineTo(){},closePath(){}};
  const canvas={getContext:()=>context};
  draw(snapshot(run,{...user,username:'long_username_12345678901',club:{name:'A very long club name'.repeat(4)}},'https://example.com'),{createElement:()=>canvas});
  assert.equal(canvas.width,1200);assert.equal(canvas.height,630);
  assert(labels.some(([text])=>text==='3 : 0'));assert(labels.every(([,x,y,,])=>x>=0&&x<=1200&&y>=0&&y<=630));
});
