/* Friends are private account data. DOM textContent avoids treating usernames
 * or API error messages as HTML. Only accepted requests can receive invites. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  let own=false,publicName='',busy=false,lastList='';
  async function api(path='',body,method){
    const r=await fetch('/api/players/friends'+path,{method:method||(body===undefined?'GET':'POST'),headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please sign in to add friends.');return data;
  }
  async function load(){
    const data=await api();$('friend-count').textContent=String(data.friends.filter(f=>f.status==='pending'&&f.incoming).length||'');
    const signature=JSON.stringify(data);if(signature===lastList)return;lastList=signature;
    $('friend-list').replaceChildren();
    for(const [title,rows] of [['Requests',data.friends.filter(f=>f.status==='pending'&&f.incoming)],['Friends',data.friends.filter(f=>f.status==='accepted')],['Sent requests',data.friends.filter(f=>f.status==='pending'&&!f.incoming)]]){
      if(!rows.length)continue;$('friend-list').append(node('h3',title));
      for(const friend of rows){
        const row=node('div','');row.className='friend-row';const link=node('a',friend.username);link.href='/u/'+encodeURIComponent(friend.username);row.append(link);
        const actions=node('div','');actions.className='actions';
        function button(label,path,body,method){const b=node('button',label);b.type='button';b.addEventListener('click',()=>act(()=>api('/'+encodeURIComponent(friend.username)+path,body,method)));actions.append(b);}
        if(friend.status==='accepted'){
          const invite=node('a','Invite to duel');invite.href='/friends?invite='+encodeURIComponent(friend.username);invite.className='primary-link';actions.append(invite);
          if(friend.invite){const join=node('a','Join invitation');join.href=friend.invite;join.className='primary-link';actions.append(join);}
          button('Remove','',undefined,'DELETE');
        }else{
          if(friend.incoming)button('Accept','/accept',{});
          button(friend.incoming?'Decline':'Cancel','',undefined,'DELETE');
        }
        row.append(actions);$('friend-list').append(row);
      }
    }
    if(!data.friends.length)$('friend-list').append(node('p','No friends yet.'));
  }
  async function act(work){
    if(busy)return;busy=true;$('friend-status').textContent='';
    try{await work();await load();}catch(e){$('friend-status').textContent=e.message;}finally{busy=false;}
  }
  $('friend-add').addEventListener('submit',e=>{e.preventDefault();act(async()=>{await api('',{username:$('friend-username').value.trim()});$('friend-username').value='';$('friend-status').textContent='Request sent. Your friend needs to accept it.';});});
  const tabs=[...document.querySelectorAll('[data-profile-tab]')];
  for(const tab of tabs)tab.addEventListener('click',()=>{
    $('profile-stats').hidden=tab.dataset.profileTab!=='overview';
    for(const b of tabs)b.setAttribute('aria-pressed',String(b===tab));
    for(const panel of document.querySelectorAll('[data-profile-panel]'))panel.hidden=panel.dataset.profilePanel!==tab.dataset.profileTab;
    if(tab.dataset.profileTab==='friends')load().catch(e=>{$('friend-status').textContent=e.message;});
  });
  $('public-add-friend').addEventListener('click',async()=>{
    const button=$('public-add-friend');button.disabled=true;
    try{const r=await api('',{username:publicName});$('public-friend-status').textContent=r.status==='accepted'?'Already friends.':'Friend request pending.';}
    catch(e){$('public-friend-status').textContent=e.message;button.disabled=false;}
  });
  globalThis.PointsFriends={profile(p,isOwn){
    own=isOwn;publicName=p.username;$('public-add-friend').hidden=own;$('profile-tabs').hidden=!own;
    if(own)load().catch(e=>{$('friend-status').textContent=e.message;});
  }};
  // Invitations arriving while the profile is open become visible quietly.
  setInterval(()=>{if(own&&!document.hidden)load().catch(()=>{});},15000);
})();
