/* Three.js scena odvozena z dodaneho stadion_penalty_v6.html.
 * Zamerne neobsahuje fetch, WebSocket, pravidla hry ani vyber spravne odpovedi.
 * Aplikace ji posila pouze roli a jiz rozhodnuty vysledek: goal/save/miss/replay.
 * Vzhled men v stadium_config.js; rozlozeni HTML prekryvu v stadium.css.
 */
import * as THREE from './vendor/three/three.module.min.js';
import {STADIUM as C} from './stadium_config.js?v=11';
import {createStadiumWorld} from './stadium_v6_world.js?v=10';
import {ballistic,bounceHeight} from './stadium_motion.js';

export function createStadium(host, framing, onFailure, onReveal = () => {}) {
    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(C.camera.entryFov, 1, 0.07, 600);
    const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, C.maxPixelRatio));
    renderer.domElement.setAttribute('aria-label', 'Penalty stadium');
    host.append(renderer.domElement);
    const v = (x, y, z) => new THREE.Vector3(x, y, z);
    const clamp = x => Math.max(0, Math.min(1, x));
    const smooth = x => { x = clamp(x); return x*x*(3-2*x); };
    const goalX = C.pitch.length / 2, spotX = goalX - C.penalty.distance;
    const ballHome = v(spotX, C.penalty.ballRadius + 0.025, 0);
    const resources = new Set();
    let role = 'shooter', phase = 'idle', disposed = false, raf = 0, progress = 1;
    let completion = null, path = null, startEye = null, startAim = null,startQuaternion=null,startFov=66,startOffset={x:0,y:0};
    let pathLength=1,approachDistance=0;
    let endingPose=null,endingProgress=0,focusAmount=0,blurReady=false;
    let width = 1, height = 1, lastOutcome = null, lastPlan = null, caught = false;
    const abort = new AbortController();
    const on = (element, name, fn) => element.addEventListener(name, fn, {signal: abort.signal});

    // Cela geometrie (tunel, hriste, sit, mic i obleceny brankar) je z v6.
    const world=createStadiumWorld(scene);
    const {ball,keeperRig,strikerRig}=world,shooter=strikerRig.group,keeper=keeperRig.group;
    shooter.position.set(spotX-1.25,.92,0);
    // Only the stadium background is downsampled/blurred; players, ball and goal
    // remain crisp. The same camera renders both layers, including during travel.
    world.background.traverse(o=>o.layers.set(1));camera.layers.enable(1);
    const backgroundMaterials=new Map();
    world.background.traverse(o=>{for(const material of [].concat(o.material||[]))backgroundMaterials.set(material,material.colorWrite);});
    // Rasterize at the same resolution as the sharp view, then downsample with
    // mipmaps. Drawing thin seat lines directly at 1/6 size made them six times
    // thicker and brightened the stands as soon as the blur layer appeared.
    const backdrop=new THREE.WebGLRenderTarget(1,1,{samples:4,generateMipmaps:true,minFilter:THREE.LinearMipmapLinearFilter});
    const softBackdrop=new THREE.WebGLRenderTarget(1,1),blurScene=new THREE.Scene();
    const blurCamera=new THREE.OrthographicCamera(-1,1,1,-1,0,1);
    const blurMaterial=new THREE.ShaderMaterial({transparent:true,depthTest:false,depthWrite:false,
      uniforms:{map:{value:backdrop.texture},sharpMap:{value:backdrop.texture},step:{value:new THREE.Vector2()},opacity:{value:0},resolveAlpha:{value:1}},
      vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}',
      fragmentShader:`uniform sampler2D map;uniform sampler2D sharpMap;uniform vec2 step;uniform float opacity;uniform float resolveAlpha;varying vec2 vUv;
        void main(){vec4 c=vec4(0.);float total=0.;
          for(int i=-8;i<=8;i++){
            float weight=exp(-float(i*i)/18.);
            c+=texture2D(map,clamp(vUv+float(i)*step,vec2(0.),vec2(1.)))*weight;total+=weight;
          }
          c/=total;
          // Offscreen pixels are premultiplied. Filter RGB and alpha together,
          // then unpremultiply only for the final normal-blended screen pass.
          if(resolveAlpha>0.5){
            c=mix(texture2D(sharpMap,vUv),c,opacity);
            gl_FragColor=vec4(c.rgb/max(c.a,0.00001),c.a);
          }else gl_FragColor=c;
          #include <colorspace_fragment>
        }`});
    // Render-target textures must be shared by reference, never cloned.
    const horizontalBlur=new THREE.ShaderMaterial({depthTest:false,depthWrite:false,
      vertexShader:blurMaterial.vertexShader,fragmentShader:blurMaterial.fragmentShader,
      uniforms:{map:{value:backdrop.texture},sharpMap:{value:backdrop.texture},
        step:{value:new THREE.Vector2()},opacity:{value:1},resolveAlpha:{value:0}}});
    const blurQuad=new THREE.Mesh(new THREE.PlaneGeometry(2,2),blurMaterial);blurScene.add(blurQuad);
    // Focus now controls only optical blur and the UI reveal. Do not call the
    // legacy world.setFocus fade: stands, turf, colors and depth stay unchanged.
    function focus(amount) { focusAmount=clamp(amount);onReveal(focusAmount); }
    function travel(t) {
        const a=.13,b=.60,total=a/2+b-a+(1-b)/2;
        if(t<a)return t*t/(2*a)/total;
        if(t<b)return (a/2+t-a)/total;
        const q=t-b;return (a/2+b-a+q-q*q/(2*(1-b)))/total;
    }

    function finalView() {
        return role==='keeper'
            ? {eye:v(goalX+C.camera.keeperBehindLine,C.camera.keeperHeight,C.camera.keeperSide),aim:v(goalX-4,.8,0)}
            : {eye:v(spotX-C.camera.behindBall,C.camera.height,0),aim:v(goalX,.92,0)};
    }
    function render() {
        if(disposed)return;world.shadows();
        const fade=focusAmount;
        // Warm both shaders and render targets before the camera starts moving,
        // not on the first visible blur frame (which otherwise stalls briefly).
        const prepareBlur=fade>0||!blurReady;
        renderer.autoClear=false;
        if(prepareBlur){
            camera.layers.set(1);renderer.setClearColor(0x000000,0);
            renderer.setRenderTarget(backdrop);renderer.clear();renderer.render(scene,camera);
            // Separable Gaussian blur avoids the repeated seat-line ghosts
            // produced by widely spaced samples in a single 2D kernel.
            horizontalBlur.uniforms.map.value=backdrop.texture;
            horizontalBlur.uniforms.step.value.set(fade*C.backgroundBlur.radius/softBackdrop.width,0);
            blurQuad.material=horizontalBlur;
            renderer.setRenderTarget(softBackdrop);renderer.clear();renderer.render(blurScene,blurCamera);
        }
        renderer.setRenderTarget(null);renderer.setClearColor(0x091316,0);renderer.clear();
        // Keep the original background depth, but composite its color only
        // once. Overlaying blur onto the raw stands doubles translucent edges
        // and leaves sharp seat lines visible through the blurred silhouette.
        camera.layers.set(1);
        if(prepareBlur)for(const material of backgroundMaterials.keys())material.colorWrite=false;
        renderer.render(scene,camera);
        if(prepareBlur)for(const [material,colorWrite] of backgroundMaterials)material.colorWrite=colorWrite;
        if(prepareBlur){
            blurMaterial.uniforms.map.value=softBackdrop.texture;
            blurMaterial.uniforms.step.value.set(0,fade*C.backgroundBlur.radius/softBackdrop.height);
            blurMaterial.uniforms.opacity.value=fade;blurQuad.material=blurMaterial;renderer.render(blurScene,blurCamera);
        }
        camera.layers.set(0);renderer.render(scene,camera);camera.layers.enable(1);
        blurReady=true;
    }
    // Objektiv/vyrez se prizpusobi volnemu obdelniku mimo otazky. Na mobilu
    // kamera neutika od mice; zmeni se FOV a opticky posun celeho obrazu.
    function framingView() {
        const {eye,aim}=finalView(), rect=framing.getBoundingClientRect(),origin=host.getBoundingClientRect();
        camera.position.copy(eye); camera.lookAt(aim); camera.updateMatrixWorld(true);
        const samples = role==='keeper'
            ? [v(goalX,0,-C.goal.width/2-.7),v(goalX,C.goal.height+.4,-C.goal.width/2-.7),
                v(goalX,0,C.goal.width/2+.7),v(goalX,C.goal.height+.4,C.goal.width/2+.7),
                v(spotX-2.5,0,-.6),v(spotX-2.5,2.3,.6)]
            : [v(goalX,0,-C.goal.width/2-.45),v(goalX,C.goal.height+.6,C.goal.width/2+.45),v(spotX-.5,0,-.5),v(spotX-.5,0,.5)];
        const ps=samples.map(p=>p.applyMatrix4(camera.matrixWorldInverse));
        const xs=ps.map(p=>p.x/-p.z), ys=ps.map(p=>p.y/-p.z);
        const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
        const focal=Math.max(45,Math.min(Math.max(rect.width,70)*C.camera.framingPadding/(maxX-minX),Math.max(rect.height,90)*C.camera.framingPadding/(maxY-minY)));
        return {fov:THREE.MathUtils.radToDeg(2*Math.atan(height/(2*focal))),
            x:width/2+focal*(minX+maxX)/2-(rect.left-origin.left+rect.width/2),
            y:height/2-focal*(minY+maxY)/2-(rect.top-origin.top+rect.height/2)};
    }
    function pose(t) {
        progress=t;
        const view=framingView(),targetQuaternion=camera.quaternion.clone(), {eye,aim}=finalView();
        let settle=smooth(t);
        if (path && t<1) {
            const u=travel(t); path.getPoint(u,camera.position);
            const ahead=path.getPoint(Math.min(1,u+1.2/pathLength));
            const direction=ahead.sub(camera.position).normalize();
            settle=smooth((u*pathLength-approachDistance)/(pathLength-approachDistance));
            direction.lerp(aim.clone().sub(eye).normalize(),settle).normalize();
            camera.lookAt(camera.position.clone().add(direction));
        } else if (startEye && t<1) {
            camera.position.lerpVectors(startEye,eye,smooth(t));
            camera.position.z+=Math.sin(Math.PI*smooth(t))*3.5;
            camera.quaternion.copy(startQuaternion).slerp(targetQuaternion,smooth(t));
        } else { camera.position.copy(eye); camera.lookAt(aim); }
        camera.fov=THREE.MathUtils.lerp(path?(width<height?76:C.camera.entryFov):startFov,view.fov,settle);
        camera.setViewOffset(width,height,THREE.MathUtils.lerp(path?0:startOffset.x,view.x,settle),THREE.MathUtils.lerp(path?0:startOffset.y,view.y,settle),width,height);
        camera.updateProjectionMatrix(); render();
    }
    function resize() {
        if(disposed)return;
        width=Math.max(1,host.clientWidth); height=Math.max(1,host.clientHeight);
        renderer.setSize(width,height); camera.aspect=width/height;
        const bufferSize=renderer.getDrawingBufferSize(new THREE.Vector2());
        backdrop.setSize(bufferSize.x,bufferSize.y);
        softBackdrop.setSize(Math.max(1,Math.round(width/C.backgroundBlur.downsample)),Math.max(1,Math.round(height/C.backgroundBlur.downsample)));
        blurReady=false;
        if(['outro','finished'].includes(phase)&&endingPose)endingPose(endingProgress);else pose(progress);
    }
    function stop() {
        cancelAnimationFrame(raf); raf=0;
        if(completion){const done=completion; completion=null; done();}
    }
    function skip() {
        if(phase==='intro'){stop();phase='ready';focus(1);pose(1);}
        if(phase==='outro'){endingPose?.(1);phase='finished';stop();}
    }
    // Odchod ze stadionu zastavi i probihajici strelu. Zadny RAF nesmi dal
    // vykreslovat skryty canvas; dalsi enter() znovu nastavi celou kameru.
    function suspend() { stop();phase='idle'; }
    function setView(nextRole,{intro=false,duration=0}={}) {
        camera.up.set(0,1,0);
        startQuaternion=camera.quaternion.clone();startFov=camera.fov;
        startOffset={x:camera.view?.offsetX||0,y:camera.view?.offsetY||0};
        stop(); resetBall(); role=nextRole==='keeper'?'keeper':'shooter';
        focus(intro&&duration>0?0:1);
        shooter.visible=role==='keeper'; keeper.visible=true;
        renderer.domElement.setAttribute('aria-label',role==='keeper'?'Side view of the goalkeeper and penalty taker':'Penalty taker view facing the goal');
        const oldEye=camera.position.clone(), oldAim=oldEye.clone().add(camera.getWorldDirection(v(0,0,0)).multiplyScalar(10));
        const {eye}=finalView(); path=null;startEye=oldEye;startAim=oldAim;
        if(intro){
            // Presna mekka zatacka v6: nejdriv rovne ke stredu, pak ctvrtobrat.
            const turnZ=12,pathHeight=C.camera.height;
  class SoftQuarterTurn extends THREE.Curve {
    getPoint(t, target = new THREE.Vector3()) {
      const u = 1-t;
      // Kvintická Bézierova křivka; první/poslední tři body jsou kolineární.
      const k = 0.34;
      const weights = [u**5, 5*u**4*t, 10*u**3*t*t,
                       10*u*u*t**3, 5*u*t**4, t**5];
      const xs = [0,0,0,(1-2*k)*turnZ,(1-k)*turnZ,turnZ];
      const zs = [turnZ,(1-k)*turnZ,(1-2*k)*turnZ,0,0,0];
      let x=0,z=0;
      for(let i=0;i<6;i++) { x += weights[i]*xs[i]; z += weights[i]*zs[i]; }
      return target.set(x,pathHeight,z);
    }
  }

            path=new THREE.CurvePath();
            path.add(new THREE.LineCurve3(v(0,pathHeight,74),v(0,pathHeight,turnZ)));
            path.add(new SoftQuarterTurn());
            if(role==='keeper'){
                // Kamera obleti branu: cele telo brankare zustane pred objektivem.
                path.add(new THREE.CubicBezierCurve3(v(turnZ,pathHeight,0),v(35,pathHeight,0),v(goalX-5,pathHeight,7),eye));
            } else path.add(new THREE.LineCurve3(v(turnZ,pathHeight,0),eye));
            path.curves.forEach(curve=>{curve.arcLengthDivisions=600;});
            pathLength=path.getLength();approachDistance=path.curves[0].getLength()+path.curves[1].getLength();
        }
        phase=duration>0?'intro':'ready';progress=duration>0?0:1;resize();
        if(!duration)return Promise.resolve();
        // Skutecny uplynuly cas: po navratu z uspane zalozky se intro nedohani
        // na ukor serveroveho casu. Serverove otevreni otazky ma vzdy prednost.
        return new Promise(resolve=>{
            completion=resolve; const started=performance.now();
            const focusMs=intro?Math.min(C.focusMs,duration*.2):0,travelMs=duration-focusMs;
            function frame(now){
                if(disposed||phase!=='intro')return;
                const elapsed=now-started,t=clamp(elapsed/travelMs);
                if(focusMs)focus(smooth((elapsed-travelMs)/focusMs));
                pose(t);
                if(elapsed>=duration){phase='ready';render();stop();}else raf=requestAnimationFrame(frame);
            }
            raf=requestAnimationFrame(frame);
        });
    }
    function resetBall() {
        ball.visible=true;
        ball.position.copy(ballHome);ball.rotation.set(.1,.25,.3);
        keeper.position.set(goalX-.4,.92,0);keeper.rotation.set(0,0,0);keeperRig.poseHands();world.rippleNet(0);
        lastOutcome=null;lastPlan=null;caught=false;
        shooter.position.set(spotX-2.0,.92,0);strikerRig.kick(0);
    }
    function reset() {
        // Render stejnej verze serveru nesmi prerusit kamerovy prijezd.
        if(phase==='shot'){stop();phase='ready';}
        resetBall();render();
    }
    function shot(outcome,animated=true,plan=globalThis.PenaltyShots.plan(outcome),onCue=()=>{}) {
        if(!['goal','save','miss','replay'].includes(outcome)||disposed)return;
        skip();stop();resetBall();lastOutcome=outcome;lastPlan=plan;
        if(outcome==='replay'){render();return Promise.resolve();}
        phase='shot'; const start=performance.now();
        const runUp=role==='keeper'?C.runUpMs:0,totalMs=C.shotMs+runUp+(role==='keeper'?C.keeperHoldMs:0);
        // +Z je prava strana obrazovky strelce (+X pohled), u brankare naopak.
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
        const landingHeight=.92*Math.cos(Math.abs(roll))+.43*Math.sin(Math.abs(roll));
        const landingTime=(jumpVelocity+Math.sqrt(jumpVelocity**2+2*gravity*(.92-landingHeight)))/gravity;
        function keeperPose(seconds) {
            const airborne=Math.max(0,seconds-takeoff),dive=clamp(airborne/contactTime);
            const angle=roll*smooth(dive);
            // Obalka tela pri otoceni: boty, bok ani hlava neprojdou pod zem.
            const floor=.92*Math.cos(Math.abs(angle))+.43*Math.sin(Math.abs(angle));
            // After contact the keeper lands and slides to a stop, instead of
            // continuing sideways until his whole body crosses the goalpost.
            const travel=Math.min(airborne,landingTime)/contactTime;
            const lateralTravel=travel<=1?travel:1+.25*(1-Math.exp(-2*(travel-1)));
            return {position:v(goalX-.4-.12*travel,Math.max(floor,ballistic(.92,jumpVelocity,airborne,gravity)),lateral*lateralTravel),angle};
        }
        const contactRoot=keeperPose(flightSeconds).position;
        let kicked=false,contacted=false;
        const cue=name=>{try{onCue(name);}catch{/* Audio failure must never stop the shot. */}};
        function shotPose(t) {
            const elapsed=t*totalMs,approach=runUp?clamp(elapsed/runUp):1;
            const seconds=Math.max(0,(elapsed-runUp)/1000),u=clamp(seconds/flightSeconds),after=Math.max(0,seconds-flightSeconds);
            if(role==='keeper'){
                shooter.position.x=THREE.MathUtils.lerp(spotX-2.0,spotX-.65,smooth(approach));
                // Backswing, strike and follow-through; ball only moves after contact.
                strikerRig.kick(approach<.65?Math.sin(approach/.65*Math.PI)*.65:
                  THREE.MathUtils.lerp(.1,-.85,smooth((approach-.65)/.35))*(1-smooth(seconds/.65)));
            }
            const root=keeperPose(seconds),dive=smooth(clamp((seconds-takeoff)/contactTime));
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
                handTarget.y=THREE.MathUtils.lerp(handTarget.y,root.position.y+.12,smooth(after/.55));
                handTarget.z=THREE.MathUtils.lerp(handTarget.z,root.position.z+Math.sign(keeperZ)*.15,smooth(after/.55));
            }
            keeperRig.poseHands(handTarget,dive);
            caught=outcome==='save'&&u===1;
            if(caught)ball.position.copy(keeperRig.handCenter());
            else if(after>0) {
                // Sit pohlti doprednou energii; vysoka strela pak spadne
                // a tlumene odskoci. Mimo branu mic pokracuje po parabole.
                const netDelay=.13,fall=after;
                const impactVelocity=outcome==='goal'?-.35:(targetY-ballHome.y)/flightSeconds-.5*gravity*flightSeconds;
                ball.position.x=end.x+(outcome==='goal'?Math.min(after/netDelay,1)*.8:(1-Math.exp(-after*3))*2);
                ball.position.y=plan.target.high?bounceHeight(targetY,impactVelocity,fall,ballHome.y,gravity,C.shot.bounce):ballHome.y;
            }
            world.rippleNet(outcome==='goal'?Math.sin(clamp(after/.30)*Math.PI)*.35:0,targetZ,targetY);
            // Stable third-person camera: the actual keeper, gloves and ball
            // stay visible through contact and landing. No duplicate POV ball.
            render();
            // Cross each contact threshold once after rendering that pose,
            // including low-FPS frames. Keeper run-up delays the kick.
            if(animated&&!kicked&&elapsed>=runUp){kicked=true;cue('kick');}
            if(animated&&!contacted&&u===1){contacted=true;if(outcome==='save')cue('catch');else if(outcome==='goal')cue('net');}
        }
        if(!animated){shotPose(1);cue(outcome==='save'?'catch':outcome==='goal'?'net':'kick');phase='ready';return Promise.resolve();}
        return new Promise(resolve=>{
            completion=resolve;
            function frame(now){const t=clamp((now-start)/totalMs);shotPose(t);if(t<1)raf=requestAnimationFrame(frame);else{phase='ready';stop();}}
            raf=requestAnimationFrame(frame);
        });
    }
    function finish(duration=C.outroMs,onProgress=()=>{}) {
        stop();phase='outro';
        const from=camera.position.clone(),aim=from.clone().add(camera.getWorldDirection(v()).multiplyScalar(12));
        const oldFov=camera.fov,offset={x:camera.view?.offsetX||0,y:camera.view?.offsetY||0};
        const altitude=Math.max(150,130/camera.aspect);
        const flight=new THREE.CubicBezierCurve3(from,v(32,12,0),v(0,70,0),v(0,altitude,0));
        const started=performance.now();
        function framePose(t){
            endingProgress=t;
            // Reach the overhead view before fading the whole HTML stage.
            // The wrapper shares this reveal value with the results card.
            const travel=smooth(clamp(t/.72)),reveal=smooth(clamp((t-.76)/.24));
            focusAmount=1-smooth(clamp(t/.22));
            camera.position.copy(flight.getPoint(travel));
            camera.up.set(0,1-travel,-travel).normalize();camera.lookAt(aim.clone().lerp(v(0,0,0),travel));
            camera.fov=THREE.MathUtils.lerp(oldFov,66,travel);
            camera.setViewOffset(width,height,offset.x*(1-travel),offset.y*(1-travel),width,height);
            camera.updateProjectionMatrix();
            render();onProgress(reveal);
        }
        endingPose=framePose;
        if(!duration){framePose(1);phase='finished';return Promise.resolve();}
        return new Promise(resolve=>{
            completion=resolve;
            function frame(now){const t=clamp((now-started)/duration);framePose(t);if(t<1)raf=requestAnimationFrame(frame);else{phase='finished';stop();}}
            raf=requestAnimationFrame(frame);
        });
    }
    const observer=new ResizeObserver(resize);observer.observe(host);observer.observe(framing);
    on(window,'resize',resize);
    on(renderer.domElement,'webglcontextlost',event=>{event.preventDefault();stop();onFailure();});
    function dispose(){
        if(disposed)return;stop();disposed=true;observer.disconnect();abort.abort();
        scene.traverse(object=>{if(object.geometry)resources.add(object.geometry);for(const m of [].concat(object.material||[]))resources.add(m);});
        world.dispose();resources.forEach(resource=>resource.dispose());
        backdrop.dispose();softBackdrop.dispose();blurQuad.geometry.dispose();blurMaterial.dispose();horizontalBlur.dispose();
        renderer.dispose();renderer.domElement.remove();
    }
    return {setView,skip,shot,reset,suspend,dispose,finish,
        inspect:()=>({role,phase,progress,endingProgress,...world.inspect(),focus:focusAmount,geometryFocus:world.inspect().focus,camera:camera.position.toArray(),ball:ball.position.toArray(),keeper:keeper.position.toArray(),hands:keeperRig.handCenter().toArray(),lastOutcome,lastPlan,caught,keeperVisible:keeper.visible,ballVisible:ball.visible,
            markingsVisible:world.pitch.children.filter(o=>o.name.startsWith('pitch-marking-')).every(o=>o.visible&&o.layers.mask===1),drawCalls:renderer.info.render.calls})};
}
