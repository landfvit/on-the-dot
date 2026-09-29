const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../trivia_app/static/friends.js'),'utf8');
const code=source.slice(source.indexOf('  function roundDecision(s){'),source.indexOf('  function showDecision('));
const ctx=vm.createContext({playerName:(s,i)=>s.players[i].is_guest?(i===s.me?'You':'Friend'):s.players[i].name});
vm.runInContext(code,ctx);
function snapshot({me=0,shooter=0,outcome='goal',answers=[{correct:true,elapsed_ms:2200},{correct:true,elapsed_ms:3000}],guest=false}={}){
    return {me,round:{shooter,outcome,answers},rules:{tie_ms:150},players:[{name:'Alex',is_guest:guest},{name:'Sam',is_guest:guest}]};
}
test('no result before server resolution (even if client knows the answers)',()=>{
    assert.equal(ctx.roundDecision(snapshot({outcome:null})),null);
    const s=snapshot();delete s.round.answers;assert.equal(ctx.roundDecision(s),null);
});
for(const me of [0,1])for(const shooter of [0,1])for(const outcome of ['goal','save'])test(`speed decision from seat ${me}, shooter ${shooter}, ${outcome}`,()=>{
    const winner=outcome==='goal'?shooter:1-shooter,answers=[{correct:true,elapsed_ms:3000},{correct:true,elapsed_ms:3000}];answers[winner].elapsed_ms=2200;
    const s=snapshot({me,shooter,outcome,answers}),r=ctx.roundDecision(s);
    assert.equal(r.rows.find(a=>a.winner).time,'2.20 s');
    assert.equal(r.rows.find(a=>!a.winner).time,'3.00 s');
    assert.equal(r.rows[0].name,s.players[me].name);assert(r.rows.every(a=>a.status==='Correct'));
    assert.equal(r.rows.find(a=>a.winner).name,s.players[winner].name);
});
test('a close tie is explicitly a retake, not a win',()=>{
    const s=snapshot({outcome:'replay',answers:[{correct:true,elapsed_ms:2200},{correct:true,elapsed_ms:2349}]}),r=ctx.roundDecision(s);
    assert(r.rows.every(a=>!a.winner));assert.equal(r.outcome,'replay');
    assert.equal(r.rows[1].time,'2.349 s','Do not round a 149 ms tie into an apparent 150 ms win');
});
test('both wrong or both timed out never highlight a winner',()=>{
    for(const answers of [[null,null],[{correct:false,elapsed_ms:2500},{correct:false,elapsed_ms:2700}]]){
        const r=ctx.roundDecision(snapshot({outcome:'replay',answers}));
        assert(r.rows.every(a=>!a.winner));assert.equal(r.outcome,'replay');
    }
});
test('correct keeper versus timeout does not claim a speed win',()=>{
    const r=ctx.roundDecision(snapshot({outcome:'save',answers:[null,{correct:true,elapsed_ms:1500}]}));
    assert.equal(r.rows[1].winner,true);assert.equal(r.rows[0].status,'Time out');assert.equal(r.rows[0].time,null);
});
test('guests keep You / Friend names and winner is authoritative',()=>{
    const r=ctx.roundDecision(snapshot({guest:true}));assert.equal(r.rows[0].name,'You');assert.equal(r.rows[0].winner,true);
    assert.equal(r.rows[1].name,'Friend');
});
