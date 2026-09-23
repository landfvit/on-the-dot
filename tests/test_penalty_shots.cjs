const test=require('node:test');
const assert=require('node:assert/strict');
const {plan,zones}=require('../trivia_app/static/penalty_shots.js');

test('six unique zones include both heights at all three horizontal positions',()=>{
    assert.equal(new Set(zones.map(z=>z.id)).size,6);
    for(const side of [-1,0,1])for(const high of [false,true])assert(zones.some(z=>z.side===side&&z.high===high));
    assert(Object.isFrozen(zones));assert(zones.every(Object.isFrozen));
});
for(const zone of zones) {
    test(`goal ${zone.id}: keeper chooses the opposite side`,()=>{
        const p=plan('goal',undefined,()=>zones.indexOf(zone)/6);
        assert.deepEqual(p.target,zone);assert.notEqual(p.keeper.side,zone.side);
        if(zone.side)assert.equal(p.keeper.side,-zone.side);
    });
    test(`save ${zone.id}: hands target exactly the ball's zone`,()=>{
        const p=plan('save',undefined,()=>zones.indexOf(zone)/6);
        assert.deepEqual(p.target,zone);assert.deepEqual(p.keeper,p.target);
    });
}
test('1000 seeded rounds: all goals differ from keeper, all saves match, both clients agree',()=>{
    const counts=Object.fromEntries(zones.map(z=>[z.id,0]));
    for(let round=0;round<1000;round++)for(const outcome of ['goal','save']) {
        const key=`room-qa:${round}`,a=plan(outcome,key),b=plan(outcome,key);
        assert.deepEqual(a,b);
        if(outcome==='goal'){assert.notEqual(a.target.side,a.keeper.side);counts[a.target.id]++;}
        else assert.deepEqual(a.target,a.keeper);
    }
    // Large tolerance avoids a brittle statistical test, but catches fixed/cyclic sides.
    for(const count of Object.values(counts))assert(count>100&&count<240);
});
test('different round keys do not always pick the same direction',()=>{
    assert(new Set(Array.from({length:100},(_,i)=>plan('goal',`solo:${i}`).target.id)).size===6);
});
test('invalid results never invent a shot; miss and replay retain their result',()=>{
    assert.equal(plan('unknown'),null);
    for(const outcome of ['miss','replay'])assert.equal(plan(outcome,'round').outcome,outcome);
});
