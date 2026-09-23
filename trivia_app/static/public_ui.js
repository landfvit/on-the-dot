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
    // Preview reserves the same responsive dimensions as a future ad creative.
    // Actual ads require a separate consent/provider integration before launch.
    if(new URLSearchParams(location.search).get('ad_preview')==='1'){
        for(const slot of document.querySelectorAll('[data-ad-slot]')){slot.hidden=false;slot.dataset.preview='true';}
    }
})();
