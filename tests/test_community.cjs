const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/community.js'),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup(view='leaderboard') {
  const nodes=new Map(),requests=[],metric={value:'wins'},board={value:'players'};
  const element=tag=>({tag,children:[],style:{},hidden:false,handlers:{},textContent:'',append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},setAttribute(k,v){this[k]=v;},addEventListener(k,fn){this.handlers[k]=fn;}});
  const get=id=>{if(!nodes.has(id))nodes.set(id,element('div'));return nodes.get(id);};
  vm.runInNewContext(source,{document:{getElementById:get,createElement:element,
    querySelector:s=>s==='.community-page'?{dataset:{view}}:s.includes('metric')?metric:s.includes('board')?board:null,
    querySelectorAll:s=>s.includes('metric')?[get('xp'),get('streak'),get('level'),get('wins'),get('win_rate'),get('daily_highscore')]:s.includes('board')?[get('players'),get('teams')]:[]},
    AbortController,Date,encodeURIComponent,URLSearchParams,location:{search:''},
    PointsUI:{badge:club=>club?.team_id&&club?.name?.trim()?Object.assign(element('img'),{alt:club.name}):null},
    fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
  return {get,requests,metric,board};
}
const player={rank:1,username:'<script>player</script>',accent:'blue',level:2,xp:100,total_xp:220};
const board={entries:[player],me:player,participants:1,signed_in:true,period:'all',since:null,as_of:'2026-09-22T12:00:00Z',distribution:[{minimum:100,label:'100-249',count:1}]};
const reply=(r,data,status=200)=>r.resolve({ok:status<400,status,json:async()=>data});
test('ranks, profile links and distribution use server data as text',async()=>{
  const s=setup();reply(s.requests[0],board);await flush();
  const row=s.get('ranking-rows').children[0];assert.equal(row.className,'own-rank');
  const name=row.children[1].children[0];assert.equal(name.textContent,player.username);assert.equal(name.href,'/u/%3Cscript%3Eplayer%3C%2Fscript%3E');
  assert.equal(row.children[1].children.some(n=>n.className?.includes('avatar')),false);
  assert.equal(s.get('participant-count').textContent,'1 player');
  assert.equal(s.get('distribution-bars').children[0].children[1].style.height,'100%');
});
test('rapid metric changes abort stale requests and keep all-time rankings',async()=>{
  const s=setup();s.metric.value='xp';s.get('xp').handlers.change();
  assert(s.requests[0].options.signal.aborted);assert.match(s.requests[1].url,/period=all/);
  reply(s.requests[1],{...board,period:'all',since:null});await flush();
  reply(s.requests[0],{...board,entries:[]});await flush();
  assert.equal(s.get('ranking-rows').children.length,1);assert.match(s.get('ranking-period').textContent,/All time/);
});
test('player cell contains only username and an optional nonempty team',async()=>{
  for(const club of [undefined,null,{name:''},{name:'   '},{name:'Manchester United',team_id:33}]){
    const s=setup();reply(s.requests[0],{...board,entries:[{...player,club,wins:12,losses:8}]});await flush();
    const contents=s.get('ranking-rows').children[0].children[1].children;
    assert.deepEqual(contents.map(n=>n.tag==='img'?n.alt:n.textContent),club?.name?.trim()?[player.username,club.name]:[player.username]);
  }
});
test('failed request provides a usable retry and empty ranks never invent players',async()=>{
  const s=setup();reply(s.requests[0],{},503);await flush();assert.equal(s.get('community-retry').hidden,false);
  s.get('community-retry').handlers.click();reply(s.requests[1],{...board,entries:[],me:null,participants:0,signed_in:false,distribution:[]});await flush();
  assert.equal(s.get('ranking-table').hidden,true);
  assert.equal(s.get('ranking-self').children.filter(e=>e.tag==='a').length,0);
  assert.match(s.get('community-status').textContent,/No scores/);
});
test('history is private and requests authentication on an expired session',async()=>{
  const s=setup('history');reply(s.requests[0],{},401);await flush();
  assert.equal(s.get('history-list').children.length,0);assert.match(s.get('community-status').textContent,/Sign in/);
});
test('history rows link to owner-authorized run details and paginate',async()=>{
  const s=setup('history');reply(s.requests[0],{items:[{run_id:'abc',phase:'ABANDONED',finished_at:1789980000000,difficulty:'easy',correct:3,questions:10,xp:30,category:{label:'All clubs',topic_label:'Goals'}}],has_more:true});await flush();
  assert.equal(s.get('history-list').children[0].href,'/penalties?run=abc');
  assert.equal(s.get('community-pagination').hidden,false);
  s.get('next-page').handlers.click();assert.match(s.requests[1].url,/offset=20/);
});

test('ranking tabs request the selected metric and display its value',async()=>{
  const s=setup();s.metric.value='win_rate';s.get('win_rate').handlers.change();
  assert.match(s.requests.at(-1).url,/metric=win_rate/);
  reply(s.requests.at(-1),{...board,metric:'win_rate',entries:[{...player,wins:12,losses:8,win_rate:60,club:{name:'Manchester United',team_id:33}}]});await flush();
  const row=s.get('ranking-rows').children[0];assert.equal(row.children.length,3);assert.equal(row.children[2].textContent,'60.0%');
  assert.equal(row.children[1].children[1].alt,'Manchester United');
  s.metric.value='level';s.get('level').handlers.change();assert.match(s.requests.at(-1).url,/period=all&metric=level/);
});

test('team ranking uses returned totals and badges, never averages them again',async()=>{
  const s=setup();s.board.value='teams';s.get('teams').handlers.change();
  assert.match(s.requests.at(-1).url,/board=teams/);
  const team={rank:1,team_id:33,name:'Manchester United',members:3,xp:1000,wins:4,win_rate:62.5,streak:5,level:6};
  reply(s.requests.at(-1),{...board,board:'teams',metric:'win_rate',entries:[team],me:team});await flush();
  const row=s.get('ranking-rows').children[0];
  assert.equal(row.className,'own-rank');assert.equal(row.children[2].textContent,'62.5%');
  assert.equal(row.children[1].children[0].tag,'span');assert.equal(row.children[1].children[1].alt,team.name);
  assert.equal(s.get('rank-name').textContent,'Team');assert.equal(s.get('team-ranking-note').hidden,false);
  assert.equal(s.get('participant-count').textContent,'1 team');
});

test('player levels use server values and survive board changes',async()=>{
  const s=setup();s.metric.value='level';s.get('level').handlers.change();
  assert.match(s.requests.at(-1).url,/period=all&metric=level&board=players/);
  reply(s.requests.at(-1),{...board,board:'players',metric:'level',period:'all',since:null});await flush();
  assert.equal(s.get('rank-value').textContent,'Levels');
  assert.equal(s.get('ranking-rows').children[0].children[2].textContent,'2');
  assert.equal(s.get('ranking-self').children[1].textContent,'2 Levels');
  s.board.value='teams';s.get('teams').handlers.change();
  assert.match(s.requests.at(-1).url,/period=all&metric=level&board=teams/);
  s.board.value='players';s.get('players').handlers.change();
  assert.match(s.requests.at(-1).url,/period=all&metric=level&board=players/);
  s.metric.value='xp';s.get('xp').handlers.change();
  assert.match(s.requests.at(-1).url,/period=all&metric=xp/);
});

test('current streak stays all-time and shows its current-day meaning',async()=>{
  const s=setup();s.metric.value='streak';s.get('streak').handlers.change();
  assert.match(s.requests.at(-1).url,/period=all&metric=streak/);
  reply(s.requests.at(-1),{...board,metric:'streak',period:'all',since:null,entries:[{...player,streak:7}]});await flush();
  assert.equal(s.get('ranking-rows').children[0].children[2].textContent,'7');
  assert.equal(s.get('ranking-period').textContent,'Current streak in days');
});

test('every player and team metric always requests all time and 25 rows',()=>{
  const s=setup();
  for(const name of ['players','teams']){
    s.board.value=name;s.get(name).handlers.change();
    for(const name of ['xp','streak','wins','win_rate','level','daily_highscore']){
      s.metric.value=name;s.get(name).handlers.change();
      assert.match(s.requests.at(-1).url,/period=all&metric=/);
      assert.match(s.requests.at(-1).url,/offset=0&limit=25$/);
    }
  }
});

const entries=(start,count)=>Array.from({length:count},(_,i)=>({...player,rank:start+i+1,username:'player_'+(start+i+1)}));
test('ranges are always visible and next pages exist only above each 25-player boundary',async()=>{
  for(const total of [0,1,25,26,50,51]){
    const s=setup();
    for(let offset=0;offset<Math.max(1,total);offset+=25){
      const count=Math.min(25,total-offset);
      assert.match(s.requests.at(-1).url,new RegExp(`offset=${offset}&limit=25$`));
      reply(s.requests.at(-1),{...board,participants:total,entries:entries(offset,count)});await flush();
      assert.equal(s.get('ranking-rows').children.length,count);
      assert.equal(s.get('community-pagination').hidden,false);
      assert.equal(s.get('page-number').textContent,`${count?offset+1:0} - ${offset+count} of ${total}`);
      assert.equal(s.get('previous-page').disabled,offset===0);
      assert.equal(s.get('next-page').disabled,offset+25>=total);
      const before=s.requests.length;s.get('next-page').handlers.click();
      assert.equal(s.requests.length,before+(offset+25<total?1:0));
      if(offset+25<total){s.get('next-page').handlers.click();assert.equal(s.requests.length,before+1);}
    }
    if(total>25){s.get('previous-page').handlers.click();assert.match(s.requests.at(-1).url,new RegExp(`offset=${Math.floor((total-1)/25)*25-25}&limit=25$`));}
  }
});

test('changing boards or metrics resets to the first page',async()=>{
  const s=setup();
  for(const kind of ['metric','board']){
    reply(s.requests.at(-1),{...board,participants:50,entries:entries(0,25)});await flush();
    s.get('next-page').handlers.click();reply(s.requests.at(-1),{...board,participants:50,entries:entries(25,25)});await flush();
    if(kind==='metric'){s.metric.value='xp';s.get('xp').handlers.change();}
    else{s.board.value='teams';s.get('teams').handlers.change();}
    assert.match(s.requests.at(-1).url,/offset=0&limit=25$/);
  }
});

test('a shrinking leaderboard returns to its last existing page',async()=>{
  const s=setup();reply(s.requests[0],{...board,participants:26,entries:entries(0,25)});await flush();
  s.get('next-page').handlers.click();reply(s.requests.at(-1),{...board,participants:12,entries:[]});await flush();
  assert.match(s.requests.at(-1).url,/offset=0&limit=25$/);
  reply(s.requests.at(-1),{...board,participants:12,entries:entries(0,12)});await flush();
  assert.equal(s.get('page-number').textContent,'1 - 12 of 12');assert.equal(s.get('next-page').disabled,true);
});
