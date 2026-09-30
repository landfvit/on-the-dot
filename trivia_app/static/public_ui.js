/* Shared public presentation; no advertising provider or tracker is loaded. */
(() => {
    'use strict';
    const key='onthedot.preferences';
    let preferences={animations:true,reduced_motion:false};
    try{Object.assign(preferences,JSON.parse(localStorage.getItem(key)||'{}'));}catch{}
    globalThis.PointsPreferences={get:()=>({...preferences}),set(value){
        preferences={animations:value.animations!==false,reduced_motion:value.reduced_motion===true};
        try{localStorage.setItem(key,JSON.stringify(preferences));}catch{}
        window.dispatchEvent(new Event('points-preferences'));
    },clear(){preferences={animations:true,reduced_motion:false};try{localStorage.removeItem(key);}catch{}}};
    function badge(club){
        if(!club?.team_id||!club.name?.trim()||!Number.isInteger(Number(club.team_id)))return null;
        const image=document.createElement('img');image.className='club-badge';image.width=28;image.height=28;
        image.src=`/trivia-assets/clubs/${Number(club.team_id)}.png`;image.alt=club.name;image.title=club.name;image.decoding='async';
        image.addEventListener('error',()=>{const text=document.createElement('span');text.className='club-fallback';text.textContent=club.name;image.replaceWith(text);},{once:true});
        return image;
    }
    function teamPicker(teams,select,target){
        target.replaceChildren();
        for(const team of [{team_id:'',name:'No team'},...teams]){
            const label=document.createElement('label'),input=document.createElement('input');input.type='radio';input.name='club';input.value=String(team.team_id);
            input.checked=input.value===select.value;input.setAttribute('aria-label',team.name);label.title=team.name;label.append(input);
            const image=badge(team);
            if(image)label.append(image);else{label.className='no-team';const x=document.createElement('img');x.src='/trivia-assets/icons/x.svg';x.alt='No team';label.append(x);}
            input.addEventListener('change',()=>{select.value=input.value;});target.append(label);
        }
    }
    globalThis.PointsUI={badge,teamPicker};
    // One tooltip for the entire public UI. Popover puts it above dialogs;
    // clamping keeps long labels inside the viewport without changing layout.
    const tip=document.createElement('div');tip.id='ui-tooltip';tip.className='ui-tooltip';
    tip.setAttribute('role','tooltip');tip.setAttribute('popover','manual');tip.hidden=true;document.body.append(tip);
    let target=null,pendingTarget=null,focusHint=false,showTimer,hideTimer;
    function hydrate(root){
        for(const e of [root,...(root.querySelectorAll?.('[title]')||[])]){
            if(!(e instanceof Element)||!e.hasAttribute('title'))continue;
            const title=e.getAttribute('title');if(title)e.dataset.uiTooltip=title;e.removeAttribute('title');
        }
    }
    function hideTip(){
        clearTimeout(showTimer);clearTimeout(hideTimer);pendingTarget=null;focusHint=false;
        if(target){const ids=(target.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&id!==tip.id);
            if(ids.length)target.setAttribute('aria-describedby',ids.join(' '));else target.removeAttribute('aria-describedby');}
        if(tip.hidePopover&&tip.matches(':popover-open'))tip.hidePopover();tip.hidden=true;target=null;
    }
    function placeTip(){
        if(!target?.isConnected||!target.getClientRects().length){hideTip();return;}
        const rect=target.getBoundingClientRect(),view=window.visualViewport;
        const left=view?.offsetLeft||0,top=view?.offsetTop||0,right=left+(view?.width||innerWidth),bottom=top+(view?.height||innerHeight);
        tip.style.maxWidth=Math.min(260,right-left-24)+'px';
        const w=tip.offsetWidth,h=tip.offsetHeight,gap=8;
        tip.style.left=Math.max(left+8,Math.min(right-w-8,rect.left+(rect.width-w)/2))+'px';
        const y=rect.top-h-gap>=top+8?rect.top-h-gap:rect.bottom+gap;
        tip.style.top=Math.max(top+8,Math.min(bottom-h-8,y))+'px';
    }
    function showTip(next,keyboard=false){
        hideTip();if(!next?.isConnected||!next.dataset.uiTooltip)return;
        target=next;focusHint=keyboard;tip.textContent=next.dataset.uiTooltip;tip.hidden=false;
        // Keep the hint inside a modal's non-inert subtree. The popover top
        // layer still lets it extend beyond the dialog without being clipped.
        (next.closest('dialog[open]')||document.body).append(tip);
        if(tip.showPopover)tip.showPopover();
        const ids=(next.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean);
        next.setAttribute('aria-describedby',[...ids,tip.id].join(' '));placeTip();
    }
    const tooltipTarget=e=>e instanceof Element?e.closest('[data-ui-tooltip]'):null;
    hydrate(document.body);
    new MutationObserver(changes=>{
        for(const change of changes)if(change.type==='attributes')hydrate(change.target);
        else for(const node of change.addedNodes)if(node instanceof Element)hydrate(node);
        if(target&&!target.isConnected)hideTip();
        else if(target&&tip.textContent!==target.dataset.uiTooltip){tip.textContent=target.dataset.uiTooltip;placeTip();}
    }).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['title']});
    document.addEventListener('pointerover',e=>{
        if(e.pointerType==='touch'||focusHint)return;
        if(tip.contains(e.target)){clearTimeout(hideTimer);return;}
        const next=tooltipTarget(e.target);if(next&&next===target){clearTimeout(hideTimer);return;}
        if(next&&next===pendingTarget)return;
        hideTip();if(next){pendingTarget=next;showTimer=setTimeout(()=>showTip(next),350);}
    });
    document.addEventListener('pointerout',e=>{
        if(focusHint)return;
        const next=tooltipTarget(e.relatedTarget);
        if((next&&(next===target||next===pendingTarget))||tip.contains(e.relatedTarget))return;
        clearTimeout(showTimer);pendingTarget=null;clearTimeout(hideTimer);hideTimer=setTimeout(hideTip,100);
    });
    // Layout/scroll can fire pointer events without any mouse movement. A
    // keyboard hint remains until focus leaves, Escape or a pointer press.
    document.addEventListener('focusin',e=>{if(e.target.matches(':focus-visible'))showTip(tooltipTarget(e.target),true);});
    document.addEventListener('focusout',hideTip);
    document.addEventListener('pointerdown',hideTip);
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&target){e.preventDefault();e.stopPropagation();hideTip();}},true);
    document.addEventListener('scroll',()=>{
        if(target?.contains(document.activeElement)&&document.activeElement.matches(':focus-visible')){
            const r=target.getBoundingClientRect();
            if(r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth)placeTip();else hideTip();
        }else hideTip();
    },true);window.addEventListener('resize',hideTip);
    // Preview reserves the same responsive dimensions as a future ad creative.
    // Actual ads require a separate consent/provider integration before launch.
    if(new URLSearchParams(location.search).get('ad_preview')==='1'){
        for(const slot of document.querySelectorAll('[data-ad-slot]')){slot.hidden=false;slot.dataset.preview='true';}
    }
})();
