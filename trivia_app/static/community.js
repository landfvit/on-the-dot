(function(){
  'use strict';
  const $=id=>document.getElementById(id),page=document.querySelector('.community-page'),ranking=page.dataset.view==='leaderboard';
  let offset=0,request=0,controller;
  const size=ranking?25:20,number=n=>Number(n).toLocaleString('en-US');
  const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
  const period=()=>document.querySelector('input[name="period"]:checked')?.value||'today';
  const metric=()=>document.querySelector('input[name="metric"]:checked')?.value||'xp';
  const board=()=>document.querySelector('input[name="board"]:checked')?.value||'players';
  const labels={xp:'XP',streak:'Streak',wins:'Wins',win_rate:'Win rate',level:'Levels',daily_wins:'Daily wins'};
  const requestedMetric=new URLSearchParams(location.search||'').get('metric');
  if(ranking&&Object.hasOwn(labels,requestedMetric)){const input=document.querySelector(`input[name="metric"][value="${requestedMetric}"]`);if(input)input.checked=true;}
  const rate=n=>n===null||n===undefined?'–':`${Number(n).toFixed(1)}%`;
  function playerLink(p){const a=node('a',p.username);a.href='/u/'+encodeURIComponent(p.username);return a;}
  function renderRanking(data){
    const teams=(data.board||board())==='teams',selected=data.metric||metric();
    const value=p=>selected==='win_rate'?rate(p.win_rate):number(p[selected]||0);
    const identity=p=>teams?node('span',p.name):playerLink(p);
    const own=p=>data.me&&(teams?data.me.team_id===p.team_id:data.me.username===p.username);
    $('rank-name').textContent=teams?'Team':'Player';$('rank-value').textContent=labels[selected];
    $('team-ranking-note').hidden=!teams;
    $('ranking-table').hidden=!data.entries.length;
    $('ranking-rows').replaceChildren(...data.entries.map(p=>{
      const row=node('tr');if(own(p))row.className='own-rank';
      const name=node('td');name.append(identity(p));
      const badge=globalThis.PointsUI?.badge(teams?p:p.club);if(badge)name.append(badge);
      row.append(node('td',number(p.rank)),name,node('td',value(p)));return row;
    }));
    $('ranking-self').hidden=false;$('ranking-self').replaceChildren();
    $('ranking-table').setAttribute('data-metric',selected);
    if(data.me)$('ranking-self').append(node('strong',`${teams?'Your team':'Your rank'} #${number(data.me.rank)}`),node('span',`${value(data.me)} ${selected==='win_rate'?'':labels[selected]}`.trim()),identity(data.me));
    else {
      $('ranking-self').append(node('strong',data.signed_in?(teams?'Add a team to join this leaderboard.':'Complete a shootout to enter this leaderboard.'):'Sign in to join the leaderboard.'));
      const a=node('a',data.signed_in?(teams?'Your profile':'Play penalties'):'Sign in');a.href=data.signed_in&&!teams?'/penalties':'/account';$('ranking-self').append(a);
    }
    const noun=teams?'team':'player';
    $('distribution').hidden=!data.participants||selected==='daily_wins';$('participant-count').textContent=`${number(data.participants)} ${noun}${data.participants===1?'':'s'}`;
    const maximum=Math.max(1,...data.distribution.map(b=>b.count));
    $('distribution-bars').replaceChildren(...data.distribution.map(b=>{
      const col=node('div',undefined,'distribution-column'),bar=node('div',undefined,'distribution-bar');
      bar.style.height=`${b.count/maximum*100}%`;bar.setAttribute('aria-hidden','true');
      col.append(node('span',number(b.count)),bar,node('small',b.label));
      col.setAttribute('aria-label',`${b.label} XP: ${b.count} ${noun}${b.count===1?'':'s'}`);return col;
    }));
    const day=s=>new Date(s).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
    $('ranking-period').textContent=selected==='streak'?'Current streak · days · UTC':(data.since?`${day(data.since)}${data.period==='week'?' - '+day(data.as_of):''} · UTC`:'All time');
    $('community-status').textContent=data.participants?'':'No scores yet in this period.';
    $('community-play').hidden=Boolean(data.participants);
    return offset+data.entries.length<data.participants;
  }
  function renderHistory(data){
    $('history-list').replaceChildren(...data.items.map(item=>{
      const link=node('a',undefined,'history-row');link.href='/penalties?run='+encodeURIComponent(item.run_id);
      const date=node('time',new Date(item.finished_at).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}));date.dateTime=new Date(item.finished_at).toISOString();
      const name=node('div'),score=node('div',undefined,'history-score');
      const outcome=item.shootout?.winner?(item.shootout.winner==='player'?'Won':'Lost'):item.phase==='FINISHED'?'Completed':'Ended early';
      name.append(node('strong',item.category.topic_label||'Mixed topics'),node('span',`${item.category.label} · ${item.difficulty} · ${outcome}`));
      score.append(node('strong',item.shootout?`${item.shootout.player} : ${item.shootout.opponent}`:`${item.correct} / ${item.questions}`),node('span',`+${number(item.xp)} XP`));link.append(date,name,score);return link;
    }));
    $('community-status').textContent=data.items.length?'':'No completed shootouts yet.';$('community-play').hidden=Boolean(data.items.length);
    return data.has_more;
  }
  async function load(){
    const own=++request;controller?.abort();controller=new AbortController();
    $('community-status').textContent='Loading...';$('community-retry').hidden=true;$('community-signin').hidden=true;$('community-play').hidden=true;
    $('community-pagination').hidden=true;
    if(ranking){$('ranking-table').hidden=true;$('distribution').hidden=true;$('ranking-self').hidden=true;}
    else $('history-list').replaceChildren();
    try {
      const currentOnly=['level','streak'].includes(metric());
      if(ranking){
        document.querySelectorAll('input[name="period"]').forEach(input=>{input.disabled=currentOnly;if(currentOnly)input.checked=input.value==='all';});
      }
      const response=await fetch(`/api/community/${ranking?'leaderboard?period='+(currentOnly?'all':period())+'&metric='+metric()+'&board='+board():'history?'}&offset=${offset}&limit=${size}`,{signal:controller.signal});
      if(own!==request)return;
      if(response.status===401){$('community-status').textContent='Sign in to see your shootout history.';$('community-signin').hidden=false;return;}
      if(!response.ok)throw new Error('Unable to load results. Please try again.');
      const data=await response.json();if(own!==request)return;
      const more=ranking?renderRanking(data):renderHistory(data);
      $('community-pagination').hidden=!offset&&!more;$('previous-page').disabled=!offset;$('next-page').disabled=!more;
      $('page-number').textContent=`Page ${Math.floor(offset/size)+1}`;
    }catch(e){if(own!==request||e.name==='AbortError')return;$('community-status').textContent=e.message;$('community-retry').hidden=false;}
  }
  document.querySelectorAll('input[name="period"]').forEach(input=>input.addEventListener('change',()=>{offset=0;load();}));
  document.querySelectorAll('input[name="metric"]').forEach(input=>input.addEventListener('change',()=>{offset=0;load();}));
  document.querySelectorAll('input[name="board"]').forEach(input=>input.addEventListener('change',()=>{
    offset=0;load();
  }));
  $('previous-page').addEventListener('click',()=>{offset=Math.max(0,offset-size);load();});
  $('next-page').addEventListener('click',()=>{offset+=size;load();});
  $('community-retry').addEventListener('click',load);load();
})();
