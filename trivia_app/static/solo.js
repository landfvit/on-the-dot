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
      ?'You can change teams 3 days after your last change.'
      :'You can change teams once every 3 days.';
  }

  function showProfile(p,own){
    $('notice').textContent='';$('authentication').hidden=true;$('profile').hidden=false;$('own-profile').hidden=!own;
    $('signout').hidden=!own;
    $('profile-name').textContent=p.username;$('profile-bio').textContent=p.bio;
    const badge=globalThis.PointsUI?.badge(p.club);
    $('profile-team').replaceChildren(...(badge?[badge]:[]));
    const record=p.stats||{wins:0,losses:0,played:0,win_rate:null};
    metrics('profile-record',[[record.wins,'Wins'],[record.losses,'Losses'],[record.win_rate===null?'—':`${Number(record.win_rate).toFixed(1)}%`,'Win rate']]);
    $('add-team').textContent=p.club?'Change team':'Add team';$('profile-team-select').dataset.selected=p.club?.team_id||'';
    metrics('profile-metrics',[[record.played,'Shootouts'],[p.streak.current,'Daily streak'],[p.streak.longest,'Best streak'],[p.completed_quizzes||0,'Completed quizzes']]);
    $('profile-level').textContent=`Level ${p.level}`;
    $('profile-xp-total').textContent=Number(p.total_xp).toLocaleString('en-GB')+' total XP';
    $('profile-xp-range').textContent=p.next_level_xp===null?'':`${p.total_xp-p.level_xp} / ${p.next_level_xp-p.level_xp} XP`;
    $('level-label').textContent=p.next_level_xp===null?'Maximum level':`${p.next_level_xp-p.total_xp} XP to level ${p.level+1}`;
    $('level-progress').max=p.next_level_xp===null?1:p.next_level_xp-p.level_xp;
    $('level-progress').value=p.next_level_xp===null?1:p.total_xp-p.level_xp;
    $('daily-status').textContent='';$('daily-status').hidden=true;
    if(own){teamChangeAt=p.team_change?.next_change_at||null;teamChangeStatus();$('bio').value=p.bio;$('profile-username').value=p.username;$('account-email').value=p.email||'';$('public-profile').href='/u/'+encodeURIComponent(p.username);globalThis.PointsAccountSettings?.setProfile(p);}
    globalThis.PointsFriends?.profile(p,own);
    globalThis.PointsProfile={profile:p,own};
    window.dispatchEvent(new CustomEvent('points-profile',{detail:globalThis.PointsProfile}));
  }
  async function accountPage(){
    const params=new URLSearchParams(location.search||''),next=params.get('next');
    const returnTo=next&&/^\/(daily|penalties|friends(?:\/[A-Za-z0-9_-]{32,64})?)$/.test(next)?next:null;
    const publicName=page.dataset.username;
    if(publicName){showProfile(await api('/api/players/profiles/'+encodeURIComponent(publicName)),false);return;}
    let user=null,blockedMessage='';
    try{user=await currentUser();}catch(e){if(e.status!==403)throw e;blockedMessage=e.message;}
    if(user&&returnTo){location.href=returnTo;return;}if(user)showProfile(user,true);else{$('notice').textContent='';$('authentication').hidden=false;}
    setInterval(()=>{if(!$('own-profile').hidden)teamChangeStatus();},60000);
    function authMode(){
      const register=document.querySelector('input[name="auth-mode"]:checked').value==='register';
      $('login-field').hidden=register;$('identifier').disabled=register;
      $('registration-fields').hidden=!register;$('email').disabled=!register;$('username').disabled=!register;
      $('authenticate').textContent=register?'Create account':'Sign in';$('password').autocomplete=register?'new-password':'current-password';error('');
    }
    document.querySelectorAll('input[name="auth-mode"]').forEach(input=>input.addEventListener('change',authMode));
    if(params.get('mode')==='register')document.querySelector('input[name="auth-mode"][value="register"]').checked=true;
    authMode();globalThis.PointsAccountSettings?.resetView();if(blockedMessage)error(blockedMessage);
    $('auth-form').addEventListener('submit',async e=>{
      e.preventDefault();error('');$('authenticate').disabled=true;
      try{const mode=document.querySelector('input[name="auth-mode"]:checked').value;
        const credentials=mode==='register'?{username:$('username').value,email:$('email').value,password:$('password').value}:{identifier:$('identifier').value,password:$('password').value};
        const p=await api('/api/players/'+mode,credentials);$('password').value='';if(returnTo){location.href=returnTo;return;}showProfile(p,true);
      }catch(e){error(e.message);}finally{$('authenticate').disabled=false;}
    });
    $('profile-edit').addEventListener('submit',async e=>{
      e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;$('profile-edit-status').textContent='';
      try{showProfile(await api('/api/players/me',{bio:$('bio').value},'PATCH'),true);$('profile-edit-status').textContent='Profile saved.';}
      catch(e){$('profile-edit-status').textContent=e.message;}finally{button.disabled=false;}
    });
    $('signout').addEventListener('click',async()=>{
      const button=$('signout');if(button.disabled)return;
      button.disabled=true;error('');
      try{await api('/api/players/logout',{});globalThis.PointsPreferences?.clear();location.href='/account';}
      catch(e){error(e.message);button.disabled=false;}
    });
    const closeTeam=()=>$('team-dialog').close();
    let teamRequest=0;
    $('team-dialog').addEventListener('close',()=>{teamRequest++;teamChangeStatus();});
    $('cancel-team').addEventListener('click',closeTeam);
    $('add-team').addEventListener('click',async()=>{
      const request=++teamRequest;
      globalThis.PointsAccountSettings.openDialog('team-dialog',$('add-team'));
      $('team-edit').hidden=true;$('team-edit-status').textContent='Loading teams...';
      try{
        const data=await api('/api/players/teams');
        if(request!==teamRequest||!$('team-dialog').open)return;
        $('profile-team-select').replaceChildren(...[{team_id:'',name:'No team'},...data.teams].map(t=>{const o=node('option',t.name);o.value=String(t.team_id);return o;}));
        $('profile-team-select').value=$('profile-team-select').dataset.selected;
        globalThis.PointsUI?.teamPicker(data.teams,$('profile-team-select'),$('team-options'));
        $('team-edit').hidden=false;$('team-edit-status').textContent='';
      }catch(e){if(request===teamRequest)$('team-edit-status').textContent=e.message;}finally{teamChangeStatus();}
    });
    $('team-edit').addEventListener('submit',async e=>{
      e.preventDefault();$('save-team').disabled=true;$('team-edit-status').textContent='';
      try{showProfile(await api('/api/players/me/team',{team_id:$('profile-team-select').value?Number($('profile-team-select').value):null},'PUT'),true);closeTeam();}
      catch(e){$('team-edit-status').textContent=e.message;if(e.status===409){try{const latest=await currentUser();if(latest)showProfile(latest,true);}catch{}}}finally{$('save-team').disabled=false;}
    });
    $('email-edit').addEventListener('submit',async e=>{
      e.preventDefault();const button=e.target.querySelector('button:not(.password-toggle)');button.disabled=true;$('email-edit-status').textContent='';
      try{const p=await api('/api/players/email',{email:$('account-email').value,password:$('email-password').value},'PUT');$('email-password').value='';showProfile(p,true);$('email-edit-status').textContent='Sign-in email saved.';}
      catch(e){$('email-edit-status').textContent=e.message;}finally{button.disabled=false;}
    });
  }

  async function soloPage(){
    const daily=page.dataset.mode==='daily',base=daily?'/api/daily':'/api/solo',minimum=daily?1:10;
    let rankedAvailable=true;
    let user=null,counts={},rules=null,trialAvailable=true,run=null,offset=0,polling=false,busy=false,rendered='',pending=null,startRequest=null;
    let catalogReady=false,catalogLoading=false,catalogReset=Infinity;
    const animatedShots=new Set(),scene=globalThis.PenaltyScene;
    const stadium=globalThis.PointsStadium;
    let stadiumRun=null,stadiumWaiting=false,presentation=0,presented='';
    let nextRevealTimer=null,feedbackKey='',feedbackUntil=0;
    function syncNextPenalty(){
      clearTimeout(nextRevealTimer);
      const ready=run?.phase==='READY',review=run?.phase==='REVIEW';
      const remaining=feedbackUntil-Date.now();
      const show=ready||(review&&!stadiumWaiting&&remaining<=0);
      const button=$('next'),wasHidden=button.hidden;
      button.hidden=!show;button.disabled=busy||stadiumWaiting;
      $('answer-slot').classList.toggle('is-continuing',show);
      $('choices').inert=show;
      if(review&&!stadiumWaiting&&remaining>0)nextRevealTimer=setTimeout(syncNextPenalty,remaining);
      // Keyboard users advance from the same place without stealing focus
      // from navigation. A held key must not skip the newly revealed question.
      if(show&&review&&wasHidden&&[document.body,$('question-title')].includes(document.activeElement))button.focus({preventScroll:true});
    }
    const resultShare=globalThis.PointsResultShare;
    let reviewPosition=0;
    const sharing=resultShare?.bind?.(()=>run?{run_id:run.run_id,mode:daily?'daily':'solo'}:null);
    const xpResult=globalThis.PointsProgress?.bindResult();
    // Detail views are separate dialogs, so long shootouts never grow the
    // result card. Pagination is presentation-only and uses server review data.
    const correctAnswer=answer=>(answer?.options||[]).find(option=>option.id===answer?.correct)?.text||'';
    function reviewAnswer(position){
      const answers=run?.review||[];
      reviewPosition=Math.max(0,Math.min(position,answers.length-1));
      const answer=answers[reviewPosition];
      $('review').replaceChildren();
      if(answer){
        const block=node('article',undefined,'review-item');
        block.append(node('h3',PointsQuestion.text(answer)),node('p',correctAnswer(answer)));
        $('review').append(block);
      }
      $('review-position').textContent=answers.length?`${reviewPosition+1} / ${answers.length}`:'No answers';
      $('review-previous').disabled=reviewPosition===0;
      $('review-next').disabled=reviewPosition>=answers.length-1;
    }
    function clearShare(){
      sharing?.reset();
      if($('review-dialog').open)$('review-dialog').close();
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
            const winner=run.shootout?.winner;
            if(winner)globalThis.PointsAudio?.play(winner==='player'?'win':'loss');
            xpResult?.reveal();
          }
        }else if(run.phase==='REVIEW'){
          // Camera travel happens before Next sends the request that opens the clock.
          stadium.reset();await stadium.enter(run.survival?'shooter':run.shootout.next_role,{intro:false});
        }else if(run.phase==='ANSWERING')stadium.skip();
      }finally{
        if(current()){stadiumWaiting=false;syncNextPenalty();}
      }
    }
    function stadiumView(){
      if(!stadium)return;
      if(run.shootout||run.survival){const task=shootoutView(),token=presentation;task.catch(()=>{if(token!==presentation)return;stadiumWaiting=false;stadium.leave();$('summary').hidden=!['FINISHED','ABANDONED'].includes(run.phase);syncNextPenalty();xpResult?.reveal();});return;}
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
        if(run?.run_id!==id)return;stadiumWaiting=false;syncNextPenalty();
      });
    }
    function pitch(){
      const score=run?.shootout,survival=run?.survival;
      const finished=run&&['FINISHED','ABANDONED'].includes(run.phase);
      $('shootout-board').hidden=(!score&&!survival)||(finished&&stadiumRun!==run.run_id);
      $('shootout-board').classList.toggle('daily-survival-board',Boolean(survival));
      if($('name-opponent').parentElement)$('name-opponent').parentElement.hidden=Boolean(survival);
      if(survival){
        $('name-player').textContent='Goals';$('score-player').textContent=String(survival.goals);
        $('kicks-player').replaceChildren(...Array.from({length:survival.max_lives},(_,i)=>{
          const life=node('span',undefined,'daily-life '+(i<survival.lives?'remaining':'lost'));
          life.setAttribute('role','img');life.setAttribute('aria-label',i<survival.lives?'Life remaining':'Life lost');return life;
        }));
        $('shootout-round').textContent=`${survival.ranked?'Daily score':'Practice'} · ${survival.lives} / ${survival.max_lives} lives`;
        return;
      }
      $('name-player').textContent='You';
      if(!scene)return;
      if(score){
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
        $('availability').textContent=catalogLoading?'Loading...':catalogReady&&count<1?'No unused questions. Try again after the weekly reset.':!catalogReady?'Daily Challenge is unavailable.':rankedAvailable?'This attempt counts towards your best score.':'Practice only. Today\'s scored attempt is complete.';
        $('weekly-reset').hidden=!catalogReady;
        $('start').disabled=!catalogReady||count<1||busy;$('start').textContent=rankedAvailable?'Play Daily Challenge':'Play practice';
        $('trial-note').hidden=true;$('quiz-rules').textContent='Three lives. You only shoot. 15 seconds per answer.';return;
      }
      $('availability').textContent=catalogLoading?'Loading...':!catalogReady?'Could not load shootouts. Please refresh.':count>=10?'':'No new shootout at this difficulty. Try another.';
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
        if(daily){counts={mixed:catalog.remaining};rules=catalog.rules;rankedAvailable=catalog.ranked_available;catalogReset=Date.parse(catalog.resets_at);$('weekly-reset').textContent='One scored attempt each day.';catalogReady=true;return;}
        // Keep eligibility checks internal; every new game uses all clubs and topics.
        counts=catalog.topics.find(t=>t.code==='ALL')?.counts_by_team.ALL||{};rules=catalog.rules;
        catalogReset=catalog.resets_at?Date.parse(catalog.resets_at):Infinity;
        $('weekly-reset').textContent=catalog.resets_at?'Questions reset weekly.':'';
        for(const level of ['easy','medium','hard']){
          $(level+'-rate').textContent=`${rules.xp_by_difficulty[level]} XP / answer`;
          $(level+'-perfect').textContent=rules.bonus_mode==='win'?`Win: ${rules.win_multipliers[level]}x XP`:rules.format==='shootout'?`Perfect game: ${rules.perfect_multipliers[level]}x XP`:`10/10: ${10*rules.xp_by_difficulty[level]*rules.perfect_multipliers[level]} XP`;
        }
        catalogReady=true;
      }finally{catalogLoading=false;selection();}
    }
    function render(next){
      if(run&&run.run_id===next.run_id&&next.server_now<run.server_now)return;
      const justFinished=run?.run_id===next.run_id&&!['FINISHED','ABANDONED'].includes(run.phase)&&['FINISHED','ABANDONED'].includes(next.phase);
      run=next;offset=next.server_now-Date.now();storage(['FINISHED','ABANDONED'].includes(run.phase)?null:run.run_id);
      updateClock();
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
      $('run-position').textContent=run.survival?`Shot ${Math.max(1,run.position)}`:run.shootout?`${run.role==='keeper'?'Defending':'Shooting'} · Penalty ${Math.max(1,Math.ceil(run.position/2))}`:`Shot ${Math.max(1,run.position)} / 10`;
      $('question-title').textContent=PointsQuestion.text(run.question)||'Ready for your first question?';
      $('choices').replaceChildren();
      const answer=run.review.find(a=>a.position===run.position);
      (run.question?.options||[]).forEach(option=>{
        const button=node('button',option.text);button.disabled=!active||busy;
        if(answer){
          button.classList.toggle('correct',option.id===answer.correct);button.classList.toggle('incorrect',option.id===answer.option_id&&!answer.is_correct);button.classList.toggle('chosen',option.id===answer.option_id);
          if(option.id===answer.correct)button.setAttribute('aria-label',option.text+', correct answer');
          else if(option.id===answer.option_id)button.setAttribute('aria-label',option.text+', incorrect answer');
        }
        button.addEventListener('click',()=>submit(option.id));$('choices').append(button);
      });
      // Outcome colors and accessible option labels carry feedback in-game.
      // The full answer list remains available in the post-game review.
      $('feedback').textContent='';
      $('next').textContent=run.phase==='READY'?'Take first shot':'Next penalty';
      const answerKey=`${run.run_id}:${run.position}`;
      if(run.phase==='REVIEW'&&feedbackKey!==answerKey){
        feedbackKey=answerKey;
        // Keep green/red feedback readable even with animations switched off.
        feedbackUntil=Date.now()+600;
      }
      $('leave').hidden=done;$('another').hidden=!done;$('summary').hidden=!done;
      $('another').textContent='New shootout';$('guest-benefits').hidden=!done||!run.is_trial;
      if(done){
        clearShare();
        $('share-status').textContent='';
        const total=run.shootout||run.survival?run.review.length:run.rules.questions;
        $('result-heading').textContent=run.shootout?.winner?(run.shootout.winner==='player'?'You won the shootout!':'Opponent wins'):run.perfect?'Perfect shootout!':run.phase==='ABANDONED'?'Shootout ended':'Shootout complete';
        $('result-completion').textContent=run.shootout?`${run.shootout.player} : ${run.shootout.opponent} · ${run.review.length} ${run.review.length===1?'penalty':'penalties'}${run.end_reason==='question_pool_exhausted'?' · No unused questions remain; no winner declared.':''}`:`${run.review.filter(a=>a.option_id!==null).length} answered · ${run.review.filter(a=>a.option_id===null).length} timed out · ${total-run.review.length} unplayed`;
        metrics('result-metrics',[[`${run.correct} / ${total}`,'Correct answers'],[run.total_xp,run.is_trial?'Trial XP (not saved)':'XP earned'],[run.bonus_xp,run.rules.bonus_mode==='win'?'Win bonus':'Perfect bonus'],[run.multiplier+'x','Multiplier']]);
        if(run.survival){
          const s=run.survival;
          $('result-heading').textContent=s.ranked?'Daily Challenge complete':'Practice complete';
          if(run.phase==='ABANDONED')$('result-heading').textContent=s.ranked?'Daily Challenge ended':'Practice ended';
          $('result-completion').textContent=`${total} penalties · ${s.ranked?'Daily score saved':'Practice · Not ranked'}${run.end_reason==='daily_pool_exhausted'?' · Pool completed':run.end_reason==='daily_reset'?' · Daily reset':''}`;
          metrics('result-metrics',[[s.goals,'Goals'],[s.mistakes,'Lives lost'],[run.total_xp,'XP earned'],[run.highscore??0,'All-time high score']]);
          $('another').textContent='Play practice';
        }else if(daily){
          $('result-heading').textContent=run.won?'Daily Challenge won!':run.phase==='ABANDONED'?'Challenge ended':'Try again tomorrow';
          if(!run.won&&run.phase==='FINISHED')$('result-heading').textContent='Opponent wins';
          if(run.end_reason==='daily_pool_exhausted')$('result-completion').textContent+=' · Daily pool completed';
          if(run.end_reason==='daily_reset')$('result-completion').textContent+=' · Daily reset';
          metrics('result-metrics',[[`${run.correct} / ${total}`,'Correct answers'],[run.total_xp,'XP earned']]);
          $('another').textContent='Back to Daily Challenge';
        }
        const p=run.player_progress;
        $('result-level').hidden=!p||run.is_trial;
        if(p&&!run.is_trial&&!xpResult){
          const max=p.next_level_xp===null;
          $('result-level-label').textContent=`Level ${p.level} · ${p.total_xp} total XP`;
          $('result-level-progress').max=max?1:p.next_level_xp-p.level_xp;
          $('result-level-progress').value=max?1:p.total_xp-p.level_xp;
          $('result-level-remaining').textContent=max?'Maximum level':`${Math.max(0,p.next_level_xp-p.total_xp)} XP to level ${p.level+1}`;
        }
        xpResult?.prepare(run,{animate:justFinished});
        $('summary-account').textContent=run.is_trial?'Sign in':'View profile';$('summary-account').href='/account';
        $('result-review').disabled=run.review.length===0;
        reviewAnswer(0);
        currentUser().then(p=>{if(p)user=p;}).catch(()=>{});
      }
      if(active)$('question-title').focus({preventScroll:true});
      stadiumView();
      syncNextPenalty();
      if(done&&!stadiumWaiting){$('result-heading').focus({preventScroll:true});xpResult?.reveal();}
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
      finally{busy=false;syncNextPenalty();}
    }
    function submit(option){
      if(busy||run?.phase!=='ANSWERING')return;
      if(!pending||pending.position!==run.position)pending={position:run.position,option_id:option,request_id:crypto.randomUUID()};
      return command('answers',pending);
    }
    $('next').addEventListener('click',()=>command('next',{previous:run.position}));
    $('next').addEventListener('keydown',event=>{if(event.repeat&&['Enter',' '].includes(event.key))event.preventDefault();});
    $('leave').addEventListener('click',()=>command('leave',{}));
    $('retry').addEventListener('click',()=>{rendered='';refresh();});
    $('result-review').addEventListener('click',()=>{reviewAnswer(0);$('review-dialog').showModal();});
    $('review-previous').addEventListener('click',()=>reviewAnswer(reviewPosition-1));
    $('review-next').addEventListener('click',()=>reviewAnswer(reviewPosition+1));
    $('review-close').addEventListener('click',()=>$('review-dialog').close());
    $('another').addEventListener('click',async()=>{presentation++;presented='';stadium?.leave();xpResult?.clear();stadiumRun=null;stadiumWaiting=false;storage(null);clearShare();run=null;pending=null;startRequest=null;rendered='';feedbackKey='';feedbackUntil=0;syncNextPenalty();if(location.search)history.replaceState(null,'',location.pathname);page.classList.toggle('shootout-active',false);page.classList.toggle('shootout-finished',false);pitch();$('quiz-run').hidden=true;$('selection').hidden=false;error('');try{await loadCatalog();}catch(e){error(e.message);}});
    document.querySelectorAll('input[name="difficulty"]').forEach(r=>r.addEventListener('change',selection));
    $('quiz-start').addEventListener('submit',async e=>{
      e.preventDefault();if(busy||!catalogReady||(counts[difficulty()]||0)<minimum)return;busy=true;selection();error('');
      const category='ALL',topic='ALL',level=difficulty();
      if(!startRequest||startRequest.category!==category||startRequest.topic!==topic||startRequest.difficulty!==level)startRequest={category,topic,difficulty:level,request_id:crypto.randomUUID()};
      try{if(globalThis.PointsModeIntro&&!await globalThis.PointsModeIntro.show(daily?'daily':'solo'))return;const next=await api(base+'/runs',daily?{request_id:startRequest.request_id}:startRequest);busy=false;render(next);startRequest=null;}catch(e){error(e.message);if(e.status===409){try{await loadCatalog();}catch(refreshError){error(refreshError.message);}}}finally{busy=false;selection();}
    });
    function updateClock(){
      if(!run)return;
      const remaining=run.phase==='ANSWERING'?Math.max(0,run.deadline-Date.now()-offset)/1000:0;
      // Round only the label. The progress bar keeps the precise server deadline.
      $('seconds').textContent=Math.ceil(remaining)+' s';$('timer').max=(run.rules.answer_ms||15000)/1000;$('timer').value=remaining;
      if(run.phase==='ANSWERING'&&remaining===0){for(const b of $('choices').children)b.disabled=true;}
    }
    setInterval(updateClock,100);
    setInterval(()=>{if(run&&run.phase==='ANSWERING'&&!busy)refresh();},1000);
    setInterval(()=>{if(!run&&!busy&&!catalogLoading&&Date.now()+offset>=catalogReset)loadCatalog().catch(e=>error(e.message));},30000);
    pitch();user=await currentUser();stadium?.setOutfits?.(user?.outfit,null);if(user?.preferences)globalThis.PointsPreferences?.set(user.preferences);
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
