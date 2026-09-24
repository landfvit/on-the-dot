/* Minimal ink-and-paper supporters, instanced by body part, not one draw call
 * per person. Layout/scale/jump height are editable in stadium_config.js.
 * This module never reads game APIs or computes a match score. */
import * as THREE from './vendor/three/three.module.min.js';
import {V6_WORLD as C} from './stadium_config.js?v=12';
import {reactionForShot} from './crowd_reaction.js?v=1';

export function createCrowd(parent, rows) {
  const group=new THREE.Group();group.name='supporters';parent.add(group);
  const fans=[],materials=[];
  // Each half of the bowl belongs to a fixed seat. Leave aisles and the tunnel
  // clear; both halves of the end behind the goal remain in the camera's view.
  for(const row of C.crowd.rows) {
    const points=rows[row];
    for(let j=0;j<points.length-1;j++) {
      const a=new THREE.Vector3(...points[j]),b=new THREE.Vector3(...points[j+1]);
      const count=Math.floor(a.distanceTo(b)/C.crowd.spacing);
      for(let i=0;i<count;i++) {
        const p=a.clone().lerp(b,(i+.5)/count);
        if(Math.abs(p.x)<5.8&&p.z>0)continue;
        fans.push({p,seat:p.z<0?0:1,phase:(fans.length*.618)%1,angle:Math.atan2(-p.x,-p.z)});
      }
    }
  }
  const material=color=>{const m=new THREE.MeshBasicMaterial({color});materials.push(m);return m;};
  const ink=material(C.colors.outline),paper=material(C.colors.bright),shirt=material(0xffffff);
  function instances(name,geometry,mat,multiple=1){
    const mesh=new THREE.InstancedMesh(geometry,mat,fans.length*multiple);
    mesh.name=name;mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    // Supporters' small jumps fit well inside the entire stadium. Avoid
    // recomputing a thousand-instance bounding sphere on every animation frame.
    mesh.frustumCulled=false;group.add(mesh);return mesh;
  }
  const bodies=instances('fan-body-outline',new THREE.CylinderGeometry(.25,.21,.60,8),ink);
  const shirts=instances('fan-shirts',new THREE.CylinderGeometry(.21,.18,.52,8),shirt);
  const heads=instances('fan-head-outline',new THREE.SphereGeometry(.20,6,4),ink);
  const faces=instances('fan-faces',new THREE.SphereGeometry(.164,6,4),paper);
  const eyes=instances('fan-eyes',new THREE.SphereGeometry(.016,4,3),ink,2);
  const mouths=instances('fan-mouths',new THREE.TorusGeometry(.041,.01,3,8,Math.PI),ink);
  const arms=instances('fan-arms',new THREE.CylinderGeometry(.067,.067,1,6),ink,2);
  const hands=instances('fan-hands',new THREE.SphereGeometry(.09,6,5),paper,2);
  const legs=instances('fan-legs',new THREE.CylinderGeometry(.075,.075,1,6),ink,2);
  const scarves=instances('fan-scarves',new THREE.BoxGeometry(.52,.12,.05),shirt);
  fans.forEach((fan,i)=>{
    const colors=C.crowd.shirts[fan.seat];
    shirts.setColorAt(i,new THREE.Color(colors[i%colors.length]));
    scarves.setColorAt(i,new THREE.Color(fan.seat===0?C.colors.bright:C.colors.outline));
  });
  let viewerSeat=0,reaction={winner:null,moods:['neutral','neutral']},reactions=0;
  let labels=['Player 1','Player 2'],lastTime=0,maxLift=0,staticPose=false;
  const transform=new THREE.Object3D(),orientation=new THREE.Quaternion(),axis=new THREE.Vector3(0,1,0);
  const pos=new THREE.Vector3(),end=new THREE.Vector3(),dir=new THREE.Vector3();
  function place(mesh,i,fan,x,y,z,sx=1,sy=1,sz=1,lean=0,roll=0){
    pos.set(x,y,z).multiplyScalar(C.crowd.scale).applyQuaternion(orientation).add(fan.p);
    transform.position.copy(pos);transform.quaternion.copy(orientation);
    if(lean)transform.rotateX(lean);
    if(roll)transform.rotateZ(roll);
    transform.scale.set(sx,sy,sz).multiplyScalar(C.crowd.scale);transform.updateMatrix();mesh.setMatrixAt(i,transform.matrix);
  }
  function segment(mesh,i,fan,a,b,r=1){
    pos.set(...a);end.set(...b);dir.copy(end).sub(pos);
    transform.position.copy(pos.add(end).multiplyScalar(.5)).multiplyScalar(C.crowd.scale).applyQuaternion(orientation).add(fan.p);
    transform.quaternion.setFromUnitVectors(axis,dir.clone().normalize()).premultiply(orientation);
    transform.scale.set(r,dir.length(),r).multiplyScalar(C.crowd.scale);transform.updateMatrix();mesh.setMatrixAt(i,transform.matrix);
  }
  function update(seconds=0,still=false){
    still=still||!C.crowd.animate;
    if(still&&staticPose)return;
    lastTime=seconds;staticPose=still;maxLift=0;
    // A short eased lift avoids a snap at contact. Reduced motion uses only a
    // static arms-up / head-down pose; no jumping or continuing RAF is needed.
    const ramp=still?1:THREE.MathUtils.smoothstep(seconds,0,.22);
    for(let i=0;i<fans.length;i++){
      const fan=fans[i],mood=reaction.moods[fan.seat],happy=mood==='cheer',sad=mood==='sad';
      const cycle=((seconds/C.crowd.jumpPeriod+fan.phase)%1);
      const lift=happy&&!still?C.crowd.jumpHeight*4*cycle*(1-cycle)*ramp:0;
      maxLift=Math.max(maxLift,lift);orientation.setFromAxisAngle(axis,fan.angle);
      const slump=sad?.18*ramp:0,base=lift-slump;
      place(bodies,i,fan,0,.94+base,slump*.4);
      place(shirts,i,fan,0,.96+base,.09+slump*.4);
      place(scarves,i,fan,0,1.14+base,.31+slump*.4);
      place(heads,i,fan,0,1.45+base,slump*1.3,1,1,1);
      place(faces,i,fan,0,1.45+base,.06+slump*1.3,1,1,1);
      place(mouths,i,fan,0,1.405+base,.219+slump*1.3,1,1,1,0,happy?Math.PI:0);
      for(const s of [-1,1]){
        const n=i*2+(s===1?1:0),wave=happy&&!still?Math.sin(seconds*7+fan.phase*6)*.09*ramp:0;
        const wrist=happy?[s*.50,1.1+base+.77*ramp+wave,0]:sad?[s*.17,.97+base,.29]:[s*.34,.63,0];
        segment(arms,n,fan,[s*.23,1.15+base,0],wrist);
        place(hands,n,fan,...wrist);
        place(eyes,n,fan,s*.052,1.48+base,.22+slump*1.3);
        // Feet leave and return to the same step; the jump never sinks below it.
        segment(legs,n,fan,[s*.12,.69+base,0],[s*.18,lift+.09,.04]);
      }
    }
    for(const mesh of [bodies,shirts,heads,faces,eyes,mouths,arms,hands,legs,scarves])mesh.instanceMatrix.needsUpdate=true;
  }
  // Identity is data only. No banners or usernames are painted onto the stands.
  function configure(context={}){
    viewerSeat=context.viewerSeat===1?1:0;
    const next=context.names||['Player 1','Player 2'];
    labels=next.map((label,i)=>String(label||`Player ${i+1}`).slice(0,32));
  }
  function reset(){reaction={winner:null,moods:['neutral','neutral']};staticPose=false;update(0);}
  function react(outcome,role){reaction=reactionForShot(outcome,role,viewerSeat);if(reaction.winner!==null)reactions++;staticPose=false;update(0);}
  configure();update(0);
  return {group,configure,reset,react,update,
    inspect:()=>({count:fans.length,teamCounts:[0,1].map(s=>fans.filter(f=>f.seat===s).length),viewerSeat,labels:[...labels],winner:reaction.winner,moods:[...reaction.moods],reactions,time:lastTime,maxLift,staticPose,drawCalls:group.children.length}),
    dispose:()=>{group.traverse(o=>o.geometry?.dispose());materials.forEach(m=>m.dispose());}
  };
}
