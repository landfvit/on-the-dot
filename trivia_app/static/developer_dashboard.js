(() => {
  'use strict';
  const $=id=>document.getElementById(id),number=n=>Number(n||0).toLocaleString('en-GB');
  const date=value=>value?new Date(value).toLocaleString('en-GB',{timeZone:'UTC',dateStyle:'short',timeStyle:'short'})+' UTC':'Never';
  const mode=value=>({solo:'Solo',daily:'Daily Challenge',friend:'Friend Duel'}[value]||value);
  const state={tab:'overview',players:0,games:0,audit:0,serial:0,playerSerial:0,player:null,action:null,pending:null};
  function el(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
  function error(id,message){$(id).textContent=message;$(id).hidden=!message;}
  async function api(path,body){
    const response=await fetch('/api/developer'+path,{credentials:'same-origin',cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
    if(response.status===401){location.assign('/login?next=/internal/dashboard');throw Error('Session expired');}
    const data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Request failed. Please refresh and try again.');
    return data;
  }
  // All account/content strings enter the DOM as text, never HTML.
  function table(id,headers,rows){
    const root=$(id);root.replaceChildren();
    if(!rows.length){root.append(el('p','No records in this view.','empty'));return;}
    const wrap=el('div',undefined,'table-scroll'),t=el('table'),head=el('thead'),tr=el('tr'),body=el('tbody');
    for(const name of headers){const th=el('th',name);th.scope='col';tr.append(th);}head.append(tr);t.append(head,body);
    for(const cells of rows){const row=el('tr');for(const value of cells){const td=el('td');if(value instanceof Node)td.append(value);else td.textContent=value??'—';row.append(td);}body.append(row);}
    wrap.append(t);root.append(wrap);
  }
  function pager(id,data,key){
    const root=$(id);root.replaceChildren();
    const previous=el('button','Previous'),next=el('button','Next');
    previous.disabled=!data.offset;next.disabled=data.offset+data.items.length>=data.total;
    previous.onclick=()=>{state[key]=Math.max(0,data.offset-data.limit);load();};
    next.onclick=()=>{state[key]=data.offset+data.limit;load();};
    root.append(previous,el('span',data.total?`${data.offset+1}–${data.offset+data.items.length} of ${number(data.total)}`:'0 records'),next);
  }
  function playerLink(p){const b=el('button',p.is_guest?'Guest':p.username);b.onclick=()=>openPlayer(p.account_id);return b;}
  function gameRows(items){return items.map(r=>{const people=el('div');r.players?.forEach((p,i)=>{if(i)people.append(el('span',' · '));people.append(playerLink(p));});
    return [mode(r.mode),people,date(r.created_at),r.phase.replaceAll('_',' ').toLowerCase(),r.difficulty||'Mixed',number(r.rounds),number(r.xp)];});}
  function auditRows(items){return items.map(r=>[date(r.created_at),r.username||'',r.action.replaceAll('_',' '),r.reason,r.actor]);}
  function overview(data){
    const t=data.totals,metrics=[['Registered accounts',t.registered,'All time'],['New players',t.new_players,'Selected period'],['Players active',t.players,'Registered · selected period'],['Guest identities',t.guests,'Selected period'],['Games started',t.games,'Selected period'],['Active games',t.active_games,'Activity within 5 minutes'],['Finished',t.completed,'Of games started in period'],['Abandoned / expired',t.abandoned,`${number(t.blocked)} blocked accounts`]];
    $('metrics').replaceChildren(...metrics.map(([label,value,note])=>{const n=el('div',undefined,'metric');n.append(el('span',label),el('strong',number(value)),el('span',note));return n;}));
    const max=Math.max(1,...data.trend.map(d=>d.games));
    $('activity-chart').replaceChildren(...data.trend.map(d=>{const n=el('div',undefined,'chart-bar');n.tabIndex=0;n.setAttribute('aria-label',`${d.day}: ${number(d.games)} games`);n.style.setProperty('--bar-height',`${d.games/max*100}%`);n.append(el('div'));return n;}));
    $('activity-chart').setAttribute('aria-label',`${data.days} days of game starts. ${number(t.games)} games in total.`);
    $('chart-dates').replaceChildren(el('span',data.trend[0]?.day||''),el('span',data.trend.at(-1)?.day||''));
    table('modes',['Mode','Started','Finished','Abandoned'],data.modes.map(m=>[mode(m.mode),number(m.games),number(m.completed),number(m.abandoned)]));
    table('questions',['Difficulty','Approved'],['easy','medium','hard'].map(d=>[d,number(data.questions.find(q=>q.difficulty===d)?.approved)]));
  }
  async function load(){
    const serial=++state.serial,tab=state.tab;$('refresh').disabled=true;error('error','');
    try{
      let path;
      if(tab==='overview')path='/overview?days='+$('period').value;
      if(tab==='players')path='/players?'+new URLSearchParams({search:$('search').value,status:$('player-status').value,offset:state.players});
      if(tab==='games')path='/games?'+new URLSearchParams({mode:$('game-mode').value,status:$('game-status').value,offset:state.games});
      if(tab==='management')path='/audit?offset='+state.audit;
      const data=await api(path);if(serial!==state.serial)return;
      if(tab==='overview')overview(data);
      if(tab==='players'){
        table('player-table',['Player','Email','Team','Level / XP','Games','Last game activity','Status'],data.items.map(p=>[playerLink(p),p.email||'—',p.club||'—',`${p.level} / ${number(p.xp)}`,number(p.games),date(p.last_activity),el('span',p.blocked_at?'Blocked':'Active','status'+(p.blocked_at?' blocked':''))]));
        pager('player-paging',data,'players');
      }
      if(tab==='games'){table('game-table',['Mode','Players','Started','Status','Difficulty','Rounds','XP'],gameRows(data.items));pager('game-paging',data,'games');}
      if(tab==='management'){table('audit-table',['Time','Player','Action','Reason','Admin'],auditRows(data.items));pager('audit-paging',data,'audit');}
      $('updated').textContent='Updated '+date(data.generated_at||Date.now());
    }catch(e){if(serial===state.serial){error('error',e.message);$('updated').textContent='Refresh failed · previous data may be stale';}}
    finally{if(serial===state.serial)$('refresh').disabled=false;}
  }
  function actionControls(player,busy=false){
    for(const button of document.querySelectorAll('[data-action]'))button.disabled=busy;
    document.querySelector('[data-action=password_reset]').disabled=busy||!player?.password_reset_configured||!player.email||!!player.blocked_at||player.is_guest;
  }
  async function openPlayer(id,notice=''){
    const serial=++state.playerSerial;state.player=null;state.action=null;state.pending=null;
    $('player-title').textContent='Loading player…';$('player-detail').replaceChildren();$('player-games').replaceChildren();$('player-audit').replaceChildren();
    $('player-actions').hidden=true;$('action-form').hidden=true;error('player-error','');
    error('player-notice',notice);error('recovery-note','');
    $('confirm-action').disabled=false;$('cancel-action').disabled=false;
    if(!$('player-dialog').open)$('player-dialog').showModal();
    try{
      const p=await api('/players/'+id);const games=await api('/games?'+new URLSearchParams({account_id:id,limit:10}));
      if(serial!==state.playerSerial)return;state.player=p;
      $('player-title').textContent=p.is_guest?'Guest':p.username;const dl=el('dl');
      for(const [label,value] of [['Email',p.email||'—'],['Joined',date(p.created_at)],['Team',p.club||'—'],['Bio',p.bio||'—'],['Status',p.blocked_at?'Blocked since '+date(p.blocked_at):'Active'],['Sessions',number(p.sessions)]])dl.append(el('dt',label),el('dd',value));
      $('player-detail').append(dl);$('player-actions').hidden=p.is_guest;
      document.querySelector('[data-action=block]').hidden=!!p.blocked_at;document.querySelector('[data-action=unblock]').hidden=!p.blocked_at;
      actionControls(p);
      if(!p.is_guest)error('recovery-note',!p.password_reset_configured?'Email recovery is not configured yet.':p.blocked_at?'Unblock this account before sending a reset email.':!p.email?'This account has no email address.':'');
      table('player-games',['Mode','Players','Started','Status','Difficulty','Rounds','XP'],gameRows(games.items));
      table('player-audit',['Time','Player','Action','Reason','Admin'],auditRows(p.audit.map(a=>({...a,username:p.username}))));
    }catch(e){if(serial===state.playerSerial)error('player-error',e.message);}
  }
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{
    state.tab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(t=>{const active=t===b;t.setAttribute('aria-pressed',String(active));$(t.dataset.tab).hidden=!active;});load();
  });
  $('refresh').onclick=load;$('period').onchange=load;
  $('player-search').onsubmit=e=>{e.preventDefault();state.players=0;load();};
  $('player-status').onchange=()=>{state.players=0;load();};
  for(const id of ['game-mode','game-status'])$(id).onchange=()=>{state.games=0;load();};
  $('close-player').onclick=()=>{$('player-dialog').close();state.playerSerial++;};
  $('player-dialog').addEventListener('close',()=>state.playerSerial++);
  document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{
    if(b.disabled||$('confirm-action').disabled||!state.player)return;
    state.action=b.dataset.action;state.pending=null;$('action-form').reset();$('action-form').hidden=false;
    $('action-title').textContent=b.textContent;
    $('action-impact').textContent={
      block:'The player will be signed out, cannot play on this account and will be hidden from all leaderboards. Their email cannot be used for another account, even after deletion.',
      unblock:'The player can sign in again and return to the leaderboards. Previous sessions stay revoked.',
      revoke_sessions:'Every signed-in device will need to sign in again. Existing results and XP stay unchanged.',
      delete:'Permanently remove this account and its sign-in and profile details. Game history and the admin audit remain. A blocked email stays reserved. This cannot be undone.',
      password_reset:`Send a link to ${state.player.email}. It works once and expires in 30 minutes. The password stays unchanged until the player uses it. Existing sessions are then signed out.`
    }[state.action];
    error('player-notice','');error('player-error','');
    $('confirm-action').textContent=state.action==='delete'?'Permanently delete':state.action==='password_reset'?'Send reset email':'Confirm';
    $('confirm-action').classList.toggle('danger',state.action!=='password_reset');
    $('confirmation-label').textContent='Type '+state.player.username+' to confirm';$('action-reason').focus();
  });
  $('cancel-action').onclick=()=>{$('action-form').hidden=true;state.action=null;state.pending=null;};
  $('action-form').onsubmit=async e=>{
    e.preventDefault();if(!state.player||!state.action||$('confirm-action').disabled)return;
    const id=state.player.account_id,payload={action:state.action,reason:$('action-reason').value.trim(),confirmation:$('action-confirmation').value};
    const serial=state.playerSerial,recovery=payload.action==='password_reset';
    // A network retry reuses its id, preventing duplicate moderation entries.
    const signature=JSON.stringify([id,payload]);if(state.pending?.signature!==signature)state.pending={signature,id:crypto.randomUUID()};
    $('confirm-action').disabled=true;$('cancel-action').disabled=true;actionControls(state.player,true);error('player-error','');
    try{
      const result=await api('/players/'+id+(recovery?'/password-reset':'/actions'),
        recovery?{reason:payload.reason,confirmation:payload.confirmation}:{...payload,request_id:state.pending.id});
      if(serial!==state.playerSerial||!$('player-dialog').open)return;
      if(payload.action==='delete'){$('player-dialog').close();state.player=null;state.players=0;}
      else await openPlayer(id,recovery?result.message:'');
      load();
    }
    catch(e){if(serial===state.playerSerial)error('player-error',e.message);}
    finally{if(serial===state.playerSerial){$('confirm-action').disabled=false;$('cancel-action').disabled=false;actionControls(state.player);}}
  };
  // No polling in background tabs or while an admin is inspecting/editing an account.
  setInterval(()=>{if(!document.hidden&&!$('player-dialog').open&&state.tab==='overview'&&!$('refresh').disabled)load();},30000);
  load();
})();
