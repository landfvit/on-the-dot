/* Account-only commands. Passwords and reset tokens never enter localStorage. */
(() => {
    'use strict';
    const $=id=>document.getElementById(id);
    const dialogTriggers=new WeakMap();
    function openDialog(id,trigger=document.activeElement){
        const dialog=$(id);
        if(!dialog||dialog.open)return;
        // Safari does not focus buttons on a pointer click, so remember the
        // actual opener instead of relying on document.activeElement there.
        dialogTriggers.set(dialog,trigger);
        for(const status of dialog.querySelectorAll('[role=status],[role=alert]'))status.textContent='';
        if(id==='delete-dialog')$('delete-account').reset();
        dialog.showModal();
    }
    for(const trigger of document.querySelectorAll('[data-profile-dialog]')){
        trigger.addEventListener('click',()=>openDialog(trigger.dataset.profileDialog,trigger));
    }
    for(const dialog of document.querySelectorAll('.profile-dialog')){
        dialog.addEventListener('close',()=>{
            const trigger=dialogTriggers.get(dialog);
            if(trigger?.isConnected&&!trigger.disabled)trigger.focus({preventScroll:true});
        });
    }
    let resetToken=new URLSearchParams(location.hash.slice(1)).get('reset');
    if(resetToken)history.replaceState(null,'',location.pathname+location.search);
    async function api(path,data,method='POST'){
        const response=await fetch('/api/players/'+path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
        const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'Check the entered details.');return value;
    }
    // Each input has its own reveal toggle. Labels and aria-pressed expose the
    // state without ever changing the input's autocomplete purpose.
    for(const input of document.querySelectorAll('input[type="password"]')){
        const wrap=document.createElement('span');wrap.className='password-field';input.replaceWith(wrap);wrap.append(input);
        const button=document.createElement('button'),icon=document.createElement('img');button.type='button';button.className='password-toggle';icon.alt='';button.append(icon);wrap.append(button);
        const update=()=>{const shown=input.type==='text';button.setAttribute('aria-label',shown?'Hide password':'Show password');button.title=shown?'Hide password':'Show password';button.setAttribute('aria-pressed',String(shown));icon.src='/trivia-assets/icons/'+(shown?'eye-off':'eye')+'.svg';};
        button.addEventListener('click',()=>{input.type=input.type==='password'?'text':'password';update();});
        // Keep ordinary drafts, but clear and conceal credentials on close.
        input.closest('.profile-dialog')?.addEventListener('close',()=>{input.value='';input.type='password';update();});
        input.form?.addEventListener('submit',()=>{input.type='password';update();});update();
    }
    async function submit(event,status,action){
        event.preventDefault();const button=event.target.querySelector('button:not(.password-toggle)');button.disabled=true;$(status).textContent='';
        try{await action();}catch(error){$(status).textContent=error.message;}finally{button.disabled=false;}
    }
    $('password-edit').addEventListener('submit',event=>submit(event,'password-status',async()=>{
        if($('new-password').value!==$('confirm-password').value)throw new Error('New passwords do not match.');
        await api('password',{current_password:$('current-password').value,new_password:$('new-password').value},'PUT');
        event.target.reset();$('password-status').textContent='Password changed. Other devices have been signed out.';
    }));
    $('preferences-edit').addEventListener('submit',event=>submit(event,'preferences-status',async()=>{
        const value=await api('preferences',{animations:$('setting-animations').checked,reduced_motion:$('setting-reduced-motion').checked},'PUT');
        globalThis.PointsPreferences?.set(value);$('preferences-status').textContent='Preferences saved.';
    }));
    $('delete-cancel').addEventListener('click',()=>$('delete-dialog').close());
    $('delete-account').addEventListener('submit',event=>submit(event,'delete-status',async()=>{
        await api('me',{password:$('delete-password').value,confirmation:$('delete-confirmation').value},'DELETE');
        globalThis.PointsPreferences?.clear();location.href='/penalties';
    }));
    $('forgot-password').addEventListener('click',()=>{$('auth-form').hidden=true;$('reset-request').hidden=false;$('reset-status').textContent='';});
    $('reset-back').addEventListener('click',()=>{$('auth-form').hidden=false;$('reset-request').hidden=true;$('reset-status').textContent='';});
    $('reset-request').addEventListener('submit',event=>submit(event,'reset-status',async()=>{
        const data=await api('password-reset/request',{email:$('reset-email').value});$('reset-status').textContent=data.message;
    }));
    $('reset-confirm').addEventListener('submit',event=>submit(event,'reset-status',async()=>{
        await api('password-reset/confirm',{token:resetToken,new_password:$('reset-new-password').value});resetToken=null;event.target.reset();
        $('reset-confirm').hidden=true;$('auth-form').hidden=false;$('reset-status').textContent='Password reset. Sign in with your new password.';
    }));
    function resetView(){
        if(!resetToken)return;
        $('profile').hidden=true;$('authentication').hidden=false;$('auth-form').hidden=true;$('reset-request').hidden=true;$('reset-confirm').hidden=false;$('notice').textContent='';
    }
    globalThis.PointsAccountSettings={openDialog,setProfile(p){
        $('profile-username').value=p.username;
        $('setting-animations').checked=p.preferences?.animations!==false;$('setting-reduced-motion').checked=p.preferences?.reduced_motion===true;
        globalThis.PointsPreferences?.set(p.preferences||{});resetView();
    },resetView};
    window.addEventListener('hashchange',()=>{
        const incoming=new URLSearchParams(location.hash.slice(1)).get('reset');if(!incoming)return;
        resetToken=incoming;history.replaceState(null,'',location.pathname+location.search);$('reset-status').textContent='';resetView();
    });
    fetch('/api/players/settings').then(r=>r.ok?r.json():{}).then(data=>{$('forgot-password').hidden=!data.password_reset_available;}).catch(()=>{});
    resetView();
})();
