(function(){
  'use strict';
  const $=id=>document.getElementById(id),page=document.querySelector('.solo-page');
  const node=(tag,text,className)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;};
  function error(message){$('error').textContent=message||'';$('error').hidden=!message;}
  async function api(path,body,method){
    const response=await fetch(path,{method:method||(body===undefined?'GET':'POST'),headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok){const e=new Error(typeof data.detail==='string'?data.detail:'Please check your details and try again.');e.status=response.status;throw e;}
    return data;
  }
  function metrics(target,entries){$(target).replaceChildren(...entries.map(([value,label])=>{const d=node('div',undefined,'metric');d.append(node('strong',String(value)),node('span',label));return d;}));}
  const title=value=>value.charAt(0).toUpperCase()+value.slice(1);
  async function currentUser(){try{return await api('/api/players/me');}catch(e){if(e.status===401)return null;throw e;}}
  let teamChangeAt=null;
  function teamChangeStatus(){
    const locked=teamChangeAt&&Date.parse(teamChangeAt)>Date.now();
    $('add-team').disabled=Boolean(locked);
    $('team-change-note').textContent=locked
      ?`You can change teams again on ${new Date(teamChangeAt).toLocaleString('en-GB',{timeZone:'UTC',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})} UTC.`
      :'After joining, switching or leaving a team, you must wait 3 days before changing again.';
  }

  function showProfile(p,own){
    $('notice').textContent='';$('authentication').hidden=true;$('profile').hidden=false;$('own-profile').hidden=!own;
    $('profile-name').textContent=p.username;$('profile-bio').textContent=p.bio;
    const badge=globalThis.PointsUI?.badge(p.club);
    $('profile-team').replaceChildren(...(badge?[badge]:[]));
    const record=p.stats||{wins:0,losses:0,played:0,win_rate:null};
    metrics('profile-record',[[record.wins,'Wins'],[record.losses,'Losses'],[record.win_rate===null?'—':`${Number(record.win_rate).toFixed(1)}%`,'Win rate'],[record.played,'Shootouts']]);
    $('add-team').textContent=p.club?'Change team':'Add team';$('profile-team-select').dataset.selected=p.club?.team_id||'';
    metrics('profile-metrics',[[p.total_xp,'Total XP'],[p.level,'Level'],[p.streak.current,'Daily streak'],[p.streak.longest,'Longest streak']]);
    $('level-label').textContent=p.next_level_xp===null?'Maximum level':`${p.next_level_xp-p.total_xp} XP to level ${p.level+1}`;
    $('level-progress').max=p.next_level_xp===null?1:p.next_level_xp-p.level_xp;
    $('level-progress').value=p.next_level_xp===null?1:p.total_xp-p.level_xp;
    $('daily-status').textContent='';$('daily-status').hidden=true;
    if(own){teamChangeAt=p.team_change?.next_change_at||null;teamChangeStatus();$('bio').value=p.bio;$('profile-username').value=p.username;$('account-email').value=p.email||'';$('public-profile').href='/u/'+encodeURIComponent(p.username);globalThis.PointsAccountSettings?.setProfile(p);}
  }
  async function accountPage(){
    const params=new URLSearchParams(location.search||''),next=params.get('next');
    const returnTo=next&&/^\/(daily|penalties|friends(?:\/[A-Za-z0-9_-]{32,64})?)$/.test(next)?next:null;
    const publicName=page.dataset.username;
    if(publicName){showProfile(await api('/api/players/profiles/'+encodeURIComponent(publicName)),false);return;}
    const user=await currentUser();if(user&&returnTo){location.href=returnTo;return;}if(user)showProfile(user,true);else{$('notice').textContent='';$('authentication').hidden=false;}
    setInterval(()=>{if(!$('own-profile').hidden)teamChangeStatus();},60000);
    function authMode(){
      const register=document.querySelector('input[name="auth-mode"]:checked').value==='register';
      $('login-field').hidden=register;$('identifier').disabled=register;
      $('registration-fields').hidden=!register;$('email').disabled=!register;$('username').disabled=!register;
      $('authenticate').textContent=register?'Create account':'Sign in';$('password').autocomplete=register?'new-password':'current-password';error('');
    }
    document.querySelectorAll('input[name="auth-mode"]').forEach(input=>input.addEventListener('change',authMode));
    if(params.get('mode')==='register')document.querySelector('input[name="auth-mode"][value="register"]').checked=true;
    authMode();globalThis.PointsAccountSettings?.resetView();
    $('auth-form').addEventListener('submit',async e=>{
      e.preventDefault();error('');$('authenticate').disabled=true;
      try{const mode=document.querySelector('input[name="auth-mode"]:checked').value;
        const credentials=mode==='register'?{username:$('username').value,email:$('email').value,password:$('password').value}:{identifier:$('identifier').value,password:$('password').value};
        const p=await api('/api/players/'+mode,credentials);$('password').value='';if(returnTo){location.href=returnTo;return;}showProfile(p,true);
      }catch(e){error(e.message);}finally{$('authenticate').disabled=false;}
    });
    $('profile-edit').addEventListener('submit',async e=>{
      e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;error('');
      try{showProfile(await api('/api/players/me',{bio:$('bio').value,username:$('profile-username').value},'PATCH'),true);$('notice').textContent='Profile saved.';}
      catch(e){error(e.message);}finally{button.disabled=false;}
    });
    $('signout').addEventListener('click',async()=>{try{await api('/api/players/logout',{});globalThis.PointsPreferences?.clear();location.href='/account';}catch(e){error(e.message);}});
    const closeTeam=()=>{$('team-edit').hidden=true;$('add-team').setAttribute('aria-expanded','false');};
    $('cancel-team').addEventListener('click',closeTeam);
    $('add-team').addEventListener('click',async()=>{
      $('add-team').disabled=true;error('');
      try{
        const data=await api('/api/players/teams');
        $('profile-team-select').replaceChildren(...[{team_id:'',name:'No team'},...data.teams].map(t=>{const o=node('option',t.name);o.value=String(t.team_id);return o;}));
        $('profile-team-select').value=$('profile-team-select').dataset.selected;
        globalThis.PointsUI?.teamPicker(data.teams,$('profile-team-select'),$('team-options'));
        $('team-edit').hidden=false;$('add-team').setAttribute('aria-expanded','true');$('team-options').querySelector('input:checked')?.focus();
      }catch(e){error(e.message);}finally{teamChangeStatus();}
    });
    $('team-edit').addEventListener('submit',async e=>{
      e.preventDefault();$('save-team').disabled=true;error('');
      try{showProfile(await api('/api/players/me/team',{team_id:$('profile-team-select').value?Number($('profile-team-select').value):null},'PUT'),true);closeTeam();$('notice').textContent='Team updated.';}
      catch(e){error(e.message);if(e.status===409){try{const latest=await currentUser();if(latest)showProfile(latest,true);closeTeam();}catch{}}}finally{$('save-team').disabled=false;}
    });
    $('email-edit').addEventListener('submit',async e=>{
      e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;error('');
      try{const p=await api('/api/players/email',{email:$('account-email').value,password:$('email-password').value},'PUT');$('email-password').value='';showProfile(p,true);$('notice').textContent='Sign-in email saved.';}
      catch(e){error(e.message);}finally{button.disabled=false;}
    });
  }

  async function soloPage(){
    const daily=page.dataset.mode==='daily',base=daily?'/api/daily':'/api/solo',minimum=daily?1:10;
    let wonToday=false;
    let user=null,counts={},rules=null,trialAvailable=true,run=null,offset=0,polling=false,busy=false,rendered='',pending=null,startRequest=null;
    let catalogReady=false,catalogLoading=false,catalogReset=Infinity;
    const animatedShots=new Set(),scene=globalThis.PenaltyScene;
    const stadium=globalThis.PointsStadium;
    let stadiumRun=null,stadiumWaiting=false,presentation=0,presented='';
    const resultShare=globalThis.PointsResultShare;
    let shareCard=null,shareVersion=0,reviewPosition=0;
    // Detail views are separate dialogs, so long shootouts never grow the
    // result card. Pagination is presentation-only and uses server review data.
    function reviewAnswer(position){
      const answers=run?.review||[];
      reviewPosition=Math.max(0,Math.min(position,answers.length-1));
      const answer=answers[reviewPosition];
      $('review').replaceChildren();
      if(answer){
        const block=node('article',undefined,'review-item');
        block.append(node('h3',answer.text),node('p',`${answer.option_id===null?'Timed out':answer.is_correct?'Correct':'Incorrect'} · ${answer.explanation}`));
        $('review').append(block);
      }
      $('review-position').textContent=answers.length?`${reviewPosition+1} / ${answers.length}`:'No answers';
      $('review-previous').disabled=reviewPosition===0;
      $('review-next').disabled=reviewPosition>=answers.length-1;
    }
    function shareFallback(){
      $('share-options').hidden=false;
      if(!$('share-dialog').open)$('share-dialog').showModal();
    }
    function clearShare(){
      shareVersion++;shareCard?.dispose();shareCard=null;
      $('share-result').disabled=true;$('share-options').hidden=true;
      $('share-preview').removeAttribute('src');$('share-download').removeAttribute('href');
      $('share-status').textContent='';
      $('share-dialog-status').textContent='';
      if($('share-dialog').open)$('share-dialog').close();
      if($('review-dialog').open)$('review-dialog').close();
    }
    async function prepareShare(){
      clearShare();const own=shareVersion;
      if(!resultShare)return;
      try{
        const card=await resultShare.prepare(run,user,location.origin);
        if(own!==shareVersion){card.dispose();return;}
        shareCard=card;$('share-preview').src=card.imageUrl;
        $('share-download').href=card.imageUrl;$('share-download').download=card.file.name;
        $('share-link').value=card.data.url;$('share-result').disabled=false;
      }catch{if(own===shareVersion)$('share-status').textContent='Could not prepare the result card. Refresh to retry.';}
    }
    async function shootoutView(){
      const key=`${run.run_id}:${run.position}:${run.phase}`;
      if(presented===key)return;presented=key;
      const own=++presentation,id=run.run_id,done=['FINISHED','ABANDONED'].includes(run.phase);
      const live=stadiumRun===id,answer=run.review.find(a=>a.position===run.position);
      const current=()=>own===presentation&&run?.run_id===id;
      if(done&&!live){stadium.leave();return;}
      stadiumWaiting=true;$('next').disabled=true;
      if(done){$('summary').hidden=true;$('question-panel').hidden=false;}
      try{
        if(!live){
          stadiumRun=id;
          await stadium.enter(run.role||'shooter',{intro:run.phase==='READY',maxDurationMs:run.phase==='READY'?Infinity:0});
        }
        if(!current())return;
        if(answer){
          const shotKey=`${id}:${run.position}`;
          if(!animatedShots.has(shotKey)){
            animatedShots.add(shotKey);
            await stadium.shot(answer.outcome,globalThis.PenaltyShots?.plan(answer.outcome,shotKey));
          }
          if(!current())return;
        }
        if(done){
          $('question-panel').hidden=true;$('summary').hidden=false;
          await stadium.finish?.();
          if(current()){
            $('result-heading').focus({preventScroll:true});
            const winner=run.shootout.winner;
            if(winner)globalThis.PointsAudio?.play(winner==='player'?'win':'loss');
          }
        }else if(run.phase==='REVIEW'){
          // Camera travel happens before Next sends the request that opens the clock.
          stadium.reset();await stadium.enter(run.shootout.next_role,{intro:false});
        }else if(run.phase==='ANSWERING')stadium.skip();
      }finally{
        if(current()){stadiumWaiting=false;$('next').disabled=busy;}
      }
    }
    function stadiumView(){
      if(!stadium)return;
      if(run.shootout){const task=shootoutView(),token=presentation;task.catch(()=>{if(token!==presentation)return;stadiumWaiting=false;stadium.leave();$('summary').hidden=!['FINISHED','ABANDONED'].includes(run.phase);$('next').disabled=busy;});return;}
      if(['FINISHED','ABANDONED'].includes(run.phase)){stadium.leave();stadiumWaiting=false;return;}
      if(stadiumRun===run.run_id){
        // A resumed/server-open question always wins over presentation.
        if(run.phase==='ANSWERING'){stadium.skip();stadiumWaiting=false;}
        return;
      }
      stadiumRun=run.run_id;
      const id=run.run_id,intro=run.phase==='READY';stadiumWaiting=intro;
      if(intro)$('next').disabled=true;
      // READY has no answer deadline. Finishing the intro only unlocks Next;
      // it never fetches a question or starts the server's 15-second clock.
      stadium.enter('shooter',{intro,maxDurationMs:intro?Infinity:0}).finally(()=>{
        if(run?.run_id!==id)return;stadiumWaiting=false;$('next').disabled=busy;
      });
    }
    function pitch(){
      const score=run?.shootout;
      const finished=run&&['FINISHED','ABANDONED'].includes(run.phase);
      $('shootout-board').hidden=!score||(finished&&stadiumRun!==run.run_id);
      if(!scene)return;
      if(score){
        $('penalty-score').textContent=`${score.player} : ${score.opponent}`;
        stadium?.hud?.({score:$('penalty-score').textContent});
        for(const side of ['player','opponent']){
          $('score-'+side).textContent=String(score[side]);
          const attempts=score.attempts.filter(a=>a.side===side),count=Math.max(5,score.kicks.player,score.kicks.opponent);
          // Keep the original five plus the latest sudden-death rounds on narrow screens.
          const indices=Array.from({length:count},(_,i)=>i).filter(i=>count<=7||i<5||i>=count-2);
          $('kicks-'+side).replaceChildren(...indices.map(i=>{
            const a=attempts[i],ball=node('span',undefined,'shootout-kick '+(!a?'pending':a.goal?'goal':'miss'));
            const label=`${side==='player'?'You':'Opponent'}, penalty ${i+1}: ${!a?'not taken':a.goal?'goal':'missed'}`;
            ball.title=label;ball.setAttribute('aria-label',label);ball.setAttribute('role','img');return ball;
          }));
        }
        $('shootout-round').textContent=score.winner?'Full time':score.sudden_death?'Sudden death':`Round ${Math.min(5,score.round)} / 5`;
        return;
      }
      $('penalty-score').textContent=`${run?.correct||0} / 10`;
      stadium?.hud?.({score:$('penalty-score').textContent});
      $('solo-attempts').replaceChildren(...Array.from({length:10},(_,i)=>{
        const answer=run?.review.find(a=>a.position===i+1),outcome=!answer?'pending':answer.option_id===null?'miss':answer.is_correct?'goal':'save';
        const shot=node('span',String(i+1),'solo-attempt '+outcome);shot.title=`Shot ${i+1}: ${outcome}`;shot.setAttribute('aria-label',shot.title);return shot;
      }));
      const answer=run?.review.find(a=>a.position===run.position),key=run&&`${run.run_id}:${run.position}`;
      if(answer&&!animatedShots.has(key)){
        animatedShots.add(key);scene.shot(answer.option_id===null?'miss':answer.is_correct?'goal':'save',key);
      }else if(!answer)scene.reset();
    }
    function storage(value){try{const key=(daily?'points.daily.':'points.solo.')+(user?.username||'trial');if(value===null)localStorage.removeItem(key);else if(value!==undefined)localStorage.setItem(key,value);return localStorage.getItem(key);}catch{return null;}}
    const difficulty=()=>daily?'mixed':document.querySelector('input[name="difficulty"]:checked').value;
    function selection(){
      const count=counts[difficulty()]||0;
      if(daily){
        $('availability').hidden=false;
        $('availability').textContent=catalogLoading?'Preparing Daily Challenge...':wonToday?'Today\'s challenge is won. Come back tomorrow.':catalogReady&&count<1?'No unused daily questions remain. Come back tomorrow.':!catalogReady?'Daily Challenge is not available yet.':'One daily pool: 10 Easy, 20 Medium and 20 Hard questions.';
        $('weekly-reset').hidden=!catalogReady;
        $('start').disabled=!catalogReady||count<1||wonToday||busy;$('start').textContent='Play Daily Challenge';
        $('trial-note').hidden=true;$('quiz-rules').textContent='15 seconds each · 10 / 20 / 30 XP per correct answer · One daily win';return;
      }
      $('availability').textContent=catalogLoading?'Preparing shootout...':!catalogReady?'Could not load shootouts. Refresh to try again.':count>=10?'':'No new shootout at this difficulty right now. Try another difficulty.';
      $('availability').hidden=catalogReady&&count>=10;
      $('weekly-reset').hidden=!catalogReady||count>=10||!$('weekly-reset').textContent;
      $('start').disabled=!catalogReady||count<10||busy;$('start').textContent=user?'Start shootout':'Play as guest';
      $('trial-note').hidden=Boolean(user);
      $('quiz-rules').textContent=`${rules?.format==='shootout'?'5 penalties each · Sudden death if tied':`${rules?.questions||10} questions`} · ${(rules?.answer_ms||15000)/1000} seconds each · ${rules?.xp_by_difficulty[difficulty()]||10} XP per correct answer`;
    }
    async function loadCatalog(){
      catalogReady=false;catalogLoading=true;selection();
      try{
        const catalog=await api(base+'/catalog');
        if(daily){counts={mixed:catalog.remaining};rules=catalog.rules;wonToday=catalog.won_today;catalogReset=Date.parse(catalog.resets_at);$('weekly-reset').textContent='New daily pool at 00:00 UTC. Played questions stay excluded until Monday.';catalogReady=true;return;}
        // Keep eligibility checks internal; every new game uses all clubs and topics.
        counts=catalog.topics.find(t=>t.code==='ALL')?.counts_by_team.ALL||{};rules=catalog.rules;
        catalogReset=catalog.resets_at?Date.parse(catalog.resets_at):Infinity;
        $('weekly-reset').textContent=catalog.resets_at?`Question pool resets ${catalog.resets_at.slice(0,10)} at 00:00 UTC`:'';
        for(const level of ['easy','medium','hard']){
          $(level+'-rate').textContent=`${rules.xp_by_difficulty[level]} XP / answer`;
          $(level+'-perfect').textContent=rules.bonus_mode==='win'?`Win: ${rules.win_multipliers[level]}x XP`:rules.format==='shootout'?`Perfect game: ${rules.perfect_multipliers[level]}x XP`:`10/10: ${10*rules.xp_by_difficulty[level]*rules.perfect_multipliers[level]} XP`;
        }
        catalogReady=true;
      }finally{catalogLoading=false;selection();}
    }
    function render(next){
      if(run&&run.run_id===next.run_id&&next.server_now<run.server_now)return;
      run=next;offset=next.server_now-Date.now();storage(['FINISHED','ABANDONED'].includes(run.phase)?null:run.run_id);
      const key=`${run.run_id}:${run.position}:${run.phase}:${run.review.length}`;
      if(key===rendered)return;rendered=key;
      pitch();
      $('selection').hidden=true;$('quiz-run').hidden=false;$('retry').hidden=true;
      const done=['FINISHED','ABANDONED'].includes(run.phase),active=run.phase==='ANSWERING';
      $('question-panel').hidden=done;
      $('quiz-run').setAttribute('aria-labelledby',done?'result-heading':'question-title');
      page.classList.toggle('shootout-finished',done);
      if($('timer').parentElement)$('timer').parentElement.hidden=!active;
      page.classList.toggle('shootout-active',!done);
      $('run-category').textContent=`${run.category.topic_label||'Mixed topics'} · ${run.category.label} · ${title(run.difficulty)}`;
      $('run-position').textContent=run.shootout?`${run.role==='keeper'?'Defending':'Shooting'} · Penalty ${Math.max(1,Math.ceil(run.position/2))}`:`Shot ${Math.max(1,run.position)} / 10`;$('run-xp').textContent=`${run.total_xp} ${run.is_trial?'trial XP':'XP'}`;
      $('question-title').textContent=run.question?.text||'Ready for your first question?';
      $('choices').replaceChildren();
      const answer=run.review.find(a=>a.position===run.position);
      (run.question?.options||[]).forEach(option=>{
        const button=node('button',option.text);button.disabled=!active||busy;
        if(answer){button.classList.toggle('correct',option.id===answer.correct);button.classList.toggle('incorrect',option.id===answer.option_id&&!answer.is_correct);button.classList.toggle('chosen',option.id===answer.option_id);
          if(option.id===answer.option_id)button.append(node('small','Your answer','answer-selection'));}
        button.addEventListener('click',()=>submit(option.id));$('choices').append(button);
      });
      // Puvod odpovedi patri do Studia. Hrac vidi pouze vysledek a vysvetleni.
      $('feedback').textContent=answer?(answer.option_id===null?'Time is up. ':answer.is_correct?`Correct. +${answer.xp??run.rules.xp_per_correct} ${run.is_trial?'trial XP':'XP'}. `:'Incorrect. ')+answer.explanation:'';
      $('next').hidden=!['READY','REVIEW'].includes(run.phase);$('next').textContent=run.phase==='READY'?'Take first shot':run.shootout?.next_role==='keeper'?'Face next penalty':'Next shot';
      $('leave').hidden=done;$('another').hidden=!done;$('summary').hidden=!done;
      $('another').textContent='New shootout';$('guest-benefits').hidden=!done||!run.is_trial;
      if(done){
        prepareShare();
        $('share-status').textContent='';
        const total=run.shootout?run.review.length:run.rules.questions;
        $('result-heading').textContent=run.shootout?.winner?(run.shootout.winner==='player'?'You won the shootout!':'Opponent wins'):run.perfect?'Perfect shootout!':run.phase==='ABANDONED'?'Shootout ended':'Shootout complete';
        $('result-completion').textContent=run.shootout?`${run.shootout.player} : ${run.shootout.opponent} · ${run.review.length} ${run.review.length===1?'penalty':'penalties'}${run.end_reason==='question_pool_exhausted'?' · No unused questions remain; no winner declared.':''}`:`${run.review.filter(a=>a.option_id!==null).length} answered · ${run.review.filter(a=>a.option_id===null).length} timed out · ${total-run.review.length} unplayed`;
        metrics('result-metrics',[[`${run.correct} / ${total}`,'Correct answers'],[run.total_xp,run.is_trial?'Trial XP (not saved)':'XP earned'],[run.bonus_xp,run.rules.bonus_mode==='win'?'Win bonus':'Perfect bonus'],[run.multiplier+'x','Multiplier']]);
        if(daily){
          $('result-heading').textContent=run.won?'Daily Challenge won!':run.phase==='ABANDONED'?'Challenge ended':'Try again tomorrow';
          if(!run.won&&run.phase==='FINISHED')$('result-heading').textContent='Opponent wins';
          if(run.end_reason==='daily_pool_exhausted')$('result-completion').textContent+=' · Daily pool completed';
          if(run.end_reason==='daily_reset')$('result-completion').textContent+=' · Daily reset';
          metrics('result-metrics',[[`${run.correct} / ${total}`,'Correct answers'],[run.total_xp,'XP earned']]);
          $('another').textContent='Back to Daily Challenge';
        }
        const p=run.player_progress;
        $('result-level').hidden=!p||run.is_trial;
        if(p&&!run.is_trial){
          const max=p.next_level_xp===null;
          $('result-level-label').textContent=`Level ${p.level} · ${p.total_xp} total XP`;
          $('result-level-progress').max=max?1:p.next_level_xp-p.level_xp;
          $('result-level-progress').value=max?1:p.total_xp-p.level_xp;
          $('result-level-remaining').textContent=max?'Maximum level':`${Math.max(0,p.next_level_xp-p.total_xp)} XP to level ${p.level+1}`;
        }
        $('summary-account').textContent=run.is_trial?'Sign in':'View profile';$('summary-account').href='/account';
        $('result-review').disabled=run.review.length===0;
        reviewAnswer(0);
        currentUser().then(p=>{if(p)user=p;}).catch(()=>{});
      }
      if(active)$('question-title').focus({preventScroll:true});
      stadiumView();
      if(done&&!stadiumWaiting)$('result-heading').focus({preventScroll:true});
    }
    async function refresh(){
      if(!run||polling)return;polling=true;
      const id=run.run_id,own=presentation;
      try{const next=await api(base+'/runs/'+id);if(run?.run_id!==id||own!==presentation)return;if(!$('retry').hidden)error('');render(next);$('retry').hidden=true;}
      catch(e){if(run?.run_id!==id||own!==presentation)return;error(e.message);rendered='';$('retry').hidden=false;for(const b of $('choices').children)b.disabled=true;}
      finally{polling=false;}
    }
    async function command(path,body){
      if(busy||(path==='next'&&stadiumWaiting))return;busy=true;error('');for(const b of $('choices').children)b.disabled=true;$('next').disabled=true;
      try{const next=await api(`${base}/runs/${run.run_id}/${path}`,body);busy=false;rendered='';render(next);pending=null;}
      catch(e){error(e.message);busy=false;rendered='';await refresh();}
      finally{busy=false;$('next').disabled=stadiumWaiting;}
    }
    function submit(option){
      if(busy||run?.phase!=='ANSWERING')return;
      if(!pending||pending.position!==run.position)pending={position:run.position,option_id:option,request_id:crypto.randomUUID()};
      return command('answers',pending);
    }
    $('next').addEventListener('click',()=>command('next',{previous:run.position}));
    $('leave').addEventListener('click',()=>command('leave',{}));
    $('retry').addEventListener('click',()=>{rendered='';refresh();});
    $('result-review').addEventListener('click',()=>{reviewAnswer(0);$('review-dialog').showModal();});
    $('review-previous').addEventListener('click',()=>reviewAnswer(reviewPosition-1));
    $('review-next').addEventListener('click',()=>reviewAnswer(reviewPosition+1));
    $('review-close').addEventListener('click',()=>$('review-dialog').close());
    $('share-close').addEventListener('click',()=>$('share-dialog').close());
    $('share-result').addEventListener('click',async()=>{
      if(!shareCard)return;
      const card=shareCard;const own=shareVersion;$('share-result').disabled=true;$('share-status').textContent='';
      try{
        // The PNG is already prepared: native share retains click activation.
        const outcome=await resultShare.share(card,navigator);
        if(own!==shareVersion)return;
        if(outcome==='fallback')shareFallback();
        else if(outcome==='shared')$('share-status').textContent='Share completed.';
      }catch{if(own===shareVersion){shareFallback();$('share-dialog-status').textContent='The card and link are ready to share.';}}
      finally{if(own===shareVersion)$('share-result').disabled=false;}
    });
    $('share-copy').addEventListener('click',async()=>{
      if(!shareCard)return;const own=shareVersion;
      try{await navigator.clipboard.writeText(shareCard.data.text+'\n'+shareCard.data.url);if(own===shareVersion)$('share-dialog-status').textContent='Result and link copied.';}
      catch{if(own===shareVersion){$('share-link').focus();$('share-link').select();$('share-dialog-status').textContent='Copy unavailable. The link is selected.';}}
    });
    $('another').addEventListener('click',async()=>{presentation++;presented='';stadium?.leave();stadiumRun=null;stadiumWaiting=false;storage(null);clearShare();run=null;pending=null;startRequest=null;rendered='';if(location.search)history.replaceState(null,'',location.pathname);page.classList.toggle('shootout-active',false);page.classList.toggle('shootout-finished',false);pitch();$('quiz-run').hidden=true;$('selection').hidden=false;error('');try{await loadCatalog();}catch(e){error(e.message);}});
    document.querySelectorAll('input[name="difficulty"]').forEach(r=>r.addEventListener('change',selection));
    $('quiz-start').addEventListener('submit',async e=>{
      e.preventDefault();if(busy||!catalogReady||(counts[difficulty()]||0)<minimum||daily&&wonToday)return;busy=true;selection();error('');
      const category='ALL',topic='ALL',level=difficulty();
      if(!startRequest||startRequest.category!==category||startRequest.topic!==topic||startRequest.difficulty!==level)startRequest={category,topic,difficulty:level,request_id:crypto.randomUUID()};
      try{const next=await api(base+'/runs',daily?{request_id:startRequest.request_id}:startRequest);busy=false;render(next);startRequest=null;}catch(e){error(e.message);if(e.status===409){try{await loadCatalog();}catch(refreshError){error(refreshError.message);}}}finally{busy=false;selection();}
    });
    setInterval(()=>{
      if(!run)return;
      const remaining=run.phase==='ANSWERING'?Math.max(0,run.deadline-Date.now()-offset)/1000:0;
      $('seconds').textContent=remaining.toFixed(1)+' s';$('timer').max=(run.rules.answer_ms||15000)/1000;$('timer').value=remaining;
      stadium?.hud?.({clock:run.phase==='ANSWERING'?remaining.toFixed(1)+' s':''});
      if(run.phase==='ANSWERING'&&remaining===0){for(const b of $('choices').children)b.disabled=true;}
    },100);
    setInterval(()=>{if(run&&run.phase==='ANSWERING'&&!busy)refresh();},1000);
    setInterval(()=>{if(!run&&!busy&&!catalogLoading&&Date.now()+offset>=catalogReset)loadCatalog().catch(e=>error(e.message));},30000);
    pitch();user=await currentUser();if(user?.preferences)globalThis.PointsPreferences?.set(user.preferences);
    if(daily&&!user){$('quiz-start').hidden=true;$('mode-auth').hidden=false;$('mode-signin').href='/account?next=/daily';$('mode-register').href='/account?mode=register&next=/daily';return;}
    await loadCatalog();
    // History links can only resolve through the existing owner-authorized API.
    const requestedRun=new URLSearchParams(location.search||'').get('run');
    if(requestedRun){
      if(!user){error('Sign in to view this result.');return;}
      try{render(await api(base+'/runs/'+encodeURIComponent(requestedRun)));}catch(e){error(e.message);}
      return;
    }
    const active=await api(base+'/active');trialAvailable=active.trial_available!==false;selection();
    // Only the server's active run may auto-resume. Finished games are opened
    // explicitly from History, never resurrected from an old local pointer.
    if(active.run)render(active.run);else storage(null);
  }

  async function difficultyPage(){
    let offset=0,busy=false;
    async function load(){
      if(busy)return;busy=true;error('');
      try{
        const data=await api(`/api/solo/editor/difficulty?offset=${offset}&pending=${$('pending-only').checked}`);
        $('assessments').replaceChildren(...data.questions.map(q=>{
          const form=node('form',undefined,'assessment');form.append(node('small',`${q.question.source.external_id} · ${q.section_name} · ${q.approved?'Approved':'Pending'}`),node('h2',q.question.text),node('p',q.question.options.map(o=>o.text).join(' / ')),node('p',q.question.explanation));
          const label=node('label','Difficulty'),select=node('select');for(const value of ['easy','medium','hard']){const option=node('option',title(value));option.value=value;select.append(option);}select.value=q.difficulty||'medium';label.append(select);
          const reasonLabel=node('label','Editorial rationale'),reason=node('textarea');reason.value=q.reason||'';reason.required=true;reason.minLength=10;reason.maxLength=1000;reasonLabel.append(reason);
          const approvedLabel=node('label','Approved for solo quizzes'),approved=node('input');approved.type='checkbox';approved.checked=q.approved;approvedLabel.append(approved);
          const save=node('button','Save assessment','primary');form.append(label,reasonLabel,approvedLabel,save);
          form.addEventListener('submit',async event=>{event.preventDefault();save.disabled=true;error('');try{await api('/api/solo/editor/difficulty',{release_id:q.release_id,question_id:q.question_id,difficulty:select.value,approved:approved.checked,reason:reason.value});$('notice').textContent='Assessment saved. Existing quizzes keep their original difficulty.';await load();}catch(e){error(e.message);save.disabled=false;}});
          return form;
        }));
        $('page-number').textContent=`Page ${offset/30+1}`;$('previous-page').disabled=offset===0;$('next-page').disabled=data.questions.length<30;
        if(!data.questions.length)$('notice').textContent='No questions in this view.';
      }catch(e){error(e.message);}finally{busy=false;}
    }
    $('pending-only').addEventListener('change',()=>{offset=0;load();});
    $('previous-page').addEventListener('click',()=>{if(!busy){offset=Math.max(0,offset-30);load();}});
    $('next-page').addEventListener('click',()=>{if(!busy){offset+=30;load();}});await load();
  }
  ({solo:soloPage,account:accountPage,difficulty:difficultyPage}[page.dataset.page])().catch(e=>{error(e.message);$('notice').textContent='';});
})();
