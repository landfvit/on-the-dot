const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/penalty_scene.js'),'utf8');
function bridge(available=true) {
    const calls=[];
    const window={PointsStadium:available?{reset:()=>calls.push(['reset']),shot:(...args)=>calls.push(['shot',...args])}:undefined};
    // Zadne DOM ani WebAnimation API: vyrenderovani 2D neni mozne.
    vm.runInNewContext(script,{window,PenaltyShots:require('../trivia_app/static/penalty_shots.js')});
    return {api:window.PenaltyScene,calls};
}
for(const outcome of ['goal','save','miss','replay'])test(outcome+' forwards only the server result and seeded 3D plan',()=>{
    const b=bridge();b.api.shot(outcome,'round:5');
    assert.equal(b.calls[0][0],'reset');assert.equal(b.calls[1][0],'shot');
    assert.equal(b.calls[1][1],outcome);assert.equal(b.calls[1][2].outcome,outcome);
});
test('same round retains the same plan for both clients',()=>{
    const a=bridge(),b=bridge();a.api.shot('goal','room:3');b.api.shot('goal','room:3');
    assert.deepEqual(a.calls,b.calls);
});
test('invalid outcome never starts an animation',()=>{
    const b=bridge();b.api.shot('unknown');assert.deepEqual(b.calls,[]);
});
test('reset forwards to 3D without consulting old SVG nodes',()=>{
    const b=bridge();b.api.reset();assert.deepEqual(b.calls,[['reset']]);
});
test('missing 3D cannot enable a 2D fallback or throw',()=>{
    const b=bridge(false);assert.doesNotThrow(()=>{b.api.shot('goal');b.api.reset();});
});
