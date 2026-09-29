const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../trivia_app/static/friends.js'),'utf8');
// Isolate the actual presentation queue, without account/network/DOM setup.
const present=source.slice(source.indexOf('  function present(s){'),source.indexOf('  function summary(s){'));
function harness(me=0){
    const calls=[],elements=new Map();let finishShot;
    const context=vm.createContext({
        presentation:0,entered:true,finished:false,role:me===0?'shooter':'keeper',animation:Promise.resolve(),animated:new Set(),code:'test-room',room:null,
        terminal:s=>['FINISHED','ABANDONED'].includes(s?.phase),
        $:id=>{if(!elements.has(id))elements.set(id,{hidden:false,focus(){}});return elements.get(id);},
        stadium:{
            shot:()=>{calls.push('shot');return new Promise(resolve=>{finishShot=resolve;});},
            enter:async role=>{calls.push('enter:'+role);},reset:()=>calls.push('reset'),skip:()=>calls.push('skip'),
            finish:async()=>calls.push('finish'),leave:()=>calls.push('leave'),
        },PenaltyShots:{plan:()=>({})},PointsAudio:{play:()=>{}},
    });
    vm.runInContext(present,context);
    const snapshot=(phase='RESOLVED',outcome='goal')=>({phase,me,initial_shooter:0,round:{id:1,shooter:0,outcome},winner:0});
    return {calls,context,snapshot,queue:s=>context.present(s),done:()=>context.animation,release:()=>finishShot(),flush:()=>new Promise(resolve=>setImmediate(resolve))};
}
for(const me of [0,1])test(`seat ${me} moves after the shot without waiting for a server countdown`,async()=>{
    const h=harness(me),s=h.snapshot();h.queue(s);await h.flush();
    assert.deepEqual(h.calls,['shot']);
    // A second result received while the shot is playing cannot cause a return trip.
    h.queue(s);h.release();await h.done();
    assert.deepEqual(h.calls,['shot','reset','enter:'+(me===0?'keeper':'shooter')]);
    h.queue(s);await h.done();assert.equal(h.calls.filter(c=>c.startsWith('enter:')).length,1);
    const next=h.snapshot('COUNTDOWN',null);next.round={id:2,shooter:1,outcome:null};
    h.queue(next);await h.done();assert.equal(h.calls.filter(c=>c.startsWith('enter:')).length,1);
    assert.equal(h.context.role,me===0?'keeper':'shooter');
});
test('a replay keeps the same view and shooter',async()=>{
    const h=harness(),s=h.snapshot('RESOLVED','replay');h.queue(s);await h.flush();h.release();await h.done();
    h.queue(s);await h.done();assert.deepEqual(h.calls,['shot']);
});
test('the final penalty goes straight to the outro, not the other end',async()=>{
    const h=harness();h.queue(h.snapshot('FINISHED'));await h.flush();h.release();await h.done();
    assert.deepEqual(h.calls,['shot','finish']);
});
