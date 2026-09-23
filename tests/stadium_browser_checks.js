/* DOM diagnostics for the isolated preview; no game state is changed. */
(() => {
    const output=document.createElement('output');output.id='animation-checks';output.hidden=true;document.body.append(output);
    const report={frames:0,fadeFrames:0,maxRevealStep:0,errors:[],roles:[],phases:[]};
    let previous=0;
    const error=message=>{if(!report.errors.includes(message))report.errors.push(message);};
    window.addEventListener('error',event=>error(event.message));
    window.addEventListener('unhandledrejection',event=>error(String(event.reason)));
    function frame(){
        const view=window.PointsStadium?.inspect();
        if(view?.active){
            report.frames++;
            if(!report.roles.includes(view.role))report.roles.push(view.role);
            if(!report.phases.includes(view.phase))report.phases.push(view.phase);
            if(!view.markingsVisible)error('Pitch markings left the sharp layer');
            if(!view.environmentVisible||!view.standsSolid||view.geometryFocus!==0)error('Blur changed stadium geometry');
            if(!view.keeperVisible||!view.ballVisible)error('Keeper or ball hidden');
            if(view.caught&&view.ball.some((n,i)=>Math.abs(n-view.hands[i])>.001))error('Saved ball detached from gloves');
        }
        if(document.body.classList.contains('stadium-ending')){
            const reveal=Number(document.body.style.getPropertyValue('--stadium-result'));
            const stage=document.querySelector('#stadium-layer'),panel=document.querySelector('.solo-questions');
            const stageOpacity=Number(getComputedStyle(stage).opacity),panelOpacity=Number(getComputedStyle(panel).opacity);
            if(Math.abs(stageOpacity+panelOpacity-1)>.001)error('Stage and results crossfade out of sync');
            if(reveal>0&&reveal<1){
                report.fadeFrames++;
                if(view.camera[1]<100||view.focus!==0)error('Fade began before full-detail overhead view');
            }
            if(stage.hidden&&reveal<1)error('Stage hidden before fade completed');
            if(reveal<previous)error('Results fade reversed');
            report.maxRevealStep=Math.max(report.maxRevealStep,reveal-previous);previous=reveal;
            report.final={reveal,stageOpacity,panelOpacity,hidden:stage.hidden};
        } else previous=0;
        output.textContent=JSON.stringify(report);
        requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
})();
