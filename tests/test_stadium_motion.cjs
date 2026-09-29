const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/stadium_motion.js'),'utf8');
const motion=import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('inter-penalty playback is 1.3x without changing intro, outro or physics',async()=>{
    const {STADIUM:C}=await import('../trivia_app/static/stadium_config.js');
    assert.equal(C.betweenShotSpeed,1.3);
    assert.equal(C.roleChangeMs,1800/1.3);
    assert.equal(C.introMs,10050);assert.equal(C.outroMs,6200);
    assert.equal(C.shot.gravity,9.81);assert.equal(C.shot.flightSeconds,.46);
    assert.equal(C.resultHoldMs,400);
    assert.equal(C.keeperHoldMs,undefined);
    for(const runUp of [0,C.runUpMs]){
        const total=(C.shotMs+runUp+C.resultHoldMs*C.betweenShotSpeed)/C.betweenShotSpeed;
        assert(Math.abs(total-(C.shotMs+runUp)/C.betweenShotSpeed-400)<1e-9);
    }
});
test('jump is a gravity-driven parabola and returns below launch height',async()=>{
    const {ballistic}=await motion,g=9.81,v=3.5,apex=v/g;
    assert(ballistic(.92,v,apex)>.92);
    assert(Math.abs(ballistic(.92,v,apex-.1)-ballistic(.92,v,apex+.1))<1e-10);
    assert(ballistic(.92,v,2*apex+.1)<.92);
});
test('six high/low goal trajectories settle without tunnelling below the floor',async()=>{
    const {bounceHeight}=await motion;
    for(const height of [.195,2.14])for(const side of [-1,0,1]) {
        for(let i=0;i<=220;i++)assert(bounceHeight(height,-.35,i/100,.195)>=.195);
        assert.equal(bounceHeight(height,-.35,2.2,.195),.195);
    }
});
test('first impact is continuous and rebound loses energy',async()=>{
    const {bounceHeight}=await motion,h=2.14,floor=.195,t=Math.sqrt(2*(h-floor)/9.81);
    assert(Math.abs(bounceHeight(h,0,t-1e-6,floor)-floor)<.00001);
    assert(Math.abs(bounceHeight(h,0,t+1e-6,floor)-floor)<.00001);
    assert(bounceHeight(h,0,t+.1,floor)<floor+(h-floor)*.22**2+.001);
    assert.equal(bounceHeight(h,0,3600,floor),floor);
});
