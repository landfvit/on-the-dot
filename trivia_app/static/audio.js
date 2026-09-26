/* Local Web Audio effects and two bundled, public-domain audience recordings.
 * No ambience loop. All amplitudes pass through one volume control.
 * A gesture unlocks audio, but blocked/muted sounds are dropped, never queued. */
(() => {
    'use strict';
    const key='onthedot.audio',Audio=window.AudioContext||window.webkitAudioContext;
    const voices=new Set(),lastPlayed=new Map();
    const clamp=value=>Math.max(0,Math.min(1,value));
    let context=null,master=null,noise=null,settings=readSettings(),crowdActive=false;
    const crowdBuffers=new Map(),crowdLoading=new Map();
    function readSettings(){
        try{const value=JSON.parse(localStorage.getItem(key)||'{}');return {enabled:value?.enabled!==false,
            volume:Number.isFinite(value?.volume)?clamp(value.volume):.5};}catch{return {enabled:true,volume:.5};}
    }
    function stop(){
        for(const voice of [...voices]){try{voice.source.stop();}catch{}voice.clean();}
        lastPlayed.clear();
    }
    function sync(){
        const audible=settings.enabled&&settings.volume>0;
        if(master)master.gain.setTargetAtTime(audible?settings.volume*.65:0,context.currentTime,.015);
        if(!audible)stop();
        else if(crowdActive)prepareCrowd();
        for(const button of document.querySelectorAll('[data-sound-toggle]')){
            button.disabled=!Audio;button.setAttribute('aria-pressed',String(audible));
            const label=Audio?(audible?'Mute sound':'Enable sound'):'Sound unavailable';
            button.title=label;button.setAttribute('aria-label',label);
            button.querySelector('img').src='/trivia-assets/icons/'+(audible?'volume-2':'volume-x')+'.svg';
        }
        for(const slider of document.querySelectorAll('[data-sound-volume]')){slider.value=Math.round(settings.volume*100);slider.disabled=!Audio;}
        for(const output of document.querySelectorAll('[data-sound-level]'))output.textContent=Math.round(settings.volume*100)+'%';
    }
    function save(){try{localStorage.setItem(key,JSON.stringify(settings));}catch{}sync();}
    function setEnabled(enabled){settings.enabled=Boolean(enabled);if(enabled&&!settings.volume)settings.volume=.5;save();}
    function setVolume(volume){if(Number.isFinite(volume)){settings.volume=clamp(volume);save();}}
    async function unlock(){
        if(!Audio||document.hidden||!settings.enabled||!settings.volume)return false;
        try{
            if(!context||context.state==='closed'){
                context=new Audio();master=context.createGain();master.gain.value=settings.volume*.65;
                // A gentle limiter protects against rapid overlapping UI/shot sounds.
                const limiter=context.createDynamicsCompressor();limiter.threshold.value=-10;
                limiter.knee.value=12;limiter.ratio.value=8;limiter.attack.value=.003;limiter.release.value=.12;
                master.connect(limiter);limiter.connect(context.destination);
                noise=context.createBuffer(1,Math.ceil(context.sampleRate*.3),context.sampleRate);
                const data=noise.getChannelData(0);for(let i=0;i<data.length;i++)data[i]=Math.random()*2-1;
            }
            if(context.state!=='running')await context.resume();
            if(crowdActive)prepareCrowd();
            return context.state==='running'&&!document.hidden;
        }catch{return false;}
    }
    function voice(source,start,duration,amplitude,filter=null){
        const gain=context.createGain();gain.gain.setValueAtTime(.0001,start);
        gain.gain.exponentialRampToValueAtTime(amplitude,start+.003);
        gain.gain.exponentialRampToValueAtTime(.0001,start+duration);
        if(filter){source.connect(filter);filter.connect(gain);}else source.connect(gain);
        gain.connect(master);
        const item={source,clean(){voices.delete(item);source.disconnect();gain.disconnect();filter?.disconnect();}};
        voices.add(item);source.onended=()=>item.clean();source.start(start);source.stop(start+duration+.01);
    }
    function tone(start,frequency,end,duration,amplitude,type='sine'){
        const oscillator=context.createOscillator();oscillator.type=type;
        oscillator.frequency.setValueAtTime(frequency,start);oscillator.frequency.exponentialRampToValueAtTime(end,start+duration);
        voice(oscillator,start,duration,amplitude);
    }
    function air(start,duration,amplitude,frequency,type='lowpass'){
        const source=context.createBufferSource();source.buffer=noise;
        const filter=context.createBiquadFilter();filter.type=type;filter.frequency.value=frequency;filter.Q.value=.7;
        voice(source,start,duration,amplitude,filter);
    }
    // Decode while the camera enters. A late/failed download never queues an
    // old reaction over a later question. Files are served by this app only.
    function prepareCrowd(){
        if(!context)return;
        const owner=context;
        for(const kind of ['cheer','groan']){
            if(crowdBuffers.has(kind)||crowdLoading.has(kind))continue;
            const loading=fetch(`/trivia-assets/sounds/crowd-${kind}.wav?v=1`)
                .then(response=>{if(!response.ok)throw new Error('Audio unavailable');return response.arrayBuffer();})
                .then(data=>owner.decodeAudioData(data))
                .then(buffer=>{if(context===owner)crowdBuffers.set(kind,buffer);})
                .catch(()=>{})
                .finally(()=>{if(crowdLoading.get(kind)===loading)crowdLoading.delete(kind);});
            crowdLoading.set(kind,loading);
        }
    }
    function crowdVoice(kind){
        const buffer=crowdBuffers.get(kind);
        if(!crowdActive||!buffer)return false;
        // Only one audience reaction at a time, including reduced-motion play.
        for(const item of [...voices])if(item.crowd){try{item.source.stop();}catch{}item.clean();}
        const source=context.createBufferSource(),gain=context.createGain();
        const now=context.currentTime,duration=Math.min(buffer.duration,kind==='cheer'?2.6:1.5);
        const volume=kind==='cheer'?.32:.35; // Reaction level before the user's master volume.
        source.buffer=buffer;source.loop=false;
        gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(volume,now+.04);
        gain.gain.setValueAtTime(volume,now+Math.max(.05,duration-.35));gain.gain.linearRampToValueAtTime(0,now+duration);
        source.connect(gain);gain.connect(master);
        let cleaned=false;
        const item={source,crowd:true,clean(){if(cleaned)return;cleaned=true;voices.delete(item);source.disconnect();gain.disconnect();}};
        voices.add(item);source.onended=item.clean;source.start(now);source.stop(now+duration+.01);
        return true;
    }
    function setCrowdActive(active){
        crowdActive=Boolean(active);
        if(crowdActive&&settings.enabled&&settings.volume)prepareCrowd();
        else for(const item of [...voices])if(item.crowd){try{item.source.stop();}catch{}item.clean();}
    }
    function play(name){
        if(!['click','kick','catch','net','win','loss','level-up','crowd-cheer','crowd-groan'].includes(name)||!settings.enabled||!settings.volume||document.hidden||context?.state!=='running')return false;
        const now=context.currentTime;
        if(voices.size>=24||now-(lastPlayed.get(name)??-Infinity)<(name==='click'?.045:.025))return false;
        lastPlayed.set(name,now);
        try{
            // The kick combines a short leather snap and a falling low thump.
            if(name.startsWith('crowd-'))return crowdVoice(name.slice(6));
            else if(name==='kick'){tone(now,155,48,.15,.65);air(now,.045,.38,1400,'bandpass');}
            else if(name==='catch'){air(now,.12,.5,1300);tone(now,105,52,.09,.22);}
            else if(name==='net')air(now,.19,.13,2400);
            else if(name==='click')tone(now,1250,720,.028,.07);
            else if(name==='win'){
                // Short ascending major arpeggio, with a soft sustained top note.
                [659.25,830.61,987.77,1318.51].forEach((hz,i)=>tone(now+i*.11,hz,hz,i===3?.42:.24,.19,'triangle'));
            }else if(name==='level-up'){
                [783.99,1046.5,1567.98].forEach((hz,i)=>tone(now+i*.09,hz,hz,i===2?.36:.16,.12,'sine'));
            }else [329.63,293.66,220].forEach((hz,i)=>tone(now+i*.15,hz,hz,i===2?.36:.2,.16,'triangle'));
            return true;
        }catch{stop();return false;}
    }
    // Never autoplay on initial page load. Pointer and keyboard input also
    // re-unlock Safari/Chrome after the browser interrupts the audio session.
    const gesture=event=>{if(event.isTrusted)void unlock();};
    document.addEventListener('pointerdown',gesture,{capture:true,passive:true});
    document.addEventListener('pointerup',gesture,{capture:true,passive:true});
    document.addEventListener('keydown',gesture,{capture:true});
    document.addEventListener('click',event=>{
        if(!event.isTrusted)return;
        // Touch browsers may grant activation on release/click, not touch-down.
        gesture(event);
        const control=event.target.closest?.('button,a[href],input[type="radio"],input[type="checkbox"],summary');
        if(!control||control.disabled||control.closest('[inert],[data-sound-toggle]')||control.getAttribute('aria-disabled')==='true')return;
        play('click');
    },true);
    for(const button of document.querySelectorAll('[data-sound-toggle]'))button.addEventListener('click',async event=>{
        const enabled=!(settings.enabled&&settings.volume>0);setEnabled(enabled);
        if(enabled&&event.isTrusted&&await unlock())play('click');
    });
    for(const slider of document.querySelectorAll('[data-sound-volume]')){
        slider.addEventListener('input',()=>setVolume(Number(slider.value)/100));
        slider.addEventListener('change',()=>play('click'));
    }
    document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();context?.suspend().catch(()=>{});}});
    window.addEventListener('pagehide',()=>{crowdActive=false;stop();context?.close().catch(()=>{});context=null;master=null;noise=null;crowdBuffers.clear();crowdLoading.clear();});
    window.addEventListener('storage',event=>{if(event.key===key){settings=readSettings();sync();}});
    window.PointsAudio={play,stop,setEnabled,setVolume,setCrowdActive,getSettings:()=>({...settings}),
        inspect:()=>({supported:Boolean(Audio),state:context?.state||'locked',activeVoices:voices.size,crowdActive,ambiencePlaying:false,crowdReady:crowdBuffers.size===2})};
    sync();
})();
