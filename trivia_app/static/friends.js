/* Friend Duel owns no score calculation or rewards. The server serializes both
 * answers; this module only presents its snapshots and stadium animations. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),page=document.querySelector('[data-page="friend"]');
  if(!page)return;
  const stadium=globalThis.PointsStadium,terminal=s=>['FINISHED','ABANDONED'].includes(s?.phase);
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  let code=page.dataset.invite,user=null,room=null,busy=false,polling=false,offset=0,renderKey='',startRequest=null,pending=null;
  let entered=false,introducing=false,presentation=0,role=null,animation=Promise.resolve(),finished=false,shareCard=null,openTimer=null;
  const animated=new Set();
  function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
  async function api(path,body){
    const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();if(!response.ok){const e=new Error(typeof data.detail==='string'?data.detail:'Unable to load the duel.');e.status=response.status;throw e;}return data;
  }
  const roomPath=()=>`friends/rooms/${encodeURIComponent(code)}`;
  function remember(value){code=value;history.replaceState(null,'',code?'/friends/'+encodeURIComponent(code):'/friends');}
  function gate(){
    $('quiz-start').hidden=true;$('mode-auth').hidden=false;
    const next=encodeURIComponent(location.pathname);
    $('mode-signin').href='/account?next='+next;$('mode-register').href='/account?mode=register&next='+next;
  }
  function scoreboard(s){
    $('shootout-board').hidden=s.phase==='LOBBY'||terminal(s)&&!entered;
    for(const [id,seat] of [['player',s.me],['opponent',1-s.me]]){
      $('score-'+id).textContent=String(s.score[seat]);
      const shots=s.history.filter(r=>r.shooter===seat&&r.outcome!=='replay');
      const count=Math.max(5,...s.attempts),indices=Array.from({length:count},(_,i)=>i).filter(i=>count<=7||i<5||i>=count-2);
      $('kicks-'+id).replaceChildren(...indices.map(i=>{
        const shot=shots[i],result=!shot?'pending':shot.outcome==='goal'?'goal':'miss';
        const el=node('span',undefined,'shootout-kick '+result);el.setAttribute('role','img');el.setAttribute('aria-label',`Penalty ${i+1}: ${result}`);return el;
      }));
    }
    $('shootout-round').textContent=terminal(s)?'Full time':Math.min(...s.attempts)>=5?'Sudden death':`Round ${s.round?.pair||1} / 5`;
    stadium?.hud?.({score:`${s.score[s.me]} : ${s.score[1-s.me]}`});
  }
  function lobby(s){
    $('friend-lobby').hidden=false;$('quiz-start').hidden=true;
    $('lobby-title').textContent='Friend Duel';$('lobby-players').textContent=s.players.map(p=>p.name+(p.ready?' · Ready':'')).join(' vs ');
    $('lobby-status').textContent=s.players.length<2?'Send the link to your friend.':s.players[s.me].ready?'Waiting for your friend to get ready.':'Both players must be ready to start.';
    $('invite-link').value=location.origin+'/friends/'+code;
    $('friend-ready').hidden=s.players.length<2;$('friend-ready').disabled=busy||s.players[s.me].ready;
    $('friend-leave').hidden=false;$('friend-join').hidden=true;$('invite-controls').hidden=false;
    if(entered){
      $('selection').hidden=true;$('quiz-run').hidden=false;$('summary').hidden=true;$('question-panel').hidden=false;
      $('question-title').textContent=introducing?'Entering the stadium...':'Waiting for your friend';
      $('choices').replaceChildren();$('feedback').textContent='The duel starts when both players are ready.';
      $('timer').parentElement.hidden=true;$('next').hidden=true;
    }
  }
  // Queue one animation per resolved question. A fresh server-open question
  // always takes priority over old presentation, including after reconnecting.
  function present(s){
    if(!stadium||s.phase==='LOBBY')return;
    const epoch=presentation,r=s.round,desired=(r?.shooter??s.initial_shooter)===s.me?'shooter':'keeper';
    if(!entered&&terminal(s)){stadium.leave();return;}
    animation=animation.catch(()=>{}).then(async()=>{
      if(epoch!==presentation)return;
      if(!entered){entered=true;role=desired;await stadium.enter(role,{intro:false,maxDurationMs:0});}
      if(epoch!==presentation)return;
      if(role!==desired){role=desired;stadium.reset();await stadium.enter(role,{intro:false});}
      if(epoch!==presentation)return;
      if(r?.outcome&&!animated.has(r.id)){
        animated.add(r.id);
        if(r.outcome!=='replay')await stadium.shot(r.outcome,globalThis.PenaltyShots?.plan(r.outcome,code+':'+r.id));
      }
      if(epoch!==presentation)return;
      if(terminal(s)&&!finished){
        finished=true;$('question-panel').hidden=true;$('summary').hidden=false;
        await stadium.finish?.();
        if(s.winner!==null)globalThis.PointsAudio?.play(s.winner===s.me?'win':'loss');
        $('result-heading').focus({preventScroll:true});
      }else if(s.phase==='ANSWERING')stadium.skip();
    }).catch(()=>{stadium.leave();if(terminal(room)){$('question-panel').hidden=true;$('summary').hidden=false;}});
  }
  async function prepareShare(s){
    shareCard?.dispose();shareCard=null;$('share-result').disabled=true;
    const winner=s.winner===null?null:s.winner===s.me?'player':'opponent';
    const shotList=s.history.filter(r=>r.outcome!=='replay');
    const shareRun={mode:'friend',difficulty:s.difficulty,phase:s.phase,total_xp:0,correct:s.stats[s.me].correct,
      review:s.history,rules:{questions:s.history.length},multiplier:1,opponent:s.players[1-s.me]?.name,
      shootout:{player:s.score[s.me],opponent:s.score[1-s.me],winner,attempts:shotList.map(r=>({side:r.shooter===s.me?'player':'opponent',goal:r.outcome==='goal'}))}};
    try{
      const card=await globalThis.PointsResultShare.prepare(shareRun,user,location.origin);
      if(room?.run_id!==s.run_id){card.dispose();return;}
      shareCard=card;$('share-preview').src=card.imageUrl;$('share-download').href=card.imageUrl;$('share-link').value=card.data.url;$('share-result').disabled=false;
    }catch{$('share-status').textContent='Result card unavailable. You can still share the game link.';}
  }
  function summary(s){
    $('result-heading').textContent=s.winner===null?'Duel ended':s.winner===s.me?'You won the duel!':`${s.players[s.winner].name} wins`;
    const reason={resigned:'Forfeit',disconnect_forfeit:'Connection forfeit',inactivity:'Inactivity',time_limit:'Session expired',question_pool_exhausted:'No unused questions remain'}[s.reason];
    $('result-completion').textContent=`${s.score[s.me]} : ${s.score[1-s.me]}${reason?' · '+reason:''}`;
    const entries=[[`${s.stats[s.me].correct} / ${s.history.length}`,'Correct answers'],['Friendly','No XP or rating']];
    $('result-metrics').replaceChildren(...entries.map(([value,label])=>{const e=node('div',undefined,'metric');e.append(node('strong',value),node('span',label));return e;}));
    $('result-level').hidden=true;$('guest-benefits').hidden=true;$('another').hidden=false;$('another').textContent='New friend duel';
    $('summary-account').textContent='View profile';$('result-review').hidden=true;
    $('summary').hidden=entered&&!finished;$('question-panel').hidden=!entered||finished;
    prepareShare(s);
  }
  function render(s){
    if(room&&room.run_id===s.run_id&&s.server_now<room.server_now)return;
    room=s;offset=s.server_now-Date.now();
    // Fetch at the shared opening instant, not at each tab's arbitrary polling
    // phase. The server still withholds question/answer data before that time.
    clearTimeout(openTimer);
    if(s.phase==='COUNTDOWN')openTimer=setTimeout(refresh,Math.max(20,s.round.opens_at-s.server_now+20));
    const key=[s.phase,s.version,s.round?.id,s.round?.own_option,busy].join(':');
    if(key===renderKey)return;renderKey=key;scoreboard(s);$('retry').hidden=true;
    if(s.phase==='LOBBY'){lobby(s);return;}
    $('selection').hidden=true;$('quiz-run').hidden=false;
    const done=terminal(s),active=s.phase==='ANSWERING',r=s.round;
    page.classList.toggle('shootout-active',!done);page.classList.toggle('shootout-finished',done);
    $('run-category').textContent=s.players[1-s.me]?.name||'Friend Duel';
    $('run-position').textContent=r?(r.shooter===s.me?'Shooting':'Defending')+' · Round '+r.pair:'';
    $('run-xp').textContent='Friendly';$('question-title').textContent=s.question?.text||(done?'Duel ended':r?.shooter===s.me?'Get ready to shoot':'Get ready to save');
    $('timer').parentElement.hidden=!active&&s.phase!=='COUNTDOWN';$('choices').replaceChildren();
    for(const option of s.question?.options||[]){
      const b=node('button',option.text);b.disabled=!active||busy||r.own_option!==null;
      b.classList.toggle('chosen',option.id===r.own_option);
      if(r.outcome)b.classList.toggle('correct',option.id===s.question.correct);
      b.addEventListener('click',()=>answer(option.id));$('choices').append(b);
    }
    let feedback=active&&r?.own_option!==null?'Answer locked. Waiting for your friend...':'';
    if(r?.outcome){
      const bothWrong=r.answers.every(a=>!a?.correct);
      feedback=r.outcome==='replay'?(bothWrong?'Neither answer was correct. Replay with a new question.':'Both correct, too close to call. Replay with a new question.'):(r.outcome==='goal'?'Goal. ':'Saved. ')+(s.question?.explanation||'');
    }
    $('feedback').textContent=feedback;$('next').hidden=true;$('leave').hidden=done;
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
    try{const s=await api('friends/rooms',startRequest);remember(s.code);busy=false;render(s);startRequest=null;}
    catch(e){error(e.message);}finally{busy=false;$('start').disabled=false;}
  });
  $('friend-join').addEventListener('click',()=>command('join'));
  $('friend-ready').addEventListener('click',async()=>{
    if(busy||introducing)return;introducing=true;entered=true;$('friend-ready').disabled=true;
    role=room.initial_shooter===room.me?'shooter':'keeper';lobby(room);
    try{await stadium?.enter(role,{intro:true});introducing=false;await command('ready');}
    catch(e){introducing=false;error(e.message);}
  });
  for(const id of ['friend-leave','leave'])$(id).addEventListener('click',()=>command('leave'));
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
    presentation++;stadium?.leave();remember('');room=null;role=null;entered=finished=introducing=false;renderKey='';animated.clear();shareCard?.dispose();shareCard=null;
    page.classList.remove('shootout-active','shootout-finished');$('shootout-board').hidden=true;$('quiz-run').hidden=true;$('selection').hidden=false;$('friend-lobby').hidden=true;$('quiz-start').hidden=false;error();
  });
  $('share-result').addEventListener('click',async()=>{
    if(!shareCard)return;
    try{if(await globalThis.PointsResultShare.share(shareCard,navigator)!=='fallback')return;}catch{}
    $('share-options').hidden=false;$('share-dialog').showModal();
  });
  $('share-close').addEventListener('click',()=>$('share-dialog').close());
  $('share-copy').addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText(shareCard.data.text+'\n'+shareCard.data.url);$('share-dialog-status').textContent='Result and link copied.';}
    catch{$('share-link').select();}
  });
  setInterval(()=>{if(room&&!terminal(room)&&!document.hidden)refresh();},1000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&room)refresh();});
  setInterval(()=>{
    if(!room?.round)return;
    const countdown=room.phase==='COUNTDOWN',active=room.phase==='ANSWERING',r=room.round;
    const remaining=Math.max(0,(countdown?r.opens_at:r.deadline)-Date.now()-offset)/1000;
    $('seconds').textContent=(countdown?'Ready in ':'')+remaining.toFixed(1)+' s';$('timer').max=countdown?4:15;$('timer').value=remaining;
    stadium?.hud?.({clock:active?remaining.toFixed(1)+' s':''});
    if(active&&remaining===0)for(const b of $('choices').children)b.disabled=true;
  },100);
  async function init(){
    $('start').textContent='Create invitation';$('quiz-rules').textContent='5 penalties each · 15 seconds · No XP or rating';$('availability').hidden=true;
    try{user=await api('players/me');}catch(e){if(e.status===401){gate();return;}throw e;}
    if(user.preferences)globalThis.PointsPreferences?.set(user.preferences);
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
