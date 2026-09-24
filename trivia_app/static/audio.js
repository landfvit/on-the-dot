/* Local Web Audio effects: no downloads, tracking, background music or game rules.
 * Tune sound recipes in play(); all amplitudes pass through one volume control.
 * A gesture unlocks audio, but blocked/muted sounds are dropped, never queued. */
(() => {
    'use strict';
    const key='onthedot.audio',Audio=window.AudioContext||window.webkitAudioContext;
    const voices=new Set(),lastPlayed=new Map();
    const clamp=value=>Math.max(0,Math.min(1,value));
    let context=null,master=null,noise=null,settings=readSettings(),crowdActive=false,ambience=null;
    const crowdBuffers=new Map();
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
        else startAmbience();
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
            startAmbience();
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
    // Locally synthesized audience: many detuned voices, diffuse noise and
    // scattered applause. Cache low-rate stereo PCM once per audio context;
    // it needs no download or per-frame work while the game is running.
    function crowdBuffer(kind){
        if(crowdBuffers.has(kind))return crowdBuffers.get(kind);
        const rate=24000,duration=kind==='ambience'?4:kind==='cheer'?2.8:1.9;
        const buffer=context.createBuffer(2,Math.ceil(rate*duration),rate);
        for(let channel=0;channel<2;channel++){
            const data=buffer.getChannelData(channel),phases=Array.from({length:8},(_,i)=>i*1.7+channel);
            let seed=713+channel*111,low=0,clap=0;
            const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
            for(let i=0;i<data.length;i++){
                const t=i/rate,p=t/duration,n=random()*2-1;
                low=.88*low+.12*n;
                let voices=0;
                for(let v=0;v<phases.length;v++){
                    const pitch=(115+v*19+channel*3)*(kind==='groan'?1-.28*p:1+.08*Math.sin(p*Math.PI));
                    phases[v]+=2*Math.PI*pitch/rate;
                    const a=phases[v],variation=.55+.45*Math.sin(t*(2+v*.23)+v)**2;
                    voices+=variation*(Math.sin(a)+.45*Math.sin(a*2)+.25*Math.sin(a*5));
                }
                if(kind==='cheer'&&random()<22/rate)clap=.6+random()*.4;
                clap*=.992;
                const fade=Math.min(1,t/.18,(duration-t)/.55);
                // Ambience loops through a quiet seam. Reactions rise quickly
                // and decay naturally, leaving the question/click sounds clear.
                data[i]=fade*(voices*(kind==='ambience'?.008:.028)+low*.6+n*(kind==='cheer'?.12:.05)+n*clap*.42);
            }
        }
        crowdBuffers.set(kind,buffer);return buffer;
    }
    function crowdVoice(kind,amplitude,loop=false){
        const source=context.createBufferSource(),gain=context.createGain();
        source.buffer=crowdBuffer(kind);source.loop=loop;gain.gain.value=amplitude;
        source.connect(gain);gain.connect(master);
        let cleaned=false;
        const item={source,crowd:true,clean(){if(cleaned)return;cleaned=true;voices.delete(item);source.disconnect();gain.disconnect();if(ambience===item)ambience=null;}};
        voices.add(item);source.onended=item.clean;source.start(context.currentTime);
        if(!loop)source.stop(context.currentTime+source.buffer.duration+.01);
        return item;
    }
    function startAmbience(){
        if(!crowdActive||ambience||!settings.enabled||!settings.volume||document.hidden||context?.state!=='running')return;
        try{crowdBuffer('cheer');crowdBuffer('groan');ambience=crowdVoice('ambience',.20,true);}catch{/* Audio never blocks gameplay. */}
    }
    function setCrowdActive(active){
        crowdActive=Boolean(active);
        if(crowdActive)startAmbience();
        else for(const item of [...voices])if(item.crowd){try{item.source.stop();}catch{}item.clean();}
    }
    function play(name){
        if(!['click','kick','catch','net','win','loss','crowd-cheer','crowd-groan'].includes(name)||!settings.enabled||!settings.volume||document.hidden||context?.state!=='running')return false;
        const now=context.currentTime;
        if(voices.size>=24||now-(lastPlayed.get(name)??-Infinity)<(name==='click'?.045:.025))return false;
        lastPlayed.set(name,now);
        try{
            // The kick combines a short leather snap and a falling low thump.
            if(name.startsWith('crowd-'))crowdVoice(name.slice(6),name==='crowd-cheer'?.90:.75);
            else if(name==='kick'){tone(now,155,48,.15,.65);air(now,.045,.38,1400,'bandpass');}
            else if(name==='catch'){air(now,.12,.5,1300);tone(now,105,52,.09,.22);}
            else if(name==='net')air(now,.19,.13,2400);
            else if(name==='click')tone(now,1250,720,.028,.07);
            else if(name==='win'){
                // Short ascending major arpeggio, with a soft sustained top note.
                [659.25,830.61,987.77,1318.51].forEach((hz,i)=>tone(now+i*.11,hz,hz,i===3?.42:.24,.19,'triangle'));
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
    window.addEventListener('pagehide',()=>{crowdActive=false;stop();context?.close().catch(()=>{});context=null;master=null;noise=null;crowdBuffers.clear();});
    window.addEventListener('storage',event=>{if(event.key===key){settings=readSettings();sync();}});
    window.PointsAudio={play,stop,setEnabled,setVolume,setCrowdActive,getSettings:()=>({...settings}),
        inspect:()=>({supported:Boolean(Audio),state:context?.state||'locked',activeVoices:voices.size,crowdActive,ambiencePlaying:Boolean(ambience)})};
    sync();
})();
