const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/solo.js'),'utf8');
const shareScript=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/result_share.js'),'utf8');

function setup(pageType='solo',withScene=false,stadium=undefined){
  const nodes=new Map(),requests=[],timers=[],stored=new Map(),shots=[],copied=[],sounds=[],radio={value:pageType==='account'?'login':'easy'};
  function element(tag='div'){
    let value='';const classes=new Set();
    return {tag,children:[],handlers:{},dataset:{},disabled:false,hidden:false,textContent:'',
      get value(){return value||(tag==='select'?this.children[0]?.value||'':'');},set value(v){value=v;},
      classList:{toggle(c,on){if(on)classes.add(c);else classes.delete(c);},contains(c){return classes.has(c);}},
      append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
      addEventListener(name,fn){this.handlers[name]=fn;},emit(name){return this.handlers[name]?.({preventDefault(){},target:this});},focus(){},
      querySelector(){return get('save');},
      setAttribute(name,value){this[name]=value;},
      removeAttribute(name){delete this[name];},select(){},showModal(){this.open=true;},close(){this.open=false;},
    };
  }
  const get=id=>{if(!nodes.has(id))nodes.set(id,element(['category','topic'].includes(id)?'select':'div'));return nodes.get(id);};
  const page=element();page.dataset.page=pageType;
  const document={getElementById:get,createElement:element,querySelector:s=>s==='.solo-page'?page:radio,
    querySelectorAll:s=>s.includes('auth-mode')?[get('login-mode'),get('register-mode')]:[get('easy'),get('medium'),get('hard')]};
  const location={href:'http://localhost/penalties',origin:'http://localhost',pathname:'/penalties'};
  vm.runInNewContext(shareScript+'\n'+script,{document,location,console,Date,encodeURIComponent,URLSearchParams,navigator:{clipboard:{writeText:async text=>copied.push(text)}},
    PenaltyScene:withScene?{shot:outcome=>shots.push(outcome),reset(){}}:undefined,
    PointsStadium:stadium,
    PointsAudio:{play:name=>sounds.push(name)},
    history:{replaceState(_state,_title,path){location.href=location.origin+path;location.search='';}},
    crypto:{randomUUID:()=>`request-${requests.length}`},setInterval(fn,ms){timers.push({fn,ms});},
    localStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},
    fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}));}});
  return {get,requests,radio,stored,timers,location,shots,copied,sounds};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function reply(r,data,status=200){
  if(data.categories&&!data.topics)data={...data,topics:[{code:'ALL',label:'Mixed topics',counts_by_team:Object.fromEntries(data.categories.map(c=>[c.code,c.counts]))}]};
  r.resolve({ok:status<400,status,json:async()=>data});
}
const user={username:'tester',level:1,total_xp:0};
const catalog={categories:[{code:'ALL',label:'All clubs',counts:{easy:10,medium:10,hard:10}},{code:'GEN',label:'General',counts:{easy:0,medium:10,hard:10}}],rules:{xp_by_difficulty:{easy:10,medium:20,hard:30},perfect_multipliers:{easy:1,medium:2,hard:3}}};
function run(overrides={}){return {run_id:'r1',server_now:Date.now(),phase:'READY',position:0,category:{label:'All clubs'},difficulty:'easy',rules:{xp_per_correct:10,questions:10},review:[],question:null,total_xp:0,base_xp:0,bonus_xp:0,multiplier:1,correct:0,is_trial:false,...overrides};}
async function boot(s,authenticated=true,active=null){
  reply(s.requests[0],authenticated?user:{detail:'Sign in'},authenticated?200:401);await flush();
  reply(s.requests[1],catalog);await flush();
  reply(s.requests[2],{run:active,trial_available:!active});await flush();
}

test('stadium intro holds first Next without starting the question clock',async()=>{
  let finish;const calls=[];
  const stadium={enter:(role,options)=>{calls.push({role,options});return new Promise(resolve=>{finish=resolve;});},leave(){},skip(){}};
  const s=setup('solo',true,stadium);await boot(s,true,run());
  assert.equal(calls.length,1);assert.equal(calls[0].role,'shooter');assert.equal(calls[0].options.intro,true);
  assert.equal(s.get('next').disabled,true);
  s.get('next').emit('click');assert.equal(s.requests.length,3);
  finish();await flush();assert.equal(s.get('next').disabled,false);
  s.get('next').emit('click');assert.equal(s.requests.at(-1).url,'/api/solo/runs/r1/next');
});
test('resumed live question skips travel and retains server deadline',async()=>{
  const calls=[];const stadium={enter:(role,options)=>{calls.push(options);return Promise.resolve();},leave(){},skip(){}};
  const s=setup('solo',true,stadium);
  await boot(s,true,run({phase:'ANSWERING',position:1,deadline:Date.now()+15000,question:{text:'Question?',options:[{id:'a',text:'A'}]}}));
  assert.equal(calls[0].intro,false);assert.equal(calls[0].maxDurationMs,0);assert.equal(s.get('choices').children[0].disabled,false);
});

test('solo catalog prevents unsupported difficulty from starting',async()=>{
  const s=setup();reply(s.requests[0],user);await flush();
  reply(s.requests[1],{...catalog,categories:[{code:'ALL',counts:{easy:0,medium:10,hard:10}}]});await flush();
  reply(s.requests[2],{run:null});await flush();assert.equal(s.get('start').disabled,true);
  assert.match(s.get('availability').textContent,/No new shootout/);
  const count=s.requests.length;s.get('quiz-start').emit('submit');await flush();assert.equal(s.requests.length,count);
  s.radio.value='medium';s.get('medium').emit('change');assert.equal(s.get('start').disabled,false);
});
test('quiz instructions use the server answer duration',async()=>{
  const s=setup();
  reply(s.requests[0],user);await flush();
  reply(s.requests[1],{...catalog,rules:{...catalog.rules,questions:10,answer_ms:15000}});await flush();
  reply(s.requests[2],{run:null});await flush();
  assert.match(s.get('quiz-rules').textContent,/10 questions · 15 seconds each/);
});
test('timer bar follows the frozen duration for new and legacy runs',async()=>{
  for(const answer_ms of [15000,10000]){
    const s=setup();
    await boot(s,true,run({phase:'ANSWERING',position:1,deadline:Date.now()+answer_ms,
      rules:{answer_ms,xp_per_correct:10},question:{text:'Question?',options:[{id:'0',text:'A'}]}}));
    s.timers.find(t=>t.ms===100).fn();
    assert.equal(s.get('timer').max,answer_ms/1000);
    assert.ok(s.get('timer').value<=answer_ms/1000);
  }
});
test('penalty animation follows server review once and never sends score or XP',async()=>{
  const s=setup('solo',true);
  await boot(s,true,run({phase:'ANSWERING',position:1,deadline:Date.now()+10000,question:{text:'Question?',options:[{id:'0',text:'A'},{id:'1',text:'B'}]}}));
  assert.equal(s.get('solo-attempts').children.length,10);assert.equal(s.shots.length,0);
  const submitting=s.get('choices').children[0].emit('click');await flush();
  const result=run({phase:'REVIEW',position:1,correct:1,total_xp:10,question:{text:'Question?',options:[{id:'0',text:'A'},{id:'1',text:'B'}]},review:[{position:1,option_id:'0',correct:'0',is_correct:true,authority:'user_attested',explanation:'A'}]});
  reply(s.requests[3],result);await submitting;
  assert.deepEqual(s.shots,['goal']);assert.equal(s.get('penalty-score').textContent,'1 / 10');
  assert.equal(s.get('feedback').textContent,'Correct. +10 XP. A');
  assert.doesNotMatch(s.get('feedback').textContent,/database|author|source/i);
  const retry=s.get('retry').emit('click');await flush();reply(s.requests[4],result);await retry;await flush();
  assert.deepEqual(s.shots,['goal']);
  assert.deepEqual(Object.keys(JSON.parse(s.requests[3].options.body)),['position','option_id','request_id']);
});
test('timeout is a miss and wrong answer is a save',async()=>{
  for(const [option,outcome] of [[null,'miss'],['1','save']]){
    const s=setup('solo',true);
    await boot(s,true,run({phase:'REVIEW',position:1,review:[{position:1,option_id:option,is_correct:false,explanation:'A'}]}));
    assert.deepEqual(s.shots,[outcome]);assert.equal(s.get('penalty-score').textContent,'0 / 10');
  }
});
test('anonymous players can start a guest game without a registration redirect',async()=>{
  const s=setup();await boot(s,false);assert.equal(s.get('start').textContent,'Play as guest');
  const starting=s.get('quiz-start').emit('submit');await flush();assert.equal(s.requests[3].url,'/api/solo/runs');
  reply(s.requests[3],run({is_trial:true}));await starting;
  assert.equal(s.location.href,'http://localhost/penalties');assert.equal(s.get('quiz-run').hidden,false);
});
test('starting while another tab has an active quiz resumes with usable controls',async()=>{
  const s=setup();await boot(s);const starting=s.get('quiz-start').emit('submit');await flush();
  reply(s.requests[3],run({phase:'ANSWERING',position:1,deadline:Date.now()+10000,question:{text:'Question?',options:[{id:'0',text:'A'}]}}));await starting;
  assert.equal(s.get('choices').children[0].disabled,false);
});
test('resuming a quiz preserves the server deadline and hides unknown answers',async()=>{
  const s=setup(),deadline=Date.now()+10000;
  await boot(s,true,run({phase:'ANSWERING',position:1,deadline,question:{text:'A question?',options:[{id:'0',text:'A'},{id:'1',text:'B'}]}}));
  assert.equal(s.get('question-title').textContent,'A question?');assert.equal(s.get('choices').children.length,2);
  assert(s.get('choices').children.every(b=>!b.disabled&&!b.classList.contains('correct')));
  assert.equal(s.stored.get('points.solo.tester'),'r1');
  s.timers.find(t=>t.ms===100).fn();assert(s.get('timer').value<=10);
});
test('answer retries reuse the request and cannot send a client XP total',async()=>{
  const s=setup();await boot(s,true,run({phase:'ANSWERING',position:1,deadline:Date.now()+10000,question:{text:'Question?',options:[{id:'0',text:'A'},{id:'1',text:'B'}]}}));
  const sending=s.get('choices').children[0].emit('click');await flush();
  const first=JSON.parse(s.requests[3].options.body);assert.deepEqual(Object.keys(first),['position','option_id','request_id']);
  reply(s.requests[3],{detail:'Temporary error'},503);await flush();
  reply(s.requests[4],run({phase:'ANSWERING',position:1,deadline:Date.now()+10000,question:{text:'Question?',options:[{id:'0',text:'A'},{id:'1',text:'B'}]}}));await sending;
  s.get('choices').children[1].emit('click');await flush();
  assert.deepEqual(JSON.parse(s.requests[5].options.body),first);
});
test('completed quiz displays server-calculated rewards and streak outcome',async()=>{
  const s=setup();await boot(s,true,run({phase:'FINISHED',position:10,perfect:true,streak_eligible:true,total_xp:900,base_xp:300,bonus_xp:600,multiplier:3,correct:10}));
  assert.equal(s.get('result-heading').textContent,'Perfect shootout!');
  assert.deepEqual(s.get('result-metrics').children.map(n=>n.children[0].textContent),['10 / 10','900','600','3x']);
  assert.equal(s.get('leave').hidden,true);
});
test('timeout results do not promise a daily streak',async()=>{
  const s=setup();await boot(s,true,run({phase:'FINISHED',position:10,streak_eligible:false,total_xp:90,base_xp:90}));
  assert.doesNotMatch(s.get('result-completion').textContent,/streak/i);
});
test('review retains explanations but never renders source or authority labels',async()=>{
  const s=setup();
  await boot(s,true,run({phase:'FINISHED',position:1,review:[{
    position:1,text:'Who won?',option_id:'a',correct:'a',is_correct:true,
    explanation:'United finished first with 80 points.',authority:'user_attested',
    source:{references:['https://example.com/private-source']},
  }]}));
  const item=s.get('review').children[0];
  assert.deepEqual(item.children.map(n=>n.tag),['h3','p']);
  assert.equal(item.children[1].textContent,'Correct · United finished first with 80 points.');
  assert.doesNotMatch(s.get('feedback').textContent,/source|author|database|https:/i);
});
test('result review paginates server answers and closes before a new shootout',async()=>{
  const s=setup();await boot(s,true,run({phase:'FINISHED',review:[
    {text:'First question?',option_id:null,explanation:'First explanation.'},
    {text:'Second question?',option_id:'a',is_correct:true,explanation:'Second explanation.'},
  ]}));
  s.get('result-review').emit('click');
  assert.equal(s.get('review-dialog').open,true);
  assert.equal(s.get('review-previous').disabled,true);
  s.get('review-next').emit('click');
  assert.equal(s.get('review').children.length,1);
  assert.equal(s.get('review').children[0].children[0].textContent,'Second question?');
  assert.equal(s.get('review-position').textContent,'2 / 2');
  assert.equal(s.get('review-next').disabled,true);
  s.get('review-previous').emit('click');assert.equal(s.get('review-position').textContent,'1 / 2');
  const restarting=s.get('another').emit('click');await flush();reply(s.requests.at(-1),catalog);await restarting;
  assert.equal(s.get('review-dialog').open,false);
});
test('empty ended game has no review navigation to invented answers',async()=>{
  const s=setup();await boot(s,true,run({phase:'ABANDONED',review:[]}));
  assert.equal(s.get('result-review').disabled,true);
  assert.equal(s.get('review').children.length,0);
  assert.equal(s.get('review-next').disabled,true);
});
test('network recovery restores answer controls without changing the deadline',async()=>{
  const s=setup(),active=run({phase:'ANSWERING',position:1,deadline:Date.now()+10000,question:{text:'Question?',options:[{id:'0',text:'A'}]}});
  await boot(s,true,active);s.timers.find(t=>t.ms===1000).fn();await flush();reply(s.requests[3],{detail:'Offline'},503);await flush();
  assert.equal(s.get('choices').children[0].disabled,true);assert.equal(s.get('retry').hidden,false);
  s.timers.find(t=>t.ms===1000).fn();await flush();reply(s.requests[4],{...active,server_now:Date.now()});await flush();
  assert.equal(s.get('choices').children[0].disabled,false);assert.equal(s.get('retry').hidden,true);
});

test('completed guest game offers registration without blocking another game',async()=>{
  const s=setup();await boot(s,false,run({phase:'FINISHED',position:10,is_trial:true,total_xp:100,base_xp:100,perfect:true}));
  assert.equal(s.get('another').textContent,'New shootout');assert.equal(s.get('guest-benefits').hidden,false);
  assert.match(s.get('result-metrics').children[1].children[1].textContent,/not saved/);
  const restarting=s.get('another').emit('click');await flush();reply(s.requests.at(-1),catalog);await restarting;
  assert.equal(s.location.href,'http://localhost/penalties');assert.equal(s.get('selection').hidden,false);
});

test('End shootout replaces the question with results and authoritative level progress',async()=>{
  const s=setup();await boot(s,true,run({phase:'REVIEW',position:2}));
  const ending=s.get('leave').emit('click');await flush();
  assert.equal(s.requests.at(-1).url,'/api/solo/runs/r1/leave');
  reply(s.requests.at(-1),run({phase:'ABANDONED',position:2,correct:1,total_xp:20,
    review:[{position:1,option_id:'0',is_correct:true,text:'One',explanation:'A'},{position:2,option_id:null,is_correct:false,text:'Two',explanation:'B'}],
    player_progress:{level:3,total_xp:270,level_xp:250,next_level_xp:500}}));
  await ending;
  assert.equal(s.get('question-panel').hidden,true);assert.equal(s.get('summary').hidden,false);
  assert.equal(s.get('quiz-run')['aria-labelledby'],'result-heading');
  assert.equal(s.get('result-completion').textContent,'1 answered · 1 timed out · 8 unplayed');
  assert.equal(s.get('result-level-remaining').textContent,'230 XP to level 4');
  assert.equal(s.get('result-level-progress').max,250);assert.equal(s.get('result-level-progress').value,20);
  assert.equal(s.get('result-metrics').children[0].children[0].textContent,'1 / 10');
});

test('maximum level and trial summaries do not invent next-level rewards',async()=>{
  const s=setup();await boot(s,true,run({phase:'FINISHED',player_progress:{level:100,total_xp:99999,level_xp:99999,next_level_xp:null}}));
  assert.equal(s.get('result-level-remaining').textContent,'Maximum level');
  const trial=setup();await boot(trial,false,run({phase:'ABANDONED',is_trial:true}));
  assert.equal(trial.get('result-level').hidden,true);
});

test('sharing publishes only on click and copies only the rich result URL',async()=>{
  const s=setup();await boot(s,true,run({phase:'FINISHED',correct:7,total_xp:70}));
  assert(!s.requests.some(r=>r.url==='/api/shares/results'));
  const click=s.get('share-result').emit('click');
  reply(s.requests.at(-1),{title:'Result',url:'https://onthedot.gg/s/token',image_url:'https://onthedot.gg/s/token/image.png'});await click;
  assert.equal(s.get('share-options').hidden,false);
  assert.equal(s.get('share-card-link').href,'https://onthedot.gg/s/token');
  await s.get('share-copy').emit('click');
  assert.equal(s.copied[0],'https://onthedot.gg/s/token');
  assert.equal(s.get('share-dialog-status').textContent,'Result link copied.');
  assert.equal(s.get('share-dialog').open,true);
});

test('returning from leaderboard never resurrects an ended game from local storage',async()=>{
  const s=setup('solo',true);s.stored.set('points.solo.tester','old-ended-run');await boot(s);
  assert.equal(s.stored.has('points.solo.tester'),false);
  assert.equal(s.requests.some(r=>r.url.includes('old-ended-run')),false);
  assert.equal(s.get('shootout-board').hidden,true);
});

test('New shootout clears the result pointer, history URL and score overlay',async()=>{
  const s=setup('solo',true);await boot(s,true,run({phase:'ABANDONED',shootout:shootout()}));
  assert.equal(s.get('shootout-board').hidden,true);
  s.location.search='?run=r1';s.stored.set('points.solo.tester','r1');
  const returning=s.get('another').emit('click');await flush();
  reply(s.requests.findLast(r=>r.url==='/api/solo/catalog'),catalog);await returning;
  assert.equal(s.stored.has('points.solo.tester'),false);
  assert.equal(s.location.search,'');assert.equal(s.get('selection').hidden,false);
  assert.equal(s.get('shootout-board').hidden,true);assert.equal(s.get('quiz-run').hidden,true);
});

test('late polling responses cannot reopen a game after New shootout',async()=>{
  const s=setup('solo',true);await boot(s,true,run({phase:'ANSWERING',position:1,shootout:shootout(),deadline:Date.now()+15000}));
  s.timers.find(t=>t.ms===1000).fn();const stale=s.requests.at(-1);
  const ending=s.get('leave').emit('click');await flush();
  reply(s.requests.at(-1),run({phase:'ABANDONED',position:1,shootout:shootout()}));await ending;
  const returning=s.get('another').emit('click');await flush();reply(s.requests.findLast(r=>r.url==='/api/solo/catalog'),catalog);await returning;
  reply(stale,run({phase:'ABANDONED',position:1,shootout:shootout()}));await flush();
  assert.equal(s.get('selection').hidden,false);assert.equal(s.get('quiz-run').hidden,true);assert.equal(s.get('shootout-board').hidden,true);
});

test('a history deep link resolves only through the authenticated run endpoint',async()=>{
  const s=setup();s.location.search='?run=previous-run';
  reply(s.requests[0],user);await flush();reply(s.requests[1],catalog);await flush();
  assert.equal(s.requests[2].url,'/api/solo/runs/previous-run');
  reply(s.requests[2],run({run_id:'previous-run',phase:'FINISHED'}));await flush();
  assert.equal(s.get('summary').hidden,false);
});

test('difficulty selection uses server rates and perfect totals',async()=>{
  const s=setup();await boot(s);s.radio.value='hard';s.get('hard').emit('change');
  assert.match(s.get('quiz-rules').textContent,/30 XP per correct answer/);
  assert.equal(s.get('medium-perfect').textContent,'10/10: 400 XP');
  assert.equal(s.get('hard-perfect').textContent,'10/10: 900 XP');
});

test('answer feedback uses the frozen rate of the actual run',async()=>{
  const s=setup();await boot(s,true,run({phase:'REVIEW',position:1,rules:{xp_per_correct:20},review:[{position:1,option_id:'0',correct:'0',is_correct:true,explanation:'Answer.'}],question:{text:'Question?',options:[{id:'0',text:'Answer'}]}}));
  assert.match(s.get('feedback').textContent,/Correct\. \+20 XP/);
});

test('registration submits email and username while login submits an identifier',async()=>{
  const s=setup('account');reply(s.requests[0],{detail:'Sign in'},401);await flush();
  assert.equal(s.get('registration-fields').hidden,true);
  s.radio.value='register';s.get('register-mode').emit('change');
  assert.equal(s.get('identifier').disabled,true);assert.equal(s.get('email').disabled,false);
  s.get('email').value='person@example.com';s.get('username').value='person';s.get('password').value='eight888';
  let submit=s.get('auth-form').emit('submit');await flush();
  assert.equal(s.requests[1].url,'/api/players/register');
  assert.deepEqual(JSON.parse(s.requests[1].options.body),{email:'person@example.com',username:'person',password:'eight888'});
  reply(s.requests[1],{detail:'Unavailable'},409);await submit;
  s.radio.value='login';s.get('login-mode').emit('change');s.get('identifier').value='person@example.com';
  submit=s.get('auth-form').emit('submit');await flush();
  assert.equal(s.requests[2].url,'/api/players/login');
  assert.deepEqual(JSON.parse(s.requests[2].options.body),{identifier:'person@example.com',password:'eight888'});
  reply(s.requests[2],{detail:'Invalid email or password'},401);await submit;
});

test('returning to selection refreshes weekly counts before enabling start',async()=>{
  const s=setup();await boot(s,true,run({phase:'ABANDONED'}));
  const returning=s.get('another').emit('click');await flush();
  assert.equal(s.get('start').disabled,true);
  const request=s.requests.findLast(r=>r.url==='/api/solo/catalog');
  reply(request,{...catalog,resets_at:'2026-09-28T00:00:00Z',categories:[{code:'ALL',label:'All clubs',counts:{easy:0,medium:10,hard:10}}]});
  await returning;
  assert.equal(s.get('start').disabled,true);
  assert.match(s.get('availability').textContent,/No new shootout/);
  assert.match(s.get('weekly-reset').textContent,/2026-09-28 at 00:00 UTC/);
  s.radio.value='medium';s.get('medium').emit('change');assert.equal(s.get('start').disabled,false);
});

test('failed availability refresh cannot reuse stale counts',async()=>{
  const s=setup();await boot(s,true,run({phase:'ABANDONED'}));
  const returning=s.get('another').emit('click');await flush();
  reply(s.requests.findLast(r=>r.url==='/api/solo/catalog'),{detail:'Offline'},503);
  await returning;assert.equal(s.get('start').disabled,true);assert.equal(s.get('error').textContent,'Offline');
  const count=s.requests.length;s.get('quiz-start').emit('submit');await flush();assert.equal(s.requests.length,count);
});

function shootout(overrides={}){
  return {player:1,opponent:0,kicks:{player:1,opponent:1},attempts:[{side:'player',goal:true,number:1},{side:'opponent',goal:false,number:1}],round:2,next_role:'shooter',winner:null,sudden_death:false,...overrides};
}
test('TV scoreboard shows goals, misses and unplayed kicks independently for both sides',async()=>{
  const s=setup('solo',true);
  await boot(s,true,run({phase:'REVIEW',position:2,role:'keeper',shootout:shootout()}));
  assert.equal(s.get('penalty-score').textContent,'1 : 0');
  assert.deepEqual(s.get('kicks-player').children.map(e=>e.className),['shootout-kick goal',...Array(4).fill('shootout-kick pending')]);
  assert.equal(s.get('kicks-opponent').children[0].className,'shootout-kick miss');
  assert.equal(s.get('kicks-opponent').children[0]['aria-label'],'Opponent, penalty 1: missed');
});
test('keeper answer uses server save outcome and waits for shot then role travel before Next',async()=>{
  const shot=deferred(),travel=deferred(),calls=[];
  const stadium={enter:role=>{calls.push(role);return calls.length===1?Promise.resolve():travel.promise;},
    shot:outcome=>{calls.push(outcome);return shot.promise;},reset(){},skip(){},leave(){}};
  const s=setup('solo',true,stadium);
  await boot(s,true,run({phase:'REVIEW',position:2,role:'keeper',shootout:shootout(),review:[{position:2,is_correct:true,outcome:'save'}]}));
  assert.deepEqual(calls,['keeper','save']);assert.equal(s.get('next').disabled,true);
  s.get('next').emit('click');assert.equal(s.requests.length,3);
  shot.resolve();await flush();assert.deepEqual(calls,['keeper','save','shooter']);assert.equal(s.get('next').disabled,true);
  travel.resolve();await flush();assert.equal(s.get('next').disabled,false);
});
test('deciding shot completes before stadium outro and results do not replay on refresh',async()=>{
  const shot=deferred(),outro=deferred(),calls=[];
  const stadium={enter:()=>Promise.resolve(),skip(){},reset(){},leave(){},
    shot:()=>{calls.push('shot');return shot.promise;},finish:()=>{calls.push('outro');return outro.promise;}};
  const s=setup('solo',true,stadium);
  const q={text:'Question?',options:[{id:'0',text:'A'}]};
  await boot(s,true,run({phase:'ANSWERING',position:6,role:'keeper',shootout:shootout(),question:q}));
  const sending=s.get('choices').children[0].emit('click');await flush();
  const review=Array.from({length:6},(_,i)=>({position:i+1,is_correct:true,outcome:i%2?'save':'goal',option_id:'0',correct:'0',text:'Question',explanation:'A'}));
  const done=run({phase:'FINISHED',position:6,role:'keeper',shootout:shootout({winner:'player',player:3}),question:q,review,correct:6,total_xp:60});
  reply(s.requests[3],done);await sending;await flush();
  assert.deepEqual(calls,['shot']);assert.equal(s.get('summary').hidden,true);
  assert.deepEqual(s.sounds,[]);
  shot.resolve();await flush();assert.deepEqual(calls,['shot','outro']);assert.equal(s.get('summary').hidden,false);
  outro.resolve();await flush();
  assert.deepEqual(s.sounds,['win']);
  assert.equal(s.get('result-metrics').children[0].children[0].textContent,'6 / 6');
  const sharing=s.get('share-result').emit('click');
  reply(s.requests.at(-1),{title:'3 : 0',url:'https://onthedot.gg/s/win',image_url:'https://onthedot.gg/s/win/image.png'});await sharing;
  await s.get('share-copy').emit('click');assert.equal(s.copied[0],'https://onthedot.gg/s/win');
  s.get('retry').emit('click');await flush();reply(s.requests.at(-1),done);await flush();
  assert.deepEqual(calls,['shot','outro']);
  assert.deepEqual(s.sounds,['win']);
});
test('opening a completed shootout from history shows results without replaying cinematics',async()=>{
  const calls=[],stadium={enter(){calls.push('enter');},shot(){calls.push('shot');},finish(){calls.push('finish');},leave(){calls.push('leave');}};
  const s=setup('solo',true,stadium);
  await boot(s,true,run({phase:'FINISHED',position:6,shootout:shootout({winner:'player'})}));
  assert.deepEqual(calls,['leave']);assert.equal(s.get('summary').hidden,false);
  assert.deepEqual(s.sounds,[]);
});
test('ending a live shootout plays one loss cue, never a win',async()=>{
  const stadium={enter:()=>Promise.resolve(),skip(){},leave(){},finish:()=>Promise.resolve()};
  const s=setup('solo',true,stadium);
  await boot(s,true,run({phase:'ANSWERING',position:1,shootout:shootout(),question:{text:'Question?',options:[]}}));
  const sending=s.get('leave').emit('click');await flush();
  reply(s.requests.at(-1),run({phase:'ABANDONED',position:1,shootout:shootout({winner:'opponent'})}));
  await sending;await flush();assert.deepEqual(s.sounds,['loss']);
});

test('server rejection refreshes eligibility when another tab used the questions',async()=>{
  const s=setup();await boot(s);
  const starting=s.get('quiz-start').emit('submit');await flush();
  reply(s.requests[3],{detail:'No new shootout is available for this selection right now.'},409);await flush();
  assert.equal(s.requests[4].url,'/api/solo/catalog');
  reply(s.requests[4],{...catalog,categories:[{code:'ALL',label:'All clubs',counts:{easy:0,medium:10,hard:10}}]});
  await starting;assert.equal(s.get('start').disabled,true);assert.match(s.get('error').textContent,/No new shootout/);
});

test('weekly rollover refreshes an idle selection without changing difficulty',async()=>{
  const s=setup();reply(s.requests[0],user);await flush();
  reply(s.requests[1],{...catalog,resets_at:'2000-01-03T00:00:00Z'});await flush();
  reply(s.requests[2],{run:null});await flush();
  s.radio.value='medium';s.get('medium').emit('change');
  s.timers.find(t=>t.ms===30000).fn();await flush();
  assert.equal(s.requests[3].url,'/api/solo/catalog');assert.equal(s.get('start').disabled,true);
  reply(s.requests[3],{...catalog,resets_at:'2099-09-28T00:00:00Z'});await flush();
  assert.equal(s.radio.value,'medium');assert.equal(s.get('start').disabled,false);
});

test('new games always submit mixed topics and all clubs without displaying counts',async()=>{
  const s=setup();reply(s.requests[0],user);await flush();
  reply(s.requests[1],{...catalog,topics:[
    {code:'ALL',label:'Mixed topics',counts_by_team:{ALL:{easy:10,medium:20,hard:30}}},
    {code:'kits',label:'Kits & sponsors',counts_by_team:{ALL:{easy:0,medium:20,hard:5},GEN:{easy:0,medium:0,hard:0}}},
  ]});await flush();reply(s.requests[2],{run:null});await flush();
  // Stale filter values cannot narrow the now difficulty-only selection.
  s.get('topic').value='kits';s.get('category').value='GEN';
  assert.equal(s.get('start').disabled,false);assert.equal(s.get('medium-available').textContent,'');
  s.radio.value='medium';s.get('medium').emit('change');assert.equal(s.get('start').disabled,false);
  const starting=s.get('quiz-start').emit('submit');await flush();
  assert.deepEqual(JSON.parse(s.requests[3].options.body),{category:'ALL',topic:'ALL',difficulty:'medium',request_id:'request-3'});
  assert.equal(s.get('availability').textContent,'');
  reply(s.requests[3],run({difficulty:'medium',category:{label:'All clubs',topic_code:'ALL',topic_label:'Mixed topics'}}));await starting;
  assert.equal(s.get('run-category').textContent,'Mixed topics · All clubs · Medium');
});
