/* Close-up pixel penalty vignette. Role changes swap kits, not the camera.
 * The game supplies resolved outcomes; this module never advances a question.
 * Change proportions/colors in stadium_config.js, not the game controllers.
 */
import * as THREE from './vendor/three/three.module.min.js';
import {STADIUM,COMPACT_STADIUM} from './stadium_config.js?v=28';
import {createStadiumWorld} from './stadium_v6_world.js?v=31';
import {ballistic,bounceHeight} from './stadium_motion.js';
import {reactionForShot} from './crowd_reaction.js?v=1';

export function createStadium(host,framing,onFailure,onReveal=()=>{},{compatibility=false,presentation='compact'}={}) {
    const C=presentation==='compact'?COMPACT_STADIUM:STADIUM;
    const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(40,1,.07,250);
    const contextOptions={alpha:true,stencil:false,powerPreference:compatibility?'low-power':'default'};
    let renderer;
    try { renderer=new THREE.WebGLRenderer({...contextOptions,antialias:false}); }
    catch { renderer=new THREE.WebGLRenderer({...contextOptions,antialias:false}); }
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000,0);
    renderer.domElement.setAttribute('aria-label','Penalty area');
    renderer.domElement.style.imageRendering='pixelated';
    host.append(renderer.domElement);
    const v=(x=0,y=0,z=0)=>new THREE.Vector3(x,y,z);
    const clamp=x=>Math.max(0,Math.min(1,x)),smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
    const goalX=C.pitch.length/2,spotX=goalX-C.penalty.distance;
    const ballHome=v(spotX,C.penalty.ballRadius+.025,0);
    let role='shooter',phase='idle',disposed=false,failed=false,raf=0,progress=1;
    let width=1,height=1,viewport=null,completion=null,endingPose=null,endingProgress=0;
    let lastOutcome=null,lastPlan=null,caught=false;
    const abort=new AbortController(),on=(element,name,fn)=>element.addEventListener(name,fn,{signal:abort.signal});
    const resources=new Set();
    function collectResources() {
        scene.traverse(o=>{if(o.geometry)resources.add(o.geometry);for(const mat of [].concat(o.material||[]))resources.add(mat);});
    }
    let world;
    try { world=createStadiumWorld(scene); }
    catch(error) {
        collectResources();resources.forEach(r=>r.dispose());
        renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();throw error;
    }
    world.setTheme(document.documentElement.dataset.theme);
    on(window,'points-theme',()=>guard(()=>{world.setTheme(document.documentElement.dataset.theme);render();}));
    const {ball,keeperRig,strikerRig}=world,shooter=strikerRig.group,keeper=keeperRig.group;
    function focus(amount) { onReveal(amount); }
    function render() {
        // Outfits may arrive before ResizeObserver has framed the camera.
        // Projecting the pitch from the initial origin would produce NaNs.
        if(disposed||!viewport)return;
        if(renderer.getContext().isContextLost())throw new Error('WebGL context lost');
        world.shadows();
        world.prepareFrame(camera,renderer.domElement.height);
        // One render, no offscreen buffers, blur kernels or hidden stadium draw.
        renderer.render(scene,camera);
    }
    function framingSamples() {
        return [
            // Include net depth and every target, but do not waste the short
            // viewport fitting twenty metres of empty foreground grass.
            ...[goalX-.8,goalX+1.9].flatMap(x=>[-4.1,4.1].flatMap(z=>[v(x,0,z),v(x,2.8,z)])),
            ...[-.7,2.1].flatMap(z=>[v(spotX-2.5,0,z),v(spotX-2.5,2.2,z)]),
        ];
    }
    function pose(t=1) {
        progress=t;
        // Fit only the action envelope. The same close-up serves both roles;
        // kits change ownership without moving the UI or shrinking the goal.
        camera.position.copy(v(...C.camera.offset)).add(v(spotX));
        camera.lookAt(v(...C.camera.lookAt).add(v(spotX)));
        camera.updateMatrixWorld(true);
        const rect=framing.getBoundingClientRect(),origin=host.getBoundingClientRect();
        const points=framingSamples().map(p=>p.applyMatrix4(camera.matrixWorldInverse));
        const xs=points.map(p=>p.x/-p.z),ys=points.map(p=>p.y/-p.z);
        const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
        const focal=Math.max(1,Math.min(Math.max(rect.width,1)*C.camera.framingPadding/(maxX-minX),
            Math.max(rect.height,1)*C.camera.framingPadding/(maxY-minY)));
        const x=width/2+focal*(minX+maxX)/2-(rect.left-origin.left+rect.width/2);
        const y=height/2-focal*(minY+maxY)/2-(rect.top-origin.top+rect.height/2);
        camera.fov=THREE.MathUtils.radToDeg(2*Math.atan(height/(2*focal)));
        camera.setViewOffset(width,height,x,y,width,height);camera.updateProjectionMatrix();render();
    }
    function resize() {
        if(disposed)return;
        width=Math.max(1,host.clientWidth);height=Math.max(1,host.clientHeight);
        const rect=host.getBoundingClientRect();
        viewport={left:rect.left,top:rect.top,width:rect.width,height:rect.height};
        const budget=Math.min(compatibility?600000:Infinity,C.maxRenderPixels);
        const ratio=Math.min(devicePixelRatio||1,compatibility?1:C.maxPixelRatio,
            C.pixelArt.maxWidth/width,C.pixelArt.maxHeight/height,Math.sqrt(budget/(width*height)));
        renderer.setPixelRatio(1);
        renderer.setSize(Math.max(1,Math.floor(width*ratio)),Math.max(1,Math.floor(height*ratio)),false);
        renderer.domElement.style.width=width+'px';renderer.domElement.style.height=height+'px';
        camera.aspect=width/height;
        pose(progress);
    }
    function stop() {
        cancelAnimationFrame(raf);raf=0;
        if(completion){const done=completion;completion=null;done();}
    }
    // Keep recovery transactional: an asynchronous GPU failure must release
    // Ready/Next and dispose the context before the bridge starts a replacement.
    function fail(error) {
        if(disposed||failed)return;
        failed=true;phase='failed';stop();onFailure(error);
    }
    function guard(callback) {
        if(disposed||failed)return;
        try { callback(); } catch(error) { fail(error); }
    }
    function requestFrame(callback) { raf=requestAnimationFrame(now=>guard(()=>callback(now))); }
    function skip() {
        if(phase==='intro'){stop();phase='ready';focus(1);pose(1);}
        if(phase==='outro'){endingPose?.(1);phase='finished';stop();}
    }
    function suspend() { stop();phase='idle'; }
    function setView(nextRole,{intro=false,duration=0}={}) {
        stop();resetBall();role=nextRole==='keeper'?'keeper':'shooter';
        world.setRole(role);
        shooter.visible=true;keeper.visible=true;
        renderer.domElement.setAttribute('aria-label',role==='keeper'?'Defending the penalty':'Taking the penalty');
        phase=duration>0?'intro':'ready';progress=duration>0?0:1;focus(1);resize();
        // Production enters immediately. Retain the bounded async contract
        // for explicit callers and stalled-frame recovery.
        if(!duration)return Promise.resolve();
        return new Promise(resolve=>{
            completion=resolve;const started=performance.now();
            function frame(now){
                if(disposed||phase!=='intro')return;
                const elapsed=now-started,t=clamp(elapsed/duration);
                pose(t);
                if(elapsed>=duration){phase='ready';render();stop();}else requestFrame(frame);
            }
            requestFrame(frame);
        });
    }
    function resetBall() {
        ball.visible=true;
        ball.position.copy(ballHome);ball.rotation.set(.1,.25,.3);
        keeper.position.set(goalX-.4,.92,0);keeper.rotation.set(0,0,0);keeperRig.poseHands();world.rippleNet(0);
        lastOutcome=null;lastPlan=null;caught=false;
        shooter.position.set(spotX-2.0,.92,1.35);strikerRig.kick(0);
    }
    function reset() {
        // Re-rendering server state must not interrupt a pending presentation.
        if(phase==='shot'){stop();phase='ready';}
        resetBall();render();
    }
    function shot(outcome,animated=true,plan=globalThis.PenaltyShots.plan(outcome),onCue=()=>{}) {
        if(!['goal','save','miss','replay'].includes(outcome)||disposed)return;
        skip();stop();resetBall();lastOutcome=outcome;lastPlan=plan;
        if(outcome==='replay'){render();return Promise.resolve();}
        phase='shot'; const start=performance.now();
        // Convert the short real-time result pause into simulation time.
        // Both roles use the same clock, including takeoff and landing.
        const runUp=C.runUpMs,totalMs=C.shotMs+runUp+C.resultHoldMs*C.betweenShotSpeed;
        // Both roles share the same world-space shot targets and camera.
        const targetZ=plan.target.side*(C.goal.width/2-C.shot.postInset);
        const targetY=plan.target.high?C.goal.height-C.shot.crossbarInset:ballHome.y;
        const keeperZ=plan.keeper.side*(C.goal.width/2-C.shot.postInset);
        const keeperY=plan.keeper.high?C.goal.height-C.shot.crossbarInset:ballHome.y;
        const hands=v(goalX-C.shot.catchX,keeperY,keeperZ);
        const end=v(outcome==='save'?hands.x:goalX,targetY,outcome==='miss'?(targetZ||4.5)*1.6:targetZ);
        const gravity=C.shot.gravity,flightSeconds=C.shot.flightSeconds,takeoff=.04;
        const contactTime=flightSeconds-takeoff;
        const contactY=plan.keeper.high?1.5:.70;
        // Pocatecni rychlost je odvozena z vysky pri kontaktu. Po vrcholu
        // paraboly gravitace automaticky vrati brankare na travnik.
        const jumpVelocity=(contactY-.92+.5*gravity*contactTime**2)/contactTime;
        const lateral=keeperZ*.57,roll=Math.sign(keeperZ)*1.52;
        const landingHeight=.92*Math.cos(Math.abs(roll))+C.keeperHalfWidth*Math.sin(Math.abs(roll));
        const landingTime=(jumpVelocity+Math.sqrt(jumpVelocity**2+2*gravity*(.92-landingHeight)))/gravity;
        function keeperPose(seconds) {
            const airborne=Math.max(0,seconds-takeoff),dive=clamp(airborne/contactTime);
            const angle=roll*smooth(dive);
            // Obalka tela pri otoceni: boty, bok ani hlava neprojdou pod zem.
            const floor=.92*Math.cos(Math.abs(angle))+C.keeperHalfWidth*Math.sin(Math.abs(angle));
            // After contact the keeper lands and slides to a stop, instead of
            // continuing sideways until his whole body crosses the goalpost.
            const travel=Math.min(airborne,landingTime)/contactTime;
            const lateralTravel=travel<=1?travel:1+.25*(1-Math.exp(-2*(travel-1)));
            return {position:v(goalX-.4-.12*travel,Math.max(floor,ballistic(.92,jumpVelocity,airborne,gravity)),lateral*lateralTravel),angle};
        }
        const contactRoot=keeperPose(flightSeconds).position;
        let kicked=false,contacted=false,reacted=false,crowdCue=null;
        const cue=name=>{try{onCue(name);}catch{/* Audio failure must never stop the shot. */}};
        function shotPose(t) {
            const elapsed=t*totalMs,approach=runUp?clamp(elapsed/runUp):1;
            const seconds=Math.max(0,(elapsed-runUp)/1000),u=clamp(seconds/flightSeconds),after=Math.max(0,seconds-flightSeconds);
            {
                shooter.position.x=THREE.MathUtils.lerp(spotX-2.0,spotX-.65,smooth(approach));
                shooter.position.z=THREE.MathUtils.lerp(1.35,.40,smooth(approach));
                // Backswing, strike and follow-through; ball only moves after contact.
                strikerRig.kick(approach<.65?Math.sin(approach/.65*Math.PI)*.65:
                  THREE.MathUtils.lerp(.1,-.85,smooth((approach-.65)/.35))*(1-smooth(seconds/.65)));
            }
            const root=keeperPose(seconds),dive=smooth(clamp((seconds-takeoff)/contactTime));
            // After landing, stand back up with the secured ball. Holding a
            // clear two-handed pose makes a save distinct from a goal even
            // without sound; never lift the body while it is still airborne.
            const stand=outcome==='save'?smooth((seconds-takeoff-landingTime-.08)/.48):0;
            root.angle*=1-stand;
            root.position.y=THREE.MathUtils.lerp(root.position.y,.92,stand);
            const bodyFloor=.92*Math.cos(Math.abs(root.angle))+C.keeperHalfWidth*Math.sin(Math.abs(root.angle));
            root.position.y=Math.max(bodyFloor,root.position.y);
            // Balisticky let s presnou koncovou vyskou. Nizka strela se valí.
            ball.position.lerpVectors(ballHome,end,u);
            if(plan.target.high)ball.position.y+=.5*gravity*flightSeconds**2*u*(1-u);
            ball.rotation.z=.3-u*24;ball.rotation.x=.1+u*5;
            keeper.position.copy(root.position);keeper.rotation.x=root.angle;
            // Po chyceni ruce i mic cestuji s telem a skladaji se k hrudi.
            // Stejny cil dostanou obe dlane: mic se pri doskoku neodpoji.
            const handTarget=hands.clone();
            if(after>0) {
                handTarget.add(root.position.clone().sub(contactRoot));
                // Keep a landed save above the grass, forward of the body:
                // two gloves surround the visible ball instead of hiding it.
                handTarget.x=THREE.MathUtils.lerp(handTarget.x,root.position.x-.46,smooth(after/.55));
                handTarget.y=THREE.MathUtils.lerp(handTarget.y,Math.max(ballHome.y+.16,root.position.y+.16+stand*.18),smooth(after/.55));
                handTarget.z=THREE.MathUtils.lerp(handTarget.z,root.position.z+Math.sign(keeperZ)*.15,smooth(after/.55));
            }
            keeperRig.poseHands(handTarget,dive);
            caught=outcome==='save'&&u===1;
            // React to the server outcome only once, at physical contact.
            if(u===1&&!reacted){crowdCue=reactionForShot(outcome,role).moods[0]==='cheer'?'crowd-cheer':'crowd-groan';reacted=true;}
            if(caught){ball.position.copy(keeperRig.handCenter());ball.rotation.set(.1,-.25,.3);}
            else if(after>0) {
                // Sit pohlti doprednou energii; vysoka strela pak spadne
                // a tlumene odskoci. Mimo branu mic pokracuje po parabole.
                const netDelay=.13,fall=after;
                const impactVelocity=outcome==='goal'?-.35:(targetY-ballHome.y)/flightSeconds-.5*gravity*flightSeconds;
                ball.position.x=end.x+(outcome==='goal'?Math.min(after/netDelay,1)*.8:(1-Math.exp(-after*3))*2);
                ball.position.y=plan.target.high?bounceHeight(targetY,impactVelocity,fall,ballHome.y,gravity,C.shot.bounce):ballHome.y;
            }
            world.rippleNet(outcome==='goal'?Math.sin(clamp(after/.30)*Math.PI)*.15:0,targetZ,targetY);
            // Keep contact, landing and the held-ball pose in the same view.
            render();
            // Cross each contact threshold once after rendering that pose,
            // including low-FPS frames. The run-up delays the kick in both roles.
            if(animated&&!kicked&&elapsed>=runUp){kicked=true;cue('kick');}
            if(animated&&!contacted&&u===1){contacted=true;if(outcome==='save')cue('catch');else if(outcome==='goal')cue('net');cue(crowdCue);}
        }
        if(!animated){shotPose(1);cue(outcome==='save'?'catch':outcome==='goal'?'net':'kick');cue(crowdCue);phase='ready';return Promise.resolve();}
        return new Promise(resolve=>{
            completion=resolve;
            // Scale playback, not gravity or individual phases: preserve the
            // complete landing/catch trajectory and fire cues at visual contact.
            function frame(now){const t=clamp((now-start)*C.betweenShotSpeed/totalMs);shotPose(t);if(t<1)requestFrame(frame);else{phase='ready';stop();}}
            requestFrame(frame);
        });
    }
    function finish(duration=C.outroMs,onProgress=()=>{}) {
        stop();phase='outro';const started=performance.now();
        function framePose(t) {
            endingProgress=t;render();onProgress(smooth(t));
        }
        endingPose=framePose;
        if(!duration){framePose(1);phase='finished';return Promise.resolve();}
        return new Promise(resolve=>{
            completion=resolve;
            function frame(now){const t=clamp((now-started)/duration);framePose(t);if(t<1)requestFrame(frame);else{phase='finished';stop();}}
            requestFrame(frame);
        });
    }
    const observer=new ResizeObserver(()=>guard(resize));observer.observe(host);observer.observe(framing);
    on(window,'resize',()=>guard(resize));
    on(renderer.domElement,'webglcontextlost',event=>{event.preventDefault();fail(new Error('WebGL context lost'));});
    function dispose() {
        if(disposed)return;stop();disposed=true;observer.disconnect();abort.abort();
        collectResources();world.dispose();resources.forEach(resource=>resource.dispose());
        renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();
    }
    return {setView,skip,shot,reset,suspend,dispose,finish,
        setOutfits:outfits=>{world.setOutfits(outfits);render();},
        inspect:()=>({role,phase,progress,endingProgress,...world.inspect(),presentation,focus:1,
            camera:camera.position.toArray(),ball:ball.position.toArray(),keeper:keeper.position.toArray(),
            ballScreen:ball.position.clone().project(camera).toArray(),
            ballDiameterPx:world.ballVisualSize()*height*camera.projectionMatrix.elements[5]/(-2*ball.position.clone().applyMatrix4(camera.matrixWorldInverse).z),
            hands:keeperRig.handCenter().toArray(),lastOutcome,lastPlan,caught,keeperVisible:keeper.visible,
            ballVisible:ball.visible,strikerVisible:shooter.visible,
            framing:framingSamples().map(p=>p.project(camera).toArray()),
            viewport,renderSize:[renderer.domElement.width,renderer.domElement.height],pixelRatio:renderer.getPixelRatio(),
            markingsVisible:world.pitch.children.filter(o=>o.name.startsWith('pitch-marking-')).every(o=>o.visible),
            drawCalls:renderer.info.render.calls,renderPasses:1})};
}
