/* Propojeni 3D prezentace s aplikaci. Zadny z techto callbacku nesmi posilat
 * odpoved, menit skore nebo posouvat otazku. Ready/Next stale ovlada hra.
 * Public API je male, aby slo renderer pozdeji vymenit bez zmen pravidel.
 */
(function () {
    'use strict';
    const $ = id => document.getElementById(id);
    if (!$('stadium-layer')) return;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const motionToggle=$('motion-toggle');
    if(motionToggle){motionToggle.disabled=reduced.matches;motionToggle.checked=!reduced.matches&&globalThis.PointsPreferences?.get().animations!==false;}
    let engine = null, modules = null, version = 0, available = true, active = false, entering = false;
    let config = null, restoreFocus = null, lastShot = null;
    const motion = () => !reduced.matches && $('motion-toggle')?.checked !== false && globalThis.PointsPreferences?.get().reduced_motion!==true;

    // Lokalne hostovana Three.js: zadne CDN requesty ani sledovani uzivatele.
    // Pri chybe se ukaze upozorneni. Zadny 2D renderer se uz nenacita.
    function load() {
        if (!modules) modules = Promise.all([import('./stadium_scene.js?v=12'), import('./stadium_config.js?v=10')]);
        return modules;
    }
    async function prepare() { try { await load(); } catch { /* Chybu zobrazime az pri vstupu do hry. */ } }
    function reveal(amount) { document.body.style.setProperty('--stadium-reveal',String(amount)); }
    function panels(inert) {
        for (const selector of ['.solo-questions','.question-column']) {
            const panel = document.querySelector(selector); if (panel) panel.inert = inert;
        }
    }
    function complete() {
        entering = false;document.body.classList.remove('stadium-entering');panels(false);
        $('stadium-skip').hidden = true;
        if (restoreFocus?.isConnected) restoreFocus.focus({preventScroll:true});
        restoreFocus = null;
    }
    function skip() { engine?.skip(); complete(); }
    function hide() {
        version++;active=false;entering=false;engine?.suspend();complete();
        document.body.classList.remove('stadium-playing','stadium-ending');$('stadium-layer').hidden=true;
        $('stadium-controls').hidden=true;$('stadium-outcome').hidden=true;
        reveal(1);
    }
    function leave() { lastShot=null;hide();$('stadium-unavailable').hidden=true; }
    function fallback() { available=false;hide();engine?.dispose();engine=null;$('stadium-unavailable').hidden=false; }
    async function enter(role, {intro=false, maxDurationMs=Infinity}={}) {
        if (!available) { $('stadium-unavailable').hidden=false;return false; }
        const own=++version,requestedAt=performance.now();
        let timer;
        try {
            const [module, settings] = await Promise.race([load(),new Promise((_,reject)=>{
                timer=setTimeout(()=>reject(new Error('Scene loading timed out')),3500);
            })]);
            if(own!==version)return false;
            config=settings.STADIUM;
            document.body.classList.remove('stadium-ending');
            $('stadium-layer').hidden=false;
            if(!engine)engine=module.createStadium($('stadium-layer'),$('stadium-framing'),fallback,reveal);
            active=true;document.body.classList.add('stadium-playing');$('stadium-controls').hidden=false;
            $('stadium-unavailable').hidden=true;
            $('stadium-role').textContent=role==='keeper'?'Goalkeeper':'Penalty taker';
            $('stadium-outcome').hidden=true;
            const availableMs=maxDurationMs-(performance.now()-requestedAt);
            const sameRole=engine.inspect().role===role&&engine.inspect().phase==='ready';
            const duration=motion()?Math.max(0,Math.min(intro?config.introMs:sameRole?0:config.roleChangeMs,availableMs)):0;
            entering=duration>0;document.body.classList.toggle('stadium-entering',entering);panels(entering);
            $('stadium-skip').hidden=!entering;
            if(entering){restoreFocus=document.activeElement;$('stadium-skip').focus({preventScroll:true});}
            await engine.setView(role,{intro,duration});
            if(own===version){complete();if(lastShot)showShot(false);}
            return own===version&&active;
        } catch {
            if(own===version)fallback();return false;
        } finally { clearTimeout(timer); }
    }
    function showShot(animated,withSound=false) {
        if(!active||!engine)return;
        const {outcome,plan}=lastShot;
        // Restoring a visual pose is silent. Only a newly presented shot gets
        // cues from its actual animation frames, never from wall-clock timers.
        skip();const completion=engine.shot(outcome,animated,plan,withSound?cue=>globalThis.PointsAudio?.play(cue):undefined);
        $('stadium-outcome').hidden=false;
        $('stadium-outcome').textContent={goal:'GOAL',save:'SAVE',miss:'MISS',replay:'REPLAY'}[outcome]||'';
        return completion;
    }
    function shot(outcome,plan=globalThis.PenaltyShots.plan(outcome)) {
        lastShot={outcome,plan};return showShot(motion(),true);
    }
    async function finish(){
        if(!active||!engine){leave();return;}
        const own=++version;lastShot=null;entering=false;panels(true);
        document.body.style.setProperty('--stadium-result','0');
        document.body.classList.add('stadium-ending');
        await engine.finish(motion()?config.outroMs:0,amount=>document.body.style.setProperty('--stadium-result',String(amount)));
        if(own!==version)return;
        panels(false);$('stadium-layer').hidden=true;$('stadium-controls').hidden=true;active=false;
    }
    function reset() { lastShot=null;if(active){engine?.reset();$('stadium-outcome').hidden=true;} }
    // Skore a hodiny jen zrcadlime z herniho controlleru. V 3D tak zustanou
    // viditelne i na mobilu, kde je puvodni velky scoreboard skryty.
    function hud({score,clock}) {
        if(score!==undefined)$('stadium-score').textContent=score;
        if(clock!==undefined)$('stadium-clock').textContent=clock;
    }
    $('stadium-skip').addEventListener('click',skip);
    $('motion-toggle')?.addEventListener('change',()=>{if(!motion()){skip();reset();}});
    window.addEventListener('points-preferences',()=>{
        const preferences=globalThis.PointsPreferences?.get();if(motionToggle)motionToggle.checked=!reduced.matches&&preferences?.animations!==false;
        if(!motion()){skip();reset();}
    });
    reduced.addEventListener('change',()=>{
        if(motionToggle){motionToggle.disabled=reduced.matches;if(reduced.matches)motionToggle.checked=false;}
        if(reduced.matches){skip();reset();}
    });
    window.addEventListener('keydown',event=>{if(event.key==='Escape'&&entering)skip();});
    window.addEventListener('pagehide',()=>{leave();engine?.dispose();engine=null;});
    // inspect() je pouze diagnostika kamery pro vizualni testy, ne herni stav.
    window.PointsStadium={prepare,enter,skip,leave,shot,reset,hud,finish,
        inspect:()=>({active,entering,...engine?.inspect()})};
    prepare();
})();
