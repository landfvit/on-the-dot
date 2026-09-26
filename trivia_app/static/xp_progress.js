/* XP is awarded by the server. This module only presents its committed totals
 * and level thresholds, including a bar rollover for each crossed level. */
(() => {
    'use strict';
    function segments(transition){
        if(!transition?.before||!transition?.after||!Array.isArray(transition.levels))return [];
        const {before,after,levels}=transition;
        if(!Number.isFinite(before.total_xp)||!Number.isFinite(after.total_xp)||after.total_xp<=before.total_xp)return [];
        const result=[];
        for(let i=0;i<levels.length;i++){
            const level=levels[i],next=levels[i+1];
            if(level.level<before.level||level.level>after.level)continue;
            const start=Math.max(before.total_xp,level.minimum_xp),end=Math.min(after.total_xp,next?.minimum_xp??after.total_xp);
            if(end<start)return [];
            result.push({start,end,progress:{level:level.level,level_xp:level.minimum_xp,next_level_xp:next?.minimum_xp??null},
                reached:next&&end===next.minimum_xp&&next.level<=after.level?next.level:null});
        }
        return result;
    }
    function bindResult(){
        const $=id=>document.getElementById(id),box=$('result-level');
        if(!box)return null;
        const bar=$('result-level-progress'),label=$('result-level-label'),remaining=$('result-level-remaining');
        const total=$('result-xp-total'),notice=$('result-level-up');
        let id=null,transition=null,final=null,pending=false,raf=0,generation=0,chimed=false;
        const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches||globalThis.PointsPreferences?.get().reduced_motion===true||
            globalThis.PointsPreferences?.get().animations===false||globalThis.PointsStadium?.inspect().motionEnabled===false;
        function paint(progress,xp=progress.total_xp){
            const maximum=progress.next_level_xp===null;
            label.textContent='Level '+progress.level;
            bar.max=maximum?1:Math.max(1,progress.next_level_xp-progress.level_xp);
            bar.value=maximum?1:Math.max(0,Math.min(bar.max,xp-progress.level_xp));
            total.textContent=Math.round(xp).toLocaleString('en-GB')+' total XP';
            remaining.textContent=maximum?'Maximum level':`${Math.max(0,progress.next_level_xp-Math.round(xp))} XP to level ${progress.level+1}`;
        }
        function stop(){generation++;cancelAnimationFrame(raf);raf=0;}
        function celebrate(level,animate){
            notice.hidden=false;notice.textContent='Level '+level+' unlocked!';
            if(animate){box.classList.remove('is-level-up');void box.offsetWidth;box.classList.add('is-level-up');}
            if(!chimed&&!document.hidden){chimed=true;globalThis.PointsAudio?.play('level-up');}
        }
        function prepare(run,{animate=false}={}){
            if(id===run.run_id)return;
            stop();id=run.run_id;final=run.player_progress;transition=run.xp_transition;
            pending=Boolean(animate&&!run.is_trial&&final&&transition?.earned_xp>0&&segments(transition).length);
            chimed=false;notice.hidden=true;notice.textContent='';box.classList.remove('is-level-up');
            if(final&&!run.is_trial)paint(pending?transition.before:final);
        }
        function reveal(){
            if(!pending||!final)return;pending=false;
            if(document.hidden){paint(final);return;}
            if(reduced()){
                paint(final);
                if(final.level>transition.before.level)celebrate(final.level,false);
                return;
            }
            const steps=segments(transition),own=++generation,duration=Math.min(900,2600/steps.length);
            let index=0,started=null;
            function frame(now){
                if(own!==generation)return;
                if(document.hidden||reduced()){paint(final);stop();return;}
                if(started===null)started=now;
                const step=steps[index],t=Math.min(1,(now-started)/duration),ease=1-(1-t)**3;
                paint(step.progress,step.start+(step.end-step.start)*ease);
                if(t===1){
                    if(step.reached)celebrate(step.reached,true);
                    index++;started=null;
                    if(index===steps.length){paint(final);raf=0;return;}
                }
                raf=requestAnimationFrame(frame);
            }
            raf=requestAnimationFrame(frame);
        }
        function clear(){stop();id=null;pending=false;final=null;transition=null;notice.hidden=true;box.classList.remove('is-level-up');}
        document.addEventListener('visibilitychange',()=>{if(document.hidden&&final){pending=false;stop();paint(final);}});
        window.addEventListener('pagehide',clear);
        return {prepare,reveal,clear};
    }
    globalThis.PointsProgress={segments,bindResult};
})();
