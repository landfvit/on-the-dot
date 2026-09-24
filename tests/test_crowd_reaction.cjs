const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/crowd_reaction.js'),'utf8');
const logic=import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
for(const viewer of [0,1])for(const role of ['shooter','keeper'])for(const outcome of ['goal','save','miss','replay']){
 test(`supporters: seat ${viewer}, ${role}, ${outcome}`,async()=>{
  const {reactionForShot}=await logic,s=role==='shooter'?viewer:1-viewer;
  const result=reactionForShot(outcome,role,viewer),winner=outcome==='replay'?null:outcome==='goal'?s:1-s;
  assert.equal(result.winner,winner);
  assert.deepEqual(result.moods,winner===null?['neutral','neutral']:winner===0?['cheer','sad']:['sad','cheer']);
  const opponent=reactionForShot(outcome,role==='shooter'?'keeper':'shooter',1-viewer);
  assert.deepEqual(opponent,result,'Both Duel clients must agree which physical stand celebrates');
 });
}
test('unknown or unresolved results never make supporters celebrate',async()=>{
 const {reactionForShot}=await logic;for(const outcome of [undefined,null,'pending',''])assert.deepEqual(reactionForShot(outcome,'shooter').moods,['neutral','neutral']);
});
