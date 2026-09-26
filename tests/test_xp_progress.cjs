const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const script=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/xp_progress.js'),'utf8');
function setup({reduced=false}={}){
 const nodes=new Map(),frames=new Map(),events={},sounds=[];let sequence=0;
 const get=id=>{if(!nodes.has(id)){const classes=new Set();nodes.set(id,{hidden:false,textContent:'',value:0,max:100,offsetWidth:100,classList:{add:v=>classes.add(v),remove:v=>classes.delete(v),contains:v=>classes.has(v)}});}return nodes.get(id);};
 const context={document:{hidden:false,getElementById:get,addEventListener:(n,f)=>events[n]=f},window:{addEventListener:(n,f)=>events[n]=f},
  matchMedia:()=>({matches:reduced}),PointsAudio:{play:n=>sounds.push(n)},requestAnimationFrame:f=>{frames.set(++sequence,f);return sequence;},cancelAnimationFrame:id=>frames.delete(id)};
 vm.runInNewContext(script,context);
 return {get,events,sounds,context,api:context.PointsProgress,ui:context.PointsProgress.bindResult(),
  tick(time){const pending=[...frames.values()];frames.clear();pending.forEach(f=>f(time));},pending:()=>frames.size};
}
const levels=[{level:1,minimum_xp:0},{level:2,minimum_xp:200},{level:3,minimum_xp:600},{level:4,minimum_xp:1200}];
function progress(total){const i=levels.findLastIndex(l=>l.minimum_xp<=total);return {level:levels[i].level,total_xp:total,level_xp:levels[i].minimum_xp,next_level_xp:levels[i+1]?.minimum_xp??null};}
function run(before=150,after=650){return {run_id:'test',is_trial:false,player_progress:progress(after),xp_transition:{earned_xp:after-before,before:progress(before),after:progress(after),levels}};}
function finish(s){for(let t=0;t<=6000;t+=100)s.tick(t);}
test('multiple level thresholds come only from the server',()=>{
 const s=setup(),steps=s.api.segments(run().xp_transition);
 assert.deepEqual(JSON.parse(JSON.stringify(steps.map(x=>[x.start,x.end,x.reached]))),[[150,200,2],[200,600,3],[600,650,null]]);
});
test('bar waits for visible results, rolls over, then lands on the exact balance',()=>{
 const s=setup();s.ui.prepare(run(),{animate:true});assert.equal(s.pending(),0);assert.equal(s.get('result-level-progress').value,150);
 s.ui.reveal();s.tick(0);s.tick(300);assert(s.get('result-level-progress').value>150&&s.get('result-level-progress').value<200);
 finish(s);assert.equal(s.get('result-level-progress').max,600);assert.equal(s.get('result-level-progress').value,50);
 assert.equal(s.get('result-level-label').textContent,'Level 3');assert.equal(s.get('result-xp-total').textContent,'650 total XP');
 assert.deepEqual(s.sounds,['level-up']);assert.equal(s.get('result-level-up').textContent,'Level 3 unlocked!');
});
test('repeated result responses never restart a celebration',()=>{
 const s=setup(),r=run();s.ui.prepare(r,{animate:true});s.ui.reveal();finish(s);s.ui.prepare(r,{animate:true});s.ui.reveal();finish(s);
 assert.deepEqual(s.sounds,['level-up']);assert.equal(s.pending(),0);
});
test('history and refresh show final XP without a celebration',()=>{
 const s=setup();s.ui.prepare(run());s.ui.reveal();finish(s);assert.deepEqual(s.sounds,[]);assert.equal(s.pending(),0);assert.equal(s.get('result-level-progress').value,50);
});
test('same-level rewards fill the bar without a level-up sound',()=>{
 const s=setup();s.ui.prepare(run(10,70),{animate:true});s.ui.reveal();finish(s);assert.equal(s.get('result-level-progress').value,70);assert.deepEqual(s.sounds,[]);
});
test('zero XP and guest games never animate or celebrate',()=>{
 for(const r of [run(150,150),{...run(),is_trial:true}]){const s=setup();s.ui.prepare(r,{animate:true});s.ui.reveal();assert.equal(s.pending(),0);assert.deepEqual(s.sounds,[]);}
});
test('reduced motion renders the final bar and a static level notification',()=>{
 const s=setup({reduced:true});s.ui.prepare(run(),{animate:true});s.ui.reveal();assert.equal(s.pending(),0);assert.equal(s.get('result-level-progress').value,50);
 assert(!s.get('result-level').classList.contains('is-level-up'));assert.deepEqual(s.sounds,['level-up']);
});
test('leaving the result cancels pending frames and sounds',()=>{
 const s=setup();s.ui.prepare(run(),{animate:true});s.ui.reveal();s.ui.clear();finish(s);assert.equal(s.pending(),0);assert.deepEqual(s.sounds,[]);
});
test('backgrounding finishes silently instead of queueing celebrations',()=>{
 const s=setup();s.ui.prepare(run(),{animate:true});s.ui.reveal();s.context.document.hidden=true;s.events.visibilitychange();finish(s);
 assert.equal(s.get('result-level-progress').value,50);assert.deepEqual(s.sounds,[]);assert.equal(s.pending(),0);
});
test('exact threshold resets to the next level and maximum level stays full',()=>{
 for(const [end,value,max] of [[200,0,400],[1300,1,1]]){const s=setup();s.ui.prepare(run(150,end),{animate:true});s.ui.reveal();finish(s);assert.equal(s.get('result-level-progress').value,value);assert.equal(s.get('result-level-progress').max,max);}
});
