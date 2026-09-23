(function(){
  'use strict';
  const $=id=>document.getElementById(id), page=document.querySelector('.penalty-page');
  let state=null,code=new URL(location.href).searchParams.get('room'),socket=null,retry=null,stopped=false;
  let rendered=-1,animated=null,offset=0,pending=null,packs=[],reconnects=0,nameChanged=false;
  const stadium=globalThis.PointsStadium;
  let readyBusy=false,stadiumRound=null,stadiumRoom=null;
  function stadiumView(next){
    if(!stadium)return;
    if(['FINISHED','ABANDONED'].includes(next.phase)){stadium.leave();return;}
    if(!next.round)return;
    const key=`${next.code}:${next.round.id}`,role=next.mode==='solo'||next.round.shooter===next.me?'shooter':'keeper';
    if(stadiumRound===key){if(next.phase==='ANSWERING')stadium.skip();return;}
    stadiumRound=key;
    // The authoritative opens_at is an upper bound, never a client-side delay.
    // Refreshing during ANSWERING uses an immediate static view, not an intro.
    const remaining=next.phase==='COUNTDOWN'?Math.max(0,next.round.opens_at-next.server_now-150):0;
    stadium.enter(role,{intro:false,maxDurationMs:remaining});
  }
  const labels={goal:'Goal',save:'Save',miss:'Miss',replay:'Timing tie: new question, same roles'};
  const reasons={target_reached:'Full time',solo_complete:'Shootout complete',disconnect_forfeit:'Forfeit: opponent did not reconnect',
    resigned:'Game ended by resignation',technical_interruption:'Game interrupted by a technical issue',players_disconnected:'Players disconnected',
    question_pool_exhausted:'No questions remaining. No winner.',time_limit:'Match time limit reached. No winner.'};
  function error(message){$('error').textContent=message||'';$('error').hidden=!message;}
  function countLabel(count,noun){return `${count} ${noun}${count===1?'':'s'}`;}
  async function api(path,body){
    const response=await fetch('/api/penalties'+path,{method:body===undefined?'GET':'POST',
      headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Unable to process the request.');return data;
  }
  function mode(){return document.querySelector('input[name="mode"]:checked').value;}
  function setupMode(){
    const pvp=mode()==='pvp';$('create-game').textContent=pvp?'Create room':'Play solo';
    $('match-label').textContent=pvp?'PvP · first to 10 goals':'Solo · 10 shots';
    $('rules-note').textContent=pvp?'First to 10 goals, with equal turns. Both players have 12 seconds to answer. A timing gap under 150 ms triggers a replay. Private, unranked pilot; 30-minute limit.':'Solo: 10 shots, 12 seconds per question. A correct answer scores a goal.';
    const pack=packs.find(p=>p.id===$('pack').value),minimum=pvp?40:1;
    if(!pvp&&pack)$('match-label').textContent=`Solo · ${countLabel(Math.min(10,pack.count),'shot')}`;
    if(!pvp&&pack)$('rules-note').textContent=`Solo: ${countLabel(Math.min(10,pack.count),'shot')}, 12 seconds per question. A correct answer scores a goal.`;
    $('pack-status').textContent=pack?`${countLabel(pack.count,'question')}${pack.language?' · '+pack.language:''}`+(pack.count<minimum?` · this mode requires ${minimum}`:''):'';
    $('pack-label').textContent=pack?.label||'';
    $('create-game').disabled=!pack||pack.count<minimum;
  }
  async function identity(){const result=await api('/session',{name:$('player-name').value.trim()});$('player-name').value=result.name;}
  function connect(){
    clearTimeout(retry);stopped=false;rendered=-1;if(socket){socket.onclose=null;socket.close();}
    socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/penalties/rooms/${code}/live`);
    socket.onmessage=e=>{try{const next=JSON.parse(e.data);reconnects=0;render(next);$('retry-connection').hidden=true;}catch{error('Invalid server message.');}};
    socket.onclose=()=>{if(stopped)return;$('connection').textContent='Reconnecting...';$('retry-connection').hidden=false;disableAnswers();reconnects++;if(reconnects>8){error('Unable to reconnect. Please try again.');return;}retry=setTimeout(connect,Math.min(15000,1000*2**reconnects));};
    socket.onerror=()=>{$('connection').textContent='Connection lost';};
  }
  function disableAnswers(){for(const button of $('answers').children)button.disabled=true;}
  function explanation(question){
    return question.explanation;
  }
  async function enter(room){
    code=room;history.replaceState(null,'','/penalties?room='+encodeURIComponent(code));
    const next=await api(`/rooms/${code}/join`,{});rendered=-1;render(next);
    if(!['FINISHED','ABANDONED'].includes(next.phase))connect();
  }
  function render(next){
    if(code&&next.code!==code)return;
    if(state&&state.code===next.code&&next.version<state.version)return;
    if(state&&state.code===next.code&&next.server_now<state.server_now)return;
    offset=next.server_now-Date.now();state=next;
    $('connection').textContent=next.phase==='LOBBY'?'Room '+next.code:'Connected';
    if(rendered===next.version)return;rendered=next.version;
    const finished=['FINISHED','ABANDONED'].includes(next.phase),lobby=next.phase==='LOBBY',r=next.round;
    if($('timer-fill').parentElement)$('timer-fill').parentElement.hidden=!['COUNTDOWN','ANSWERING'].includes(next.phase);
    page.classList.toggle('active',!lobby&&!finished);$('setup').hidden=true;$('room-tools').hidden=!lobby;
    page.classList.toggle('long-question',(next.question?.text.length||0)>160);
    $('invite-link').value=location.origin+'/penalties?room='+next.code;
    $('copy-link').hidden=next.mode==='solo';$('invite-link').parentElement.hidden=next.mode==='solo';
    $('ready-game').disabled=next.players[next.me].ready;
    $('ready-game').textContent=next.players[next.me].ready?'Ready':'Ready to play';
    $('player-a').textContent=next.players[0].name+ (next.me===0?' · you':'');
    $('player-b').textContent=next.players[1]?next.players[1].name+(next.me===1?' · you':''):(next.mode==='solo'?'Goal':'Waiting for opponent');
    $('score').textContent=next.mode==='solo'?`${next.score[0]} / ${next.attempts[0]}`:next.score.join(' : ');
    stadium?.hud?.({score:$('score').textContent});
    $('match-label').textContent=next.mode==='solo'?`Solo · ${countLabel(next.rules.solo_shots,'shot')}`:'PvP · first to 10 goals';
    $('role-a').textContent=r?(r.shooter===0?'Shooting':'Keeping'):(next.players[0].ready?'Ready':'Waiting');
    $('role-b').textContent=r&&next.mode==='pvp'?(r.shooter===1?'Shooting':'Keeping'):(next.players[1]?.ready?'Ready':'');
    $('round-count').textContent=r?`Penalty ${r.id} · ${next.mode==='solo'?'solo':'pair '+r.pair}`:'';
    $('pack-label').textContent=next.pack_label||(next.pack==='maths'?'Football maths · practice questions':'Verified ON THE DOT. questions');
    $('rules-note').textContent=next.mode==='pvp'?'First to 10 goals, with equal turns. 12 seconds per answer; a timing gap under 150 ms triggers a replay. Unranked; server timings include network latency. 30-minute limit.':`${countLabel(next.rules.solo_shots,'shot')} · 12 seconds per answer`;
    $('leave-game').hidden=finished;$('new-game').hidden=!finished;$('rematch').hidden=!finished;
    $('next-shot').hidden=next.mode!=='solo'||next.phase!=='RESOLVED';
    $('copy-result').hidden=!finished;
    $('result-stats').hidden=!finished;
    if(finished)$('result-stats').textContent=next.players.map((p,i)=>`${p.name}: ${countLabel(next.score[i],'goal')}, ${countLabel(next.stats[i].saves,'save')}, ${next.stats[i].correct}/${next.stats[i].answered+next.stats[i].timeouts} correct, ${countLabel(next.stats[i].timeouts,'timeout')}`).join('\n');
    const oldQuestion=$('question-title').textContent;
    $('question-title').textContent=next.question?.text||(lobby?(next.mode==='pvp'?'Private penalty shootout':'Ready to shoot?'):'Get ready...');
    if(oldQuestion!==$('question-title').textContent&&next.phase==='ANSWERING')$('question-title').focus({preventScroll:true});
    $('answers').replaceChildren();
    if(next.question)next.question.options.forEach((option,i)=>{
      const button=document.createElement('button'),letter=document.createElement('span');letter.textContent='ABCD'[i];letter.setAttribute('aria-hidden','true');
      button.append(letter,document.createTextNode(option.text));button.dataset.option=option.id;
      button.disabled=next.phase!=='ANSWERING'||r.own_option!==null;
      button.classList.toggle('chosen',r.own_option===option.id);
      if(next.question.correct!==undefined){button.classList.toggle('correct',option.id===next.question.correct);button.classList.toggle('wrong',r.own_option===option.id&&option.id!==next.question.correct);}
      button.addEventListener('click',()=>answer(option.id));$('answers').append(button);
    });
    if(finished){
      $('feedback').textContent=(reasons[next.reason]||'Game over')+(next.mode==='pvp'&&next.winner!==null?`. Winner: ${next.players[next.winner].name}.`:'')+(next.question?.correct!==undefined?' · '+explanation(next.question):'');
      stopped=true;clearTimeout(retry);if(socket)socket.close();
    }else if(r?.outcome){
      const times=r.answers.map((a,i)=>`${next.players[i].name}: ${a?(a.correct?'correct':'incorrect')+' · '+(a.elapsed_ms/1000).toFixed(2)+' s':'timeout'}`).join(' / ');
      $('feedback').textContent=labels[r.outcome]+'. '+explanation(next.question)+' '+times;
    }else $('feedback').textContent=lobby?'Confirm you are ready.':r?.own_option!==null&&r?.own_option!==undefined?'Answer submitted. Waiting for the result.':'';
    if(r?.outcome&&animated!==`${next.code}:${r.id}`){animated=`${next.code}:${r.id}`;window.PenaltyScene.shot(r.outcome,animated);}
    else if(!r?.outcome){window.PenaltyScene.reset();}
    $('attempts').replaceChildren();next.history.slice(-20).forEach(item=>{const dot=document.createElement('span');dot.className=item.outcome;dot.textContent={goal:'✓',save:'–',miss:'×',replay:'↻'}[item.outcome];dot.title=labels[item.outcome];$('attempts').append(dot);});
    stadiumView(next);
    updateClock();
  }
  async function answer(option){
    if(!state||state.phase!=='ANSWERING'||state.round.own_option!==null)return;
    if(!pending||pending.penalty_id!==state.round.id)pending={penalty_id:state.round.id,option_id:option,request_id:crypto.randomUUID()};
    disableAnswers();error('');
    try{render(await api(`/rooms/${code}/answers`,pending));pending=null;}
    catch(e){error(e.message);try{rendered=-1;render(await api(`/rooms/${code}`));}catch{}}
  }
  async function command(name){error('');try{render(await api(`/rooms/${code}/${name}`,{}));}catch(e){error(e.message);}}
  $('create-game').addEventListener('click',async()=>{error('');$('create-game').disabled=true;try{await identity();const room=await api('/rooms',{mode:mode(),pack:$('pack').value});await enter(room.code);}catch(e){error(e.message);}finally{setupMode();}});
  $('join-form').addEventListener('submit',async e=>{e.preventDefault();error('');try{await identity();await enter($('room-code').value.trim().toUpperCase());}catch(e){error(e.message);}});
  $('ready-game').addEventListener('click',async()=>{
    if(readyBusy||state?.phase!=='LOBBY'||state.players[state.me].ready)return;
    readyBusy=true;$('ready-game').disabled=true;
    const room=code;
    try{
      // Fly before Ready, while neither player's answer clock is running.
      // The role is supplied by the server, NOT inferred from host/guest order.
      if(stadium&&stadiumRoom!==room){
        stadiumRoom=room;
        const shooter=state.initial_shooter;
        if(shooter!==undefined)await stadium.enter(state.mode==='solo'||shooter===state.me?'shooter':'keeper',{intro:true});
      }
      if(code===room&&state?.phase==='LOBBY')await command('ready');
    }finally{readyBusy=false;if(state?.phase==='LOBBY')$('ready-game').disabled=state.players[state.me].ready;}
  });
  $('next-shot').addEventListener('click',()=>command('next'));
  $('leave-game').addEventListener('click',()=>command('leave'));
  $('new-game').addEventListener('click',()=>{location.href='/penalties';});
  $('rematch').addEventListener('click',async()=>{error('');try{const room=await api(`/rooms/${code}/rematch`,{});stadium?.leave();stadiumRoom=null;stadiumRound=null;state=null;animated=null;pending=null;await enter(room.code);}catch(e){error(e.message);}});
  $('copy-link').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('invite-link').value);$('copy-link').textContent='Copied';}catch{ $('invite-link').select();error('The link is selected and ready to copy.');}});
  $('copy-result').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(`ON THE DOT. · ${state.players.map(p=>p.name).join(' vs ')} · ${state.score.join(' : ')} · ${reasons[state.reason]||state.reason}`);$('copy-result').textContent='Copied';}catch{error('Unable to copy the result.');}});
  $('retry-connection').addEventListener('click',()=>{reconnects=0;connect();});
  document.querySelectorAll('input[name="mode"]').forEach(input=>input.addEventListener('change',setupMode));$('pack').addEventListener('change',setupMode);
  $('player-name').addEventListener('input',()=>{nameChanged=true;});
  // Update immediately on state changes as well as on ticks: the first frame
  // of a new question must not retain the countdown's expired 0.0 seconds.
  function updateClock(){
    if(!state?.round)return;const r=state.round,now=Date.now()+offset;
    const remaining=state.phase==='COUNTDOWN'?Math.max(0,r.opens_at-now):Math.max(0,r.deadline-now);
    if(state.phase==='COUNTDOWN'&&remaining===0)stadium?.skip();
    $('timer-fill').style.transform=`scaleX(${state.phase==='ANSWERING'?Math.min(1,remaining/state.rules.answer_ms):0})`;
    stadium?.hud?.({clock:['COUNTDOWN','ANSWERING'].includes(state.phase)?(remaining/1000).toFixed(1)+' s':''});
    if(state.phase==='ANSWERING'&&remaining===0)disableAnswers();
  }
  setInterval(updateClock,100);
  async function init(){
    try{
      const data=await api('/packs');packs=data.packs;$('pack').replaceChildren();
      const groups=new Map();
      packs.forEach(pack=>{
        const label=pack.group||'Other packs';let group=groups.get(label);
        if(!group){group=document.createElement('optgroup');group.label=label;groups.set(label,group);$('pack').append(group);}
        const option=document.createElement('option');option.value=pack.id;option.textContent=pack.label;group.append(option);
      });
      $('pack').disabled=!packs.length;setupMode();
    }catch(e){error(e.message);$('create-game').disabled=true;}
    try{const me=await api('/session');if(!nameChanged)$('player-name').value=me.name;if(code)await enter(code);}catch(e){if(code){$('room-code').value=code;error('Enter your name and join the room.');}}
  }
  init();
})();
