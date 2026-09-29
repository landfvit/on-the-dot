/* Friend Duel owns no score calculation or rewards. The server serializes both
 * answers; this module only presents its snapshots and stadium animations. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),page=document.querySelector('[data-page="friend"]');
  if(!page)return;
  const stadium=globalThis.PointsStadium,terminal=s=>['FINISHED','ABANDONED'].includes(s?.phase);
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  let code=page.dataset.invite,user=null,room=null,busy=false,polling=false,offset=0,renderKey='',startRequest=null,pending=null;
  let entered=false,introducing=false,presentation=0,role=null,animation=Promise.resolve(),finished=false,openTimer=null;
  const sharing=globalThis.PointsResultShare.bind(()=>room?{run_id:room.run_id,mode:'friend'}:null);
  const inviteFriend=new URLSearchParams(location.search).get('invite');
  const animated=new Set();
  let forfeitRun=null,lastDecision=null;
  const playerName=(s,seat)=>!s.players[seat]?'Friend':s.players[seat].is_guest?(seat===s.me?'You':'Friend'):s.players[seat].name;
  const opponentName=s=>playerName(s,1-s.me);
  // Presentation of an already resolved round only. Never infer correctness
  // from an option or pick a winner locally; both come from the server.
  function roundDecision(s){
    const r=s.round;
    if(!r?.outcome||!r.answers)return null;
    const winner=r.outcome==='goal'?r.shooter:r.outcome==='save'?1-r.shooter:null;
    const seconds=ms=>(ms/1000).toFixed(ms%10?3:2)+' s';
    return {outcome:r.outcome,rows:[s.me,1-s.me].map(seat=>{
      const a=r.answers[seat];
      return {name:playerName(s,seat),winner:seat===winner,correct:Boolean(a?.correct),
        status:!a?'Time out':a.correct?'Correct':'Incorrect',time:a?seconds(a.elapsed_ms):null};
    })};
  }
  function showDecision(target,decision){
    target.replaceChildren();target.hidden=!decision;if(!decision)return;
    target.dataset.outcome=decision.outcome;
    const players=node('div',undefined,'friend-answer-comparison');
    for(const row of decision.rows){
      const player=node('div',undefined,'friend-answer'+(row.winner?' is-winner':''));
      player.setAttribute('aria-label',`${row.name}: ${row.status}${row.time?', '+row.time:''}${row.winner?', won this penalty':''}`);
      const name=node('strong',row.name,'friend-answer-name');name.title=row.name;
      const detail=node('span',row.time||'Time out','friend-answer-time');
      player.append(name,detail);players.append(player);
    }
    target.append(players);
  }
  function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
  async function api(path,body){
    const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();if(!response.ok){const e=new Error(typeof data.detail==='string'?data.detail:'Unable to load the duel.');e.status=response.status;throw e;}return data;
  }
  const roomPath=()=>`friends/rooms/${encodeURIComponent(code)}`;
  function remember(value){code=value;history.replaceState(null,'',code?'/friends/'+encodeURIComponent(code):'/friends');}
  function scoreboard(s){
    $('shootout-board').hidden=s.phase==='LOBBY'||terminal(s)&&!entered;
    for(const [id,seat] of [['player',s.me],['opponent',1-s.me]]){
      const name=playerName(s,seat);
      $('name-'+id).textContent=name;$('name-'+id).title=name;
      $('score-'+id).textContent=String(s.score[seat]);
      const shots=s.history.filter(r=>r.shooter===seat&&r.outcome!=='replay');
      const count=Math.max(5,...s.attempts),indices=Array.from({length:count},(_,i)=>i).filter(i=>count<=7||i<5||i>=count-2);
      $('kicks-'+id).replaceChildren(...indices.map(i=>{
        const shot=shots[i],result=!shot?'pending':shot.outcome==='goal'?'goal':'miss';
        const el=node('span',undefined,'shootout-kick '+result);el.setAttribute('role','img');el.setAttribute('aria-label',`${name}, penalty ${i+1}: ${result}`);return el;
      }));
    }
    $('shootout-round').textContent=terminal(s)?'Full time':Math.min(...s.attempts)>=5?'Sudden death':`Round ${s.round?.pair||1} / 5`;
  }
  function lobby(s){
    $('friend-lobby').hidden=false;$('quiz-start').hidden=true;
    $('lobby-title').textContent='Friend Duel';$('lobby-players').textContent=[s.me,1-s.me].map(i=>playerName(s,i)+(s.players[i]?.ready?' · Ready':'')).join(' vs ');
    $('lobby-status').textContent=s.players.length<2?'Send the link to your friend.':s.players[s.me].ready?`Waiting for ${opponentName(s)}`:'Both players must be ready to start.';
    $('invite-link').value=location.origin+'/friends/'+code;
    $('friend-ready').hidden=s.players.length<2;$('friend-ready').disabled=busy||s.players[s.me].ready;
    $('friend-leave').hidden=false;$('friend-join').hidden=true;$('invite-controls').hidden=false;
    if(entered){
      $('shootout-board').hidden=false;
      $('selection').hidden=true;$('quiz-run').hidden=false;$('summary').hidden=true;$('question-panel').hidden=false;
      $('question-title').textContent=s.players[1-s.me]?.ready?'Getting ready...':`Waiting for ${opponentName(s)}`;
      $('question-title').setAttribute('aria-live','polite');
      // Occupy the existing answer slot: the loader never pushes controls down.
      if(!$('choices').querySelector('.friend-waiting')){
        const waiting=node('div',undefined,'friend-waiting'),ball=node('img');
        waiting.setAttribute('aria-hidden','true');ball.src='/trivia-assets/icons/football.svg?v=3';ball.alt='';waiting.append(ball);$('choices').replaceChildren(waiting);
      }
      $('feedback').textContent='The duel starts when both players are ready.';
      $('run-position').textContent=s.players[s.me].ready?'Ready':'Getting ready';
      $('leave').hidden=false;
      $('timer').parentElement.hidden=true;$('next').hidden=true;
    }
  }
  // Queue one animation per resolved question. A fresh server-open question
  // always takes priority over old presentation, including after reconnecting.
  function present(s){
    if(!stadium||s.phase==='LOBBY')return;
    const epoch=presentation,r=s.round,shotRole=(r?.shooter??s.initial_shooter)===s.me?'shooter':'keeper';
    const nextRole=r?.outcome==='replay'?shotRole:shotRole==='shooter'?'keeper':'shooter';
    if(!entered&&terminal(s)){stadium.leave();return;}
    animation=animation.catch(()=>{}).then(async()=>{
      if(epoch!==presentation)return;
      // Check inside the queue: another snapshot may have finished this shot.
      const desired=s.phase==='RESOLVED'&&animated.has(r?.id)?nextRole:shotRole;
      if(!entered){entered=true;role=desired;await stadium.enter(role,{intro:false,maxDurationMs:0});}
      if(epoch!==presentation)return;
      if(role!==desired){role=desired;stadium.reset();await stadium.enter(role,{intro:false});}
      if(epoch!==presentation)return;
      if(r?.outcome&&!animated.has(r.id)){
        animated.add(r.id);
        await stadium.shot(r.outcome,globalThis.PenaltyShots?.plan(r.outcome,code+':'+r.id));
      }
      if(epoch!==presentation)return;
      if(terminal(s)&&!finished){
        finished=true;$('question-panel').hidden=true;$('summary').hidden=false;
        await stadium.finish?.();
        if(s.winner!==null)globalThis.PointsAudio?.play(s.winner===s.me?'win':'loss');
        $('result-heading').focus({preventScroll:true});
      }else if(s.phase==='RESOLVED'&&role!==nextRole){
        // Prepare the next view immediately after the shot's short result hold.
        // Only the server opens the next question and starts its answer clock.
        role=nextRole;stadium.reset();await stadium.enter(role,{intro:false});
      }else if(['ANSWERING','COUNTDOWN'].includes(s.phase)){stadium.skip();stadium.reset();}
    }).catch(()=>{stadium.leave();if(terminal(room)){$('question-panel').hidden=true;$('summary').hidden=false;}});
  }
  function summary(s){
    $('result-heading').textContent=s.winner===null?'Duel ended':s.winner===s.me?'You won the duel!':`${playerName(s,s.winner)} wins`;
    const reason={resigned:'Forfeit',disconnect_forfeit:'Connection forfeit',inactivity:'Inactivity',time_limit:'Session expired',question_pool_exhausted:'No unused questions remain'}[s.reason];
    $('result-completion').textContent=`${s.score[s.me]} : ${s.score[1-s.me]}${reason?' · '+reason:''}`;
    const entries=[[`${s.stats[s.me].correct} / ${s.history.length}`,'Correct answers'],['Friendly','No XP or rating']];
    $('result-metrics').replaceChildren(...entries.map(([value,label])=>{const e=node('div',undefined,'metric');e.append(node('strong',value),node('span',label));return e;}));
    $('result-level').hidden=true;$('guest-benefits').hidden=true;$('another').hidden=false;$('another').textContent='New friend duel';
    $('summary-account').textContent=user?'View profile':'Create account';$('summary-account').href=user?'/account':'/account?mode=register';$('result-review').hidden=true;
    $('summary').hidden=entered&&!finished;$('question-panel').hidden=!entered||finished;
    showDecision($('friend-final-result'),roundDecision(s));
    sharing.reset();
  }
  function render(s){
    if(room&&room.run_id===s.run_id&&s.server_now<room.server_now)return;
    room=s;offset=s.server_now-Date.now();
    updateClock();
    if(terminal(s)&&$('forfeit-dialog').open)$('forfeit-dialog').close();
    // Fetch at the shared opening instant, not at each tab's arbitrary polling
    // phase. The server still withholds question/answer data before that time.
    clearTimeout(openTimer);
    if(s.phase==='COUNTDOWN')openTimer=setTimeout(refresh,Math.max(20,s.round.opens_at-s.server_now+20));
    const key=[s.phase,s.version,s.round?.id,s.round?.own_option,busy].join(':');
    if(key===renderKey)return;renderKey=key;scoreboard(s);$('retry').hidden=true;
    if(s.phase==='LOBBY'){
      lastDecision=null;showDecision($('friend-round-result'),null);$('feedback').hidden=false;
      // Reloading a ready lobby restores waiting, not a disabled Ready button.
      if(s.players[s.me].ready&&!entered){entered=true;role=s.initial_shooter===s.me?'shooter':'keeper';stadium?.enter(role,{intro:false,maxDurationMs:0});}
      lobby(s);return;
    }
    $('selection').hidden=true;$('quiz-run').hidden=false;
    const done=terminal(s),active=s.phase==='ANSWERING',r=s.round;
    page.classList.toggle('shootout-active',!done);page.classList.toggle('shootout-finished',done);
    $('run-position').textContent=r?(r.shooter===s.me?'Shooting':'Defending')+' · Round '+r.pair:'';
    $('question-title').textContent=s.question?.text||(done?'Duel ended':r?.shooter===s.me?'Get ready to shoot':'Get ready to save');
    $('timer').parentElement.hidden=!active&&s.phase!=='COUNTDOWN';$('choices').replaceChildren();
    for(const option of s.question?.options||[]){
      const b=node('button',option.text);b.disabled=!active||busy||r.own_option!==null;
      b.classList.toggle('chosen',option.id===r.own_option);
      if(r.outcome){
        b.classList.toggle('correct',option.id===s.question.correct);
        b.classList.toggle('incorrect',option.id===r.own_option&&option.id!==s.question.correct);
        if(option.id===s.question.correct)b.setAttribute('aria-label',option.text+', correct answer');
        else if(option.id===r.own_option)b.setAttribute('aria-label',option.text+', incorrect answer');
      }
      b.addEventListener('click',()=>answer(option.id));$('choices').append(b);
    }
    const feedback=active&&r?.own_option!==null?`Answer locked. Waiting for ${opponentName(s)}...`:'';
    if(r?.outcome)lastDecision=roundDecision(s);
    else if(active)lastDecision=null;
    showDecision($('friend-round-result'),lastDecision);
    $('feedback').hidden=Boolean(lastDecision);$('feedback').textContent=feedback;
    $('next').hidden=true;$('leave').hidden=done;
    $('summary').hidden=true;$('question-panel').hidden=false;
    if(done)summary(s);present(s);
  }
  async function refresh(){
    if(!code||polling||busy)return;polling=true;
    const own=code;
    try{const s=await api(roomPath());if(code!==own)return;error();render(s);}
    catch(e){if(code!==own)return;error(e.message);$('retry').hidden=false;for(const b of $('choices').children)b.disabled=true;}
    finally{polling=false;}
  }
  async function command(action,body={}){
    if(busy)return;busy=true;error();for(const b of $('choices').children)b.disabled=true;
    try{const s=await api(roomPath()+'/'+action,body);busy=false;renderKey='';render(s);pending=null;}
    catch(e){error(e.message);busy=false;renderKey='';await refresh();}
    finally{busy=false;}
  }
  function answer(option){
    if(busy||room?.phase!=='ANSWERING'||room.round.own_option!==null)return;
    if(!pending||pending.position!==room.round.id)pending={position:room.round.id,option_id:option,request_id:crypto.randomUUID()};
    return command('answers',pending);
  }
  $('quiz-start').addEventListener('submit',async e=>{
    e.preventDefault();if(busy)return;busy=true;$('start').disabled=true;error();
    const difficulty=document.querySelector('input[name="difficulty"]:checked').value;
    if(startRequest?.difficulty!==difficulty)startRequest={difficulty,request_id:crypto.randomUUID()};
    try{
      if(!await globalThis.PointsModeIntro.show('friend'))return;
      const s=await api('friends/rooms',startRequest);remember(s.code);busy=false;render(s);startRequest=null;
      if(inviteFriend&&user){await api('players/friends/'+encodeURIComponent(inviteFriend)+'/invite',{run_id:s.run_id});$('lobby-status').textContent='Invitation sent to '+inviteFriend+'. You can also share the link.';}
    }
    catch(e){error(e.message);}finally{busy=false;$('start').disabled=false;}
  });
  $('friend-join').addEventListener('click',async()=>{if(busy)return;$('friend-join').disabled=true;try{if(await globalThis.PointsModeIntro.show('friend'))await command('join');}finally{$('friend-join').disabled=false;}});
  $('friend-ready').addEventListener('click',async()=>{
    if(busy||introducing)return;introducing=true;entered=true;$('friend-ready').disabled=true;
    const match=room.run_id;
    role=room.initial_shooter===room.me?'shooter':'keeper';lobby(room);
    try{await stadium?.enter(role,{intro:true});introducing=false;if(room?.run_id===match&&room.phase==='LOBBY')await command('ready');}
    catch(e){introducing=false;error(e.message);}
  });
  function requestForfeit(){
    if(!room||terminal(room)||busy)return;
    forfeitRun=room.run_id;
    $('forfeit-description').textContent=room.players.length===2
      ?`${opponentName(room)} will win the duel. No XP or rating is affected.${room.phase==='LOBBY'?'':' The match clock keeps running.'}`
      :'This will close your invitation. No XP or rating is affected.';
    $('forfeit-confirm').textContent=room.players.length===2?'Forfeit':'Close invitation';
    $('forfeit-dialog').showModal();$('forfeit-cancel').focus();
  }
  for(const id of ['friend-leave','leave'])$(id).addEventListener('click',requestForfeit);
  $('forfeit-cancel').addEventListener('click',()=>$('forfeit-dialog').close());
  $('forfeit-dialog').addEventListener('close',()=>{forfeitRun=null;});
  $('forfeit-confirm').addEventListener('click',()=>{
    // A result arriving while the dialog is open invalidates its confirmation.
    if(!room||terminal(room)||room.run_id!==forfeitRun||busy)return;
    $('forfeit-dialog').close();command('leave');
  });
  $('retry').addEventListener('click',refresh);
  $('invite-copy').addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText($('invite-link').value);$('lobby-status').textContent='Invitation copied.';}
    catch{$('invite-link').select();$('lobby-status').textContent='Copy the selected invitation link.';}
  });
  $('invite-share').addEventListener('click',async()=>{
    if(!navigator.share){$('invite-copy').click();return;}
    try{await navigator.share({title:'ON THE DOT. | Friend Duel',text:'Join my penalty shootout.',url:$('invite-link').value});}catch(e){if(e.name!=='AbortError')error('Could not share. Copy the invitation link instead.');}
  });
  $('another').addEventListener('click',()=>{
    presentation++;stadium?.leave();remember('');room=null;role=null;lastDecision=null;entered=finished=introducing=false;renderKey='';animated.clear();sharing.reset();
    page.classList.remove('shootout-active','shootout-finished');$('shootout-board').hidden=true;$('quiz-run').hidden=true;$('selection').hidden=false;$('friend-lobby').hidden=true;$('quiz-start').hidden=false;error();
  });
  setInterval(()=>{if(room&&!terminal(room)&&!document.hidden)refresh();},1000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&room)refresh();});
  function updateClock(){
    if(!room?.round)return;
    const countdown=room.phase==='COUNTDOWN',active=room.phase==='ANSWERING',r=room.round;
    const remaining=countdown||active?Math.max(0,(countdown?r.opens_at:r.deadline)-Date.now()-offset)/1000:0;
    $('seconds').textContent=(countdown?'Ready in ':'')+Math.ceil(remaining)+' s';$('timer').max=countdown?4:15;$('timer').value=remaining;
    if(active&&remaining===0)for(const b of $('choices').children)b.disabled=true;
  }
  setInterval(updateClock,100);
  async function init(){
    page.classList.toggle('friend-motion-off',globalThis.PointsPreferences?.get?.().animations===false||globalThis.PointsPreferences?.get?.().reduced_motion===true);
    $('start').textContent='Create invitation';$('quiz-rules').textContent='5 penalties each · 15 seconds · No XP or rating';$('availability').hidden=true;
    try{user=await api('players/me');}catch(e){if(e.status!==401)throw e;}
    if(user?.preferences){globalThis.PointsPreferences?.set(user.preferences);page.classList.toggle('friend-motion-off',user.preferences.animations===false||user.preferences.reduced_motion===true);}
    if(!code){const active=await api('friends/active');if(active.code)remember(active.code);}
    if(code){
      const invite=await api('friends/invites/'+encodeURIComponent(code));
      if(invite.member){await refresh();return;}
      $('quiz-start').hidden=true;$('friend-lobby').hidden=false;$('invite-controls').hidden=true;
      $('lobby-title').textContent=invite.host+' invited you';$('lobby-players').textContent=invite.difficulty+' · Friend Duel';
      $('lobby-status').textContent=invite.joinable?'No XP, rating or Solo stats are affected.':'This invitation is no longer available.';
      $('friend-join').hidden=!invite.joinable;
    }else $('start').disabled=false;
  }
  init().catch(e=>error(e.message));
})();
