const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../trivia_app/static/game_exit.js'),'utf8');
const key='points.pending-game-exits.v1',solo='/api/solo/runs/run-1/leave';
function setup({stored=new Map(),beacon=true,status=200,blocked=false}={}){
  const handlers={},beacons=[],requests=[];let reloads=0,exits=0;
  const scope={window:{addEventListener:(name,fn)=>handlers[name]=fn},
    navigator:{sendBeacon(url){beacons.push(url);if(beacon instanceof Error)throw beacon;return beacon;}},
    localStorage:{getItem(k){if(blocked)throw Error();return stored.get(k);},setItem(k,v){if(blocked)throw Error();stored.set(k,v);},removeItem(k){if(blocked)throw Error();stored.delete(k);}},
    location:{reload(){reloads++;}},
    fetch:async(url,options)=>{requests.push({url,options});if(status instanceof Error)throw status;return {ok:status<400,status};}};
  vm.runInNewContext(source,scope);
  const exit=scope.PointsGameExit.bind(()=>exits++);
  return {exit,handlers,beacons,requests,stored,get reloads(){return reloads;},get exits(){return exits;}};
}
for(const route of [solo,'/api/daily/runs/run-2/leave','/api/friends/rooms/invite_3/leave']){
  test('page exit sends an authenticated leave for '+route,()=>{
    const s=setup();s.exit.watch(route);s.handlers.pagehide({persisted:false});s.handlers.pagehide({});
    assert.deepEqual(s.beacons,[route]);assert.equal(s.exits,1);assert.equal(s.exit.closed,true);
    assert.deepEqual(JSON.parse(s.stored.get(key)),[route]);
    assert.equal(s.handlers.visibilitychange,undefined);
  });
}
test('completed games and selection pages never forfeit',()=>{
  const s=setup();s.exit.watch(solo);s.exit.watch(null);s.handlers.pagehide({});
  assert.equal(s.beacons.length,0);assert.equal(s.stored.has(key),false);
});
for(const beacon of [false,new Error('Unsupported')])test('keepalive fallback survives rejected beacon',async()=>{
  const s=setup({beacon});s.exit.watch(solo);s.handlers.pagehide({});await new Promise(setImmediate);
  assert.equal(s.requests[0].url,solo);assert.equal(s.requests[0].options.method,'POST');
  assert.equal(s.requests[0].options.keepalive,true);assert.equal(s.requests[0].options.credentials,'same-origin');
  assert.equal(s.stored.has(key),false);
});
test('next visit confirms queued exits before resuming a game',async()=>{
  const first=setup();first.exit.watch(solo);first.handlers.pagehide({});
  const next=setup({stored:first.stored});await next.exit.flush();
  assert.deepEqual(next.requests.map(r=>r.url),[solo]);assert.equal(next.stored.has(key),false);
});
test('closing without any browser event cannot auto-resume on the next visit',async()=>{
  const first=setup();first.exit.watch(solo);
  assert.deepEqual(JSON.parse(first.stored.get(key)),[solo]);
  const next=setup({stored:first.stored});await next.exit.flush();
  assert.deepEqual(next.requests.map(r=>r.url),[solo]);assert.equal(next.stored.has(key),false);
});
test('network failure preserves the outbox and prevents resuming',async()=>{
  const s=setup({stored:new Map([[key,JSON.stringify([solo])]]),status:new Error('Offline')});
  await assert.rejects(s.exit.flush(),/Reload to retry/);
  assert.deepEqual(JSON.parse(s.stored.get(key)),[solo]);
});
for(const status of [401,403,404,410])test('stale or inaccessible games are discarded '+status,async()=>{
  const s=setup({stored:new Map([[key,JSON.stringify([solo])]]),status});await s.exit.flush();assert.equal(s.stored.has(key),false);
});
test('untrusted local storage cannot turn exit retry into an arbitrary request',async()=>{
  const s=setup({stored:new Map([[key,JSON.stringify(['https://evil.test', '/api/players/logout','/api/solo/runs/../delete',solo])]])});
  await s.exit.flush();assert.deepEqual(s.requests.map(r=>r.url),[solo]);
});
test('Back and Forward cache reloads instead of reviving the question',()=>{
  const s=setup();s.exit.watch(solo);s.handlers.pageshow({persisted:false});assert.equal(s.reloads,0);
  s.handlers.pagehide({persisted:true});s.handlers.pageshow({persisted:true});assert.equal(s.reloads,1);
});
test('a late start response is also forfeited and duplicate responses are harmless',()=>{
  const s=setup();s.handlers.pagehide({});s.exit.watch(solo);s.exit.watch(solo);
  assert.deepEqual(s.beacons,[solo]);
});
test('blocked storage still sends the leave beacon',()=>{
  const s=setup({blocked:true});s.exit.watch(solo);s.handlers.pagehide({});assert.deepEqual(s.beacons,[solo]);
});
