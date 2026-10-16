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
    const inline=Boolean($('stadium-stage'));
    let animationsEnabled=globalThis.PointsPreferences?.get().animations!==false;
    let engine = null, modules = null, version = 0, available = true, active = false, entering = false;
    let config = null, restoreFocus = null, lastShot = null;
    let loadAttempt=0,requestedRole='shooter',wanted=false,retrying=false,lastError=null;
    let recoveryTimer=null,autoRecoveryUsed=false,compatibility=false;
    let outfits=null,outfitKey='',outfitRevision=0;
    async function setOutfits(local,opponent){
        const key=JSON.stringify([local||null,opponent||null]);if(key===outfitKey)return;
        outfitKey=key;const revision=++outfitRevision;
        if(!local?.kit_id&&!opponent?.kit_id){outfits=[null,null];engine?.setOutfits(outfits);return;}
        try {
            const {loadKits}=await import('./kit_pixels.js?v=4');
            const data=await loadKits();if(revision!==outfitRevision)return;
            outfits=[local,opponent].map(choice=>({kit:data.kits.find(k=>k.id===choice?.kit_id)||null,number:choice?.number||10}));
            engine?.setOutfits(outfits);
        }catch(error){
            // Cosmetics never gate Ready, start a question timer, or fail 3D.
            outfitKey='';console.warn('Kit artwork unavailable; using default shirts.',error);
        }
    }
    try { compatibility=sessionStorage.getItem('points.stadium.compatibility')==='1'; } catch {}
    const motion = () => !reduced.matches && animationsEnabled && globalThis.PointsPreferences?.get().reduced_motion!==true;
    function syncMotionControl(){
        if(!motionToggle)return;
        const reducedMotion=reduced.matches||globalThis.PointsPreferences?.get().reduced_motion===true;
        const enabled=motion(),label=reducedMotion?'Animations disabled by reduced motion':enabled?'Disable animations':'Enable animations';
        motionToggle.disabled=reducedMotion;motionToggle.setAttribute('aria-pressed',String(enabled));
        motionToggle.setAttribute('aria-label',label);motionToggle.title=label;
        motionToggle.querySelector('img').src='/trivia-assets/icons/'+(enabled?'monitor':'monitor-off')+'.svg';
    }
    syncMotionControl();

    // Lokalne hostovana Three.js: zadne CDN requesty ani sledovani uzivatele.
    // Pri chybe se ukaze upozorneni. Zadny 2D renderer se uz nenacita.
    function load() {
        if (!modules) {
            // Change the whole relative import graph, not just the entry URL:
            // Safari also caches failed world/config/Three.js dependencies.
            const prefix=loadAttempt++?`./_retry/${loadAttempt}/`:'./';
            const pending=Promise.all([import(`${prefix}stadium_scene.js?v=37`), import(`${prefix}stadium_config.js?v=28`)]);
            modules=pending;
            pending.catch(()=>{if(modules===pending)modules=null;});
        }
        return modules;
    }
    async function prepare() { try { await load(); } catch { /* Chybu zobrazime az pri vstupu do hry. */ } }
    function reveal(amount) { document.body.style.setProperty('--stadium-reveal',String(inline?1:amount)); }
    function panels(inert) {
        for (const selector of inline?['.solo-questions']:['.solo-questions','.question-column','#shootout-hud']) {
            const panel = document.querySelector(selector); if (panel) panel.inert = inert;
        }
    }
    function complete() {
        entering = false;document.body.classList.remove('stadium-entering');panels(false);
        // The last GPU/RAF frame is not a reliable UI completion signal.
        // Always remove the reveal mask when camera travel ends or is skipped.
        reveal(1);
        $('stadium-skip').hidden = true;
        if (restoreFocus?.isConnected) restoreFocus.focus({preventScroll:true});
        restoreFocus = null;
    }
    function skip() { engine?.skip(); complete(); }
    function hide() {
        globalThis.PointsAudio?.setCrowdActive?.(false);
        version++;active=false;entering=false;engine?.suspend();complete();
        document.body.classList.remove('stadium-playing','stadium-ending');$('stadium-layer').hidden=true;
        $('stadium-controls').hidden=true;$('stadium-outcome').hidden=true;
        if(inline)$('stadium-loading').hidden=true;
        reveal(1);
    }
    function leave() {
        clearTimeout(recoveryTimer);
        wanted=false;lastShot=null;hide();$('stadium-unavailable').hidden=true;
        if(inline){$('stadium-stage').hidden=true;motionToggle.hidden=true;}
    }
    function fallback(error) {
        lastError=error instanceof Error?error.message:String(error||'WebGL rendering failed');
        console.warn('Stadium 3D failed:',error||lastError);
        available=false;hide();engine?.dispose();engine=null;$('stadium-unavailable').hidden=false;
        const message=$('stadium-error-message');
        if(message)message.textContent=/timed out|fetch|import|module/i.test(lastError)?'Stadium download interrupted.':/context|WebGL/i.test(lastError)?'3D graphics could not start.':'Stadium rendering stopped.';
        const detail=$('stadium-error-detail');
        if(detail&&['127.0.0.1','localhost','[::1]'].includes(location.hostname)){
            // Local diagnostics only: no telemetry, account data or remote logs.
            detail.textContent=(error?.name||'Error')+': '+lastError;detail.hidden=false;
        }
        if(/WebGL.*context|context.*lost/i.test(lastError)){
            // Context loss is often transient. Rebuild once with less GPU
            // pressure; never loop indefinitely or advance a game/question.
            compatibility=true;
            try { sessionStorage.setItem('points.stadium.compatibility','1'); } catch {}
            if(wanted&&!autoRecoveryUsed){autoRecoveryUsed=true;recoveryTimer=setTimeout(()=>retry(),750);}
        }
    }
    async function enter(role, {intro=false, maxDurationMs=Infinity}={}) {
        requestedRole=role;wanted=true;
        if(inline){$('stadium-stage').hidden=false;delete $('stadium-stage').dataset.ending;motionToggle.hidden=false;}
        if (!available) { $('stadium-unavailable').hidden=false;return false; }
        if(inline)$('stadium-loading').hidden=false;
        const own=++version,requestedAt=performance.now();
        let timer,viewTimer;
        try {
            // One automatic retry covers a transient dependency request failure;
            // persistent failures still expose the explicit Retry 3D control.
            const [module, settings] = await Promise.race([load().catch(()=>load()),new Promise((_,reject)=>{
                // Loading the Three.js module on a cold connection is not a
                // WebGL failure. This timeout never changes the answer clock.
                timer=setTimeout(()=>{
                    // A stalled import never rejects. Retire its entire module
                    // graph so Retry cannot get stuck on the same promise.
                    if(own===version)modules=null;
                    reject(new Error('Scene loading timed out'));
                },12000);
            })]);
            clearTimeout(timer);
            if(own!==version)return false;
            if(inline)$('stadium-loading').hidden=true;
            config=inline?settings.COMPACT_STADIUM:settings.STADIUM;
            document.body.classList.remove('stadium-ending');
            $('stadium-layer').hidden=false;
            if(!engine)engine=module.createStadium($('stadium-layer'),$('stadium-framing'),fallback,reveal,{compatibility,presentation:inline?'compact':'cinematic'});
            if(outfits)engine.setOutfits(outfits);
            active=true;document.body.classList.toggle('stadium-playing',!inline);$('stadium-controls').hidden=false;
            globalThis.PointsAudio?.setCrowdActive?.(true);
            $('stadium-unavailable').hidden=true;
            $('stadium-outcome').hidden=true;
            const availableMs=maxDurationMs-(performance.now()-requestedAt);
            const sameRole=engine.inspect().role===role&&engine.inspect().phase==='ready';
            const duration=motion()?Math.max(0,Math.min(intro?config.introMs:sameRole?0:config.roleChangeMs,availableMs)):0;
            entering=duration>0;document.body.classList.toggle('stadium-entering',entering);panels(entering);
            $('stadium-skip').hidden=!entering;
            if(entering){restoreFocus=document.activeElement;$('stadium-skip').focus({preventScroll:true});}
            const view=engine.setView(role,{intro,duration});
            // A throttled/suspended RAF can strand READY behind an inert, masked
            // panel without throwing. Bound presentation only: never fetch the
            // first question, consume a life, or start its server-owned clock.
            await Promise.race([view,new Promise(resolve=>{
                viewTimer=setTimeout(()=>{
                    if(own===version){
                        console.warn('Stadium camera did not finish; skipping to the playable view.');
                        try { skip(); } catch(error) { fallback(error); }
                    }
                    resolve();
                },duration+2000);
            })]);
            if(own===version){lastError=null;complete();if(lastShot)showShot(false);}
            return own===version&&active;
        } catch (error) {
            if(own===version)fallback(error);return false;
        } finally { clearTimeout(timer);clearTimeout(viewTimer); }
    }
    async function retry() {
        if(!wanted||retrying)return false;
        clearTimeout(recoveryTimer);
        retrying=true;available=true;
        const button=$('stadium-retry');if(button)button.disabled=true;
        try {
            // Restore the current camera/result silently. Do not replay the
            // intro, submit an answer, open a question or reset its deadline.
            return await enter(requestedRole,{intro:false,maxDurationMs:0});
        } finally {retrying=false;if(button)button.disabled=false;}
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
        clearTimeout(recoveryTimer);
        wanted=false;
        if(!active||!engine){leave();return;}
        const own=++version;lastShot=null;entering=false;panels(true);
        document.body.style.setProperty('--stadium-result','0');
        if(inline){
            // Result layout replaces the question immediately. Pin the outgoing
            // canvas to its last rendered rectangle so the crossfade cannot zoom.
            const stage=$('stadium-stage'),viewport=engine.inspect().viewport;
            if(viewport)for(const key of ['left','top','width','height'])stage.style.setProperty(`--stadium-result-${key}`,`${viewport[key]}px`);
            stage.dataset.ending='true';
        }else document.body.classList.add('stadium-ending');
        const duration=motion()?config.outroMs:0;
        let timer;
        try {
            await Promise.race([
                engine.finish(duration,amount=>document.body.style.setProperty('--stadium-result',String(amount))),
                new Promise(resolve=>{timer=setTimeout(()=>{if(own===version)engine?.skip();resolve();},duration+2000);})
            ]);
        } catch(error) {
            if(own===version){fallback(error);leave();document.body.style.setProperty('--stadium-result','1');}
        }
        finally { clearTimeout(timer); }
        if(own!==version)return;
        panels(false);$('stadium-layer').hidden=true;$('stadium-controls').hidden=true;active=false;
        document.body.style.setProperty('--stadium-result','1');
        if(inline){$('stadium-stage').hidden=true;motionToggle.hidden=true;}
        globalThis.PointsAudio?.setCrowdActive?.(false);
    }
    function reset() { lastShot=null;if(active){engine?.reset();$('stadium-outcome').hidden=true;} }
    $('stadium-skip').addEventListener('click',skip);
    $('stadium-retry')?.addEventListener('click',retry);
    // Presentation only: finish camera travel or show the resolved shot pose.
    // Never request a question, change a deadline, or discard a visible result.
    function applyMotion(){
        syncMotionControl();
        if(!motion()){skip();if(lastShot)showShot(false);}
    }
    motionToggle?.addEventListener('click',()=>{animationsEnabled=!animationsEnabled;applyMotion();});
    window.addEventListener('points-preferences',()=>{
        animationsEnabled=globalThis.PointsPreferences?.get().animations!==false;applyMotion();
    });
    reduced.addEventListener('change',applyMotion);
    window.addEventListener('keydown',event=>{if(event.key==='Escape'&&entering)skip();});
    window.addEventListener('pagehide',event=>{
        clearTimeout(recoveryTimer);
        // Back/forward cache keeps the game's JS state but not a reliable GPU
        // context. Keep the desired role/result, and rebuild only presentation.
        if(event.persisted)hide();else leave();
        engine?.dispose();engine=null;available=true;
    });
    window.addEventListener('pageshow',event=>{
        if(event.persisted&&wanted)enter(requestedRole,{intro:false,maxDurationMs:0});
    });
    // inspect() je pouze diagnostika kamery pro vizualni testy, ne herni stav.
    window.PointsStadium={prepare,enter,skip,leave,shot,reset,finish,retry,setOutfits,
        inspect:()=>({active,entering,motionEnabled:motion(),lastError,compatibility,...engine?.inspect()})};
    prepare();
})();
