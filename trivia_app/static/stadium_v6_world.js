/* Art-directed pixel scene. Keep the existing module/API names for recovery.
 * Pixel sprite patterns below are editable: "." is transparent; palette keys
 * map to colors in stadium_config.js. No bitmap downloads or lighting pass.
 */
import * as THREE from './vendor/three/three.module.min.js';
import {V6_WORLD as C} from './stadium_config.js?v=28';
import {kitPixels} from './kit_pixels.js?v=4';

export function createStadiumWorld(scene) {
  const v=(x=0,y=0,z=0)=>new THREE.Vector3(x,y,z);
  const clamp=x=>Math.max(0,Math.min(1,x)),lerp=THREE.MathUtils.lerp;
  const surface=color=>new THREE.MeshBasicMaterial({color});
  const pitch=new THREE.Group(),goal=new THREE.Group();
  pitch.name='penalty-area';goal.name='goal';scene.add(pitch,goal);
  const gx=C.penalty.goalX,spotX=C.penalty.spotX;
  const paint=surface(C.colors.markings);paint.side=THREE.DoubleSide;
  function plane(parent,color,x,z,w,d,y=C.ground.turfY,name='') {
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(w,d),surface(color));
    mesh.rotation.x=-Math.PI/2;mesh.position.set(x,y,z);mesh.name=name;parent.add(mesh);return mesh;
  }
  // Grass continues off every foreground/side edge. Only the far end is
  // visible, behind the goal. The framing rectangle is never a turf island.
  const back=gx+C.ground.behindGoal;
  plane(pitch,C.colors.pitch,back-80,0,160,240,C.ground.turfY,'penalty-turf');
  const stripes=[];
  for(let z=-120;z<120;z+=4)if(Math.round(z/4)%2===0) {
    const x0=back-160,x1=back,z0=z,z1=z+4,y=C.ground.turfY+.001;
    stripes.push(x0,y,z0,x1,y,z0,x0,y,z1,x0,y,z1,x1,y,z0,x1,y,z1);
  }
  const stripeGeometry=new THREE.BufferGeometry();
  stripeGeometry.setAttribute('position',new THREE.Float32BufferAttribute(stripes,3));
  const stripeMat=surface(C.colors.pitchStripe);stripeMat.side=THREE.DoubleSide;
  const stripeMesh=new THREE.Mesh(stripeGeometry,stripeMat);stripeMesh.name='mowing-bands';pitch.add(stripeMesh);
  const markings=[];
  function paintedLine(points,name) {
    const vertices=[],half=C.pitchMarkings.width/2,y=C.pitchMarkings.elevation;
    for(let i=1;i<points.length;i++){
      const [ax,az]=points[i-1],[bx,bz]=points[i],length=Math.hypot(bx-ax,bz-az);
      const dx=-(bz-az)/length*half,dz=(bx-ax)/length*half;
      vertices.push(ax+dx,y,az+dz,bx+dx,y,bz+dz,ax-dx,y,az-dz,
        ax-dx,y,az-dz,bx+dx,y,bz+dz,bx-dx,y,bz-dz);
    }
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
    const mesh=new THREE.Mesh(geometry,paint);mesh.name=name;pitch.add(mesh);
    markings.push({points,geometry});
  }
  paintedLine([[gx,-120],[gx,120]],'pitch-marking-goal-line');
  for(const [name,half,depth] of [['penalty-area',C.area.halfWidth,C.area.depth],['goal-area',C.area.smallHalfWidth,C.area.smallDepth]]) {
    paintedLine([[gx,-half],[gx-depth,-half],[gx-depth,half],[gx,half]],'pitch-marking-'+name);
  }
  const arcLimit=Math.acos((C.area.depth-11)/C.area.arcRadius);
  const arc=Array.from({length:41},(_,i)=>{
    const a=lerp(-arcLimit,arcLimit,i/40);
    return [spotX-C.area.arcRadius*Math.cos(a),C.area.arcRadius*Math.sin(a)];
  });
  paintedLine(arc,'pitch-marking-penalty-arc');
  // A single filled circle, on the ground under the ball. No line or cross.
  const spot=new THREE.Mesh(new THREE.CircleGeometry(.18,12),paint);
  spot.rotation.x=-Math.PI/2;spot.position.set(spotX,.015,0);spot.name='penalty-spot';pitch.add(spot);

  const unitBox=new THREE.BoxGeometry(1,1,1),outlinedBars=[];
  function bar(parent,a,b,width,color,outline=0) {
    const start=v(...a),end=v(...b),delta=end.clone().sub(start),length=delta.length();
    const mesh=new THREE.Mesh(unitBox,surface(color));
    mesh.position.copy(start).add(end).multiplyScalar(.5);
    mesh.quaternion.setFromUnitVectors(v(0,1,0),delta.normalize());
    mesh.scale.set(width,length+width,width);parent.add(mesh);
    if(outline){
      const edge=new THREE.Mesh(unitBox,new THREE.MeshBasicMaterial({color:C.colors.outline,side:THREE.BackSide}));
      edge.position.copy(mesh.position);edge.quaternion.copy(mesh.quaternion);
      edge.scale.set(width+outline*2,length+width+outline*2,width+outline*2);
      parent.add(edge);
      outlinedBars.push({mesh,edge,length,width,outline});
    }
    return mesh;
  }
  const gz=3.66,gb=gx+1.8;
  const front=new THREE.Group();front.name='goal-frame-continuous';goal.add(front);
  const thick=C.structure.postRadius*2,border=C.structure.goalOutline;
  bar(front,[gx,0,-gz],[gx,2.44,-gz],thick,C.colors.goal,border);
  bar(front,[gx,2.44,-gz],[gx,2.44,gz],thick,C.colors.goal,border);
  bar(front,[gx,0,gz],[gx,2.44,gz],thick,C.colors.goal,border);
  for(const s of [-1,1]){
    bar(goal,[gb,0,s*gz],[gb,2.2,s*gz],.075,C.colors.netShade);
    bar(goal,[gx,2.44,s*gz],[gb,2.2,s*gz],.075,C.colors.goal);
    bar(goal,[gx,0,s*gz],[gb,0,s*gz],.075,C.colors.goal);
  }
  bar(goal,[gb,2.2,-gz],[gb,2.2,gz],.075,C.colors.netShade);
  const netPoints=[],segment=(a,b)=>netPoints.push(...a,...b);
  for(let i=0;i<=10;i++){
    const z=lerp(-gz,gz,i/10);
    for(let j=0;j<4;j++)segment([gb,2.2*j/4,z],[gb,2.2*(j+1)/4,z]);
    segment([gx,2.44,z],[gb,2.2,z]);
  }
  for(let j=0;j<=4;j++){
    const y=2.2*j/4;
    for(let i=0;i<10;i++)segment([gb,y,lerp(-gz,gz,i/10)],[gb,y,lerp(-gz,gz,(i+1)/10)]);
    for(const s of [-1,1])segment([gx,2.44*j/4,s*gz],[gb,y,s*gz]);
  }
  // A dark offset behind the white mesh makes the net legible on white without
  // turning the goal into a solid colored wall.
  const netGeometry=new THREE.BufferGeometry();
  netGeometry.setAttribute('position',new THREE.Float32BufferAttribute(netPoints,3));
  const netRest=new Float32Array(netPoints);
  const netShadow=new THREE.LineSegments(netGeometry,new THREE.LineBasicMaterial({color:C.colors.netShade}));
  netShadow.position.set(.06,-.08,.06);goal.add(netShadow);
  const net=new THREE.LineSegments(netGeometry,new THREE.LineBasicMaterial({
    color:C.colors.goal,transparent:true,opacity:C.structure.netOpacity,depthWrite:false,
  }));
  net.name='goal-net';net.renderOrder=1;goal.add(net);
  function rippleNet(amount=0,targetZ=0,targetY=.6) {
    const p=netGeometry.attributes.position;
    for(let i=0;i<p.count;i++){
      const j=i*3,x=netRest[j],y=netRest[j+1],z=netRest[j+2],depth=clamp((x-gx)/1.8);
      const pin=Math.sin(Math.PI*clamp(y/lerp(2.44,2.2,depth)))*Math.sin(Math.PI*clamp((z+gz)/(gz*2)));
      p.setXYZ(i,x+amount*Math.exp(-((z-targetZ)**2+(y-targetY)**2)*.8)*depth*pin,y,z);
    }
    p.needsUpdate=true;
  }

  const textures=new Set(),parts=[],figures=[],textureCache=new Map();
  const palette={
    K:C.colors.outline,H:C.colors.hair,h:C.colors.hairLight,
    S:C.colors.skin,L:C.colors.skinLight,s:C.colors.skinShade,
    C:C.colors.shorts,W:0xffffff,w:0xdce3d1,
  };
  // Kit 0 is always the local player; kit 1 is the opponent, in Solo/Daily
  // and on each Duel device. Rigs keep their gloves and anatomy when swapped.
  const kits=[
    {...palette,B:C.colors.strikerShirt,l:C.colors.strikerLight,b:C.colors.strikerShade},
    {...palette,B:C.colors.shirt,l:C.colors.shirtLight,b:C.colors.shirtShade},
  ];
  function texture(rows,colors) {
    // Skin, boots and gloves do not need duplicate GPU maps for each kit.
    const used=Object.fromEntries([...new Set(rows.join(''))].filter(k=>k!=='.').sort().map(k=>[k,colors[k]]));
    const key=rows.join('/')+JSON.stringify(used);if(textureCache.has(key))return textureCache.get(key);
    const w=Math.max(...rows.map(row=>row.length)),h=rows.length,data=new Uint8Array(w*h*4);
    for(let y=0;y<h;y++)for(let x=0;x<w;x++){
      const code=rows[y][x];if(!code||code==='.')continue;
      const hex=colors[code];if(hex===undefined)throw Error('Unknown sprite color '+code);
      const i=((h-1-y)*w+x)*4;data[i]=hex>>16&255;data[i+1]=hex>>8&255;data[i+2]=hex&255;data[i+3]=255;
    }
    const map=new THREE.DataTexture(data,w,h);
    map.magFilter=map.minFilter=THREE.NearestFilter;map.generateMipmaps=false;
    map.colorSpace=THREE.SRGBColorSpace;map.needsUpdate=true;
    textures.add(map);textureCache.set(key,map);return map;
  }
  // A 16px football with broad black panels and quiet grey seams. Four exact
  // quarter-turns keep the silhouette crisp; no smoothing or image downloads.
  // These are cosmetic pixels: the ball still follows the same 3D trajectory.
  const football=[
    '.....KKKKKK.....',
    '...KKWWWWWWKK...',
    '..KWWWKKKKWWWK..',
    '.KWWWWKKKKWWWWK.',
    '.KWWWWWGGWWWWWK.',
    'KWWWWGGWWGGWWWWK',
    'KKWWGWWKKWWGWWKK',
    'KKKWWWKKKKWWWKKK',
    'KKKWWWKKKKWWWKKK',
    'KKWWGWKKKKWGWWKK',
    'KWWWWGGKKGGWWWWK',
    '.KWWGWWGGWWGWWK.',
    '.KWWKKWWWWKKWWK.',
    '..KWKKKGGKKKWK..',
    '...KKSSSSSSKK...',
    '.....KKKKKK.....',
  ];
  const ballFrames=[];let rotated=football;
  for(let turn=0;turn<4;turn++){
    ballFrames.push(texture(rotated,{K:C.colors.ballBlack,W:C.colors.ballWhite,G:0x9aa49a,S:0xd9dfd6}));
    rotated=rotated[0].split('').map((_,x)=>rotated.map(row=>row[x]).reverse().join(''));
  }
  const ball=new THREE.Group();ball.name='pixel-football';scene.add(ball);
  const ballSprite=new THREE.Sprite(new THREE.SpriteMaterial({map:ballFrames[0],alphaTest:.5,depthWrite:false}));
  ballSprite.scale.setScalar(C.penalty.ballRadius*2);ballSprite.renderOrder=9;ballSprite.name='pixel-football-sprite';ball.add(ballSprite);
  function part(parent,rows,colors,width,height,pos,name,order=4) {
    const anchor=new THREE.Group();anchor.position.set(...pos);anchor.name=name;parent.add(anchor);
    const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture(rows,colors),alphaTest:.5,depthWrite:false}));
    sprite.name=name+'-pixels';sprite.scale.set(width,height,1);sprite.renderOrder=order;anchor.add(sprite);
    parts.push({anchor,sprite,width,height,name,kits:kits.map(p=>texture(rows,p))});return anchor;
  }
  function limb(parent,a,b,width,rows,colors,name) {
    const anchor=part(parent,rows,colors,width,1,[0,0,0],name,3);
    setLimb(anchor,a,b);return anchor;
  }
  function setLimb(anchor,a,b) {
    anchor.position.copy(a).add(b).multiplyScalar(.5);
    const delta=b.clone().sub(a);
    anchor.scale.y=delta.length();anchor.quaternion.setFromUnitVectors(v(0,1,0),delta.normalize());
  }
  // Each silhouette uses a small authored sprite, not a pixel filter applied
  // to a rounded 3D mannequin. Limbs are articulated independently.
  const headFront=[
    '...KKKKKK...', '..KhhhhhhK..', '.KHHHhhhhHK.', '.KHHHHHHHHK.',
    '.KSLSSSSLSK.', '.KSLKSSLKSK.', '..KSSLLSSK..', '...KSSSSK...', '....KKKK....',
  ];
  const headBack=[
    '...KKKKKK...', '..KhhhhhhK..', '.KHHHhhhhHK.', '.KHHHHHhhHK.',
    '.KHHHHHHHHK.', '.KSHHHHHHSK.', '..KHHHHHHK..', '...KSSSSK...', '....KKKK....',
  ];
  const torsoFront=[
    '...KKKKKK...', '..KBWSSWBK..', '.KlBBWWBBlK.', 'KlBBBBBBBBbK',
    'KlBBBBBBBBbK', '.KlBBBBBBbK.', '.KlBBBBBBbK.', '.KlBBBBBBbK.',
    '.KBBBBBBBbK.', '.KBBBBBBBBK.', '..KKKKKKKK..',
  ];
  const torsoBack=[
    '...KKKKKK...', '..KBWWWWBK..', '.KlBBBBBBlK.', 'KlBBBBBBBBbK',
    'KlBBBBBBBBbK', '.KlBBBBBBbK.', '.KlBBBBBBbK.', '.KlBBBBBBbK.',
    '.KBBBBBBBbK.', '.KBBBBBBBBK.', '..KKKKKKKK..',
  ];
  const sleeve=['.KKK.','KlBbK','KlBbK','KlBbK','KlBbK','.KKK.'];
  const forearm=['.KK.','KLSK','KLSK','KSSK','.KK.'];
  const thigh=['.KK.','KCCK','KCCK','KLSK','KSSK','.KK.'];
  const sock=['.KKK.','KWWWK','KlBbK','KlBbK','KlBbK','KBBbK','.KKK.'];
  const glove=['.KKKK.','KWWWWK','KWWWwK','KWWWwK','.KwwK.','..KK..'];
  const fist=['.KKK.','KLSSK','KSSsK','.KKK.'];
  const boot=['..KKKK.','.KCCCCK','KCCCCCK','KKKKKKK'];
  const shorts=['KKKKKKKKKK','KCCCCCCCCK','KCCCCCCCCK','KCCCKKCCCK','KKKK..KKKK'];
  function player(isKeeper) {
    const firstPart=parts.length;
    const pivot=new THREE.Group();pivot.name=isKeeper?'goalkeeper':'striker';scene.add(pivot);
    const model=new THREE.Group();model.position.y=-.92;model.rotation.y=-Math.PI/2;pivot.add(model);
    const colors=kits[isKeeper?1:0];
    const torso=part(model,isKeeper?torsoFront:torsoBack,colors,.80,.72,[0,1.27,0],'pixel-shirt');
    const head=part(model,isKeeper?headFront:headBack,colors,.53,.49,[0,1.85,0],'pixel-head',7);
    const figure={model,isKeeper,kit:isKeeper?1:0,torso:torso.children[0],head:head.children[0],
      front:kits.map(p=>[texture(torsoFront,p),texture(headFront,p)]),
      back:kits.map(p=>[texture(torsoBack,p),texture(headBack,p)])};
    figures.push(figure);
    figure.defaults={front:figure.front,back:figure.back};
    part(model,shorts,colors,.58,.27,[0,.88,.01],'pixel-shorts',5);
    let kickingLeg;
    for(const s of [-1,1]){
      const hip=v(s*.17,.86,0),knee=v(s*.25,.51,.015),ankle=v(s*.30,.13,.035);
      const leg=new THREE.Group();leg.position.copy(hip);model.add(leg);
      limb(leg,v(),knee.clone().sub(hip),.21,thigh,colors,'pixel-thigh');
      limb(leg,knee.clone().sub(hip),ankle.clone().sub(hip),.24,sock,colors,'pixel-sock');
      part(leg,boot,colors,.34,.17,[s*.30-hip.x,.087-hip.y,.07],'pixel-boot',6);
      if(s===1)kickingLeg=leg;
    }
    const arms=[];
    for(const s of [-1,1]){
      const shoulder=v(s*.28,1.48,0),elbow=v(s*.48,1.22,.01),wrist=v(s*.63,1.04,.10);
      const upper=limb(model,shoulder,elbow,.22,sleeve,colors,'pixel-sleeve');
      const lower=limb(model,elbow,wrist,.18,isKeeper?sleeve:forearm,colors,'pixel-forearm');
      const offset=v(0,-.045,.03);
      const hand=part(model,isKeeper?glove:fist,colors,isKeeper?.27:.20,isKeeper?.28:.22,
        wrist.clone().add(offset).toArray(),'pixel-hand',8);
      arms.push({s,shoulder,elbow,wrist,upper,lower,hand,offset});
    }
    function poseHands(target=null,amount=0) {
      pivot.updateMatrixWorld(true);
      for(const arm of arms){
        const wrist=arm.wrist.clone();
        if(target)wrist.lerp(model.worldToLocal(target.clone().add(v(0,0,arm.s*C.penalty.ballRadius*.85))).sub(arm.offset),amount);
        const elbow=arm.elbow.clone().lerp(arm.shoulder.clone().lerp(wrist,.52).add(v(0,0,.06)),amount);
        setLimb(arm.upper,arm.shoulder,elbow);setLimb(arm.lower,elbow,wrist);
        arm.hand.position.copy(wrist).add(arm.offset);
      }
    }
    const rigParts=parts.slice(firstPart);
    figure.parts=rigParts;
    function setKit(index){
      figure.kit=index;
      for(const part of rigParts)part.sprite.material.map=part.kits[index];
    }
    return {group:pivot,poseHands,setKit,shirtColor:()=>kits[figure.kit].B,kick:amount=>{kickingLeg.rotation.x=amount;},
      handPositions:()=>{pivot.updateMatrixWorld(true);return arms.map(a=>a.hand.getWorldPosition(v()));},
      handCenter:()=>{pivot.updateMatrixWorld(true);return arms.reduce((sum,a)=>sum.add(a.hand.getWorldPosition(v())),v()).multiplyScalar(.5);}};
  }
  const keeperRig=player(true),strikerRig=player(false);strikerRig.group.rotation.y=Math.PI;
  const defaultTextures=new Set(textures);
  let role='shooter',outfitsKey='',outfits=[null,null],customMaps=[];
  function setRole(value){role=value;keeperRig.setKit(role==='keeper'?0:1);strikerRig.setKit(role==='keeper'?1:0);}
  function setOutfits(value){
    const key=JSON.stringify(value.map(o=>[o?.kit?.id,o?.number]));if(key===outfitsKey)return;
    outfitsKey=key;outfits=value;
    // Replace cosmetic textures as a batch. Repeated matches/polls cannot
    // accumulate GPU textures; skin, faces, gloves and boots remain shared.
    for(const map of new Set(customMaps))if(!defaultTextures.has(map)){textures.delete(map);map.dispose();}
    for(const [cacheKey,map] of textureCache)if(!textures.has(map))textureCache.delete(cacheKey);
    customMaps=[];
    const maps=value.map(o=>{
      if(!o?.kit)return null;
      const result=Object.fromEntries(['front','back','sleeve','shorts','sock'].map(part=>{
        const {rows,colors}=kitPixels(o.kit,part,o.number);
        const map=texture(rows,colors);customMaps.push(map);return [part,map];
      }));
      result.thigh=texture(thigh,{...palette,C:parseInt(o.kit.design.shorts.slice(1),16)});
      customMaps.push(result.thigh);return result;
    });
    for(const figure of figures){
      figure.front=figure.defaults.front.map((pair,index)=>[maps[index]?.front||pair[0],pair[1]]);
      figure.back=figure.defaults.back.map((pair,index)=>[maps[index]?.back||pair[0],pair[1]]);
      for(const part of figure.parts){
        if(!part.defaults)part.defaults=part.kits;
        const name=part.name==='pixel-forearm'&&figure.isKeeper?'sleeve':{'pixel-sleeve':'sleeve','pixel-shorts':'shorts','pixel-sock':'sock','pixel-thigh':'thigh'}[part.name];
        part.kits=part.defaults.map((map,index)=>maps[index]?.[name]||map);
      }
    }
    setRole(role);
  }

  // Project each bone into the camera plane before drawing its pixel sprite.
  // Thus a diving body rotates as one rig, while both gloves stay on the
  // physically simulated ball. The sprite atlas itself is never resampled.
  function prepareFrame(camera,renderHeight=240) {
    scene.updateMatrixWorld(true);
    ballSprite.material.map=ballFrames[Math.floor(Math.abs(ball.rotation.z)*1.5)%ballFrames.length];
    const ballDepth=-ball.getWorldPosition(v()).applyMatrix4(camera.matrixWorldInverse).z;
    const ballPixelsPerUnit=renderHeight*camera.projectionMatrix.elements[5]/(2*Math.max(.01,ballDepth));
    ballSprite.scale.setScalar(Math.max(C.penalty.ballRadius*2,C.penalty.minimumBallPixels/Math.max(.01,ballPixelsPerUnit)));
    // Keep the chosen kit on both the front and back of the animated figure.
    for(const figure of figures){
      const origin=figure.model.getWorldPosition(v());
      const normal=figure.model.localToWorld(v(0,0,1)).sub(origin);
      const facing=normal.dot(camera.getWorldPosition(v()).sub(origin))>=0;
      const maps=(facing?figure.front:figure.back)[figure.kit];
      figure.torso.material.map=maps[0];figure.head.material.map=maps[1];
    }
    // Preserve a solid white core at small framebuffer sizes. Subpixel posts
    // otherwise alternate black/white along the diagonal and look broken.
    for(const {mesh,edge,length,width,outline} of outlinedBars){
      const depth=-mesh.getWorldPosition(v()).applyMatrix4(camera.matrixWorldInverse).z;
      const pixelsPerUnit=renderHeight*camera.projectionMatrix.elements[5]/(2*(camera.isPerspectiveCamera?depth:1));
      const core=Math.max(width,2.2/Math.max(.01,pixelsPerUnit));
      const rim=Math.max(outline,1/Math.max(.01,pixelsPerUnit));
      mesh.scale.set(core,length+core,core);
      edge.scale.set(core+rim*2,length+core+rim*2,core+rim*2);
    }
    for(const {anchor,sprite,width,height} of parts){
      const a=anchor.localToWorld(v(0,-height/2,0)).applyMatrix4(camera.matrixWorldInverse);
      const b=anchor.localToWorld(v(0,height/2,0)).applyMatrix4(camera.matrixWorldInverse);
      const dx=b.x-a.x,dy=b.y-a.y;
      const scale=anchor.getWorldScale(v());
      sprite.scale.set(width,Math.max(.001,Math.hypot(dx,dy)/scale.y),1);
      sprite.material.rotation=Math.atan2(-dx,dy);
    }
    // Ground paint must occupy a full logical pixel even on foreshortened
    // horizontal edges. Otherwise an unfiltered arc turns into a dotted line.
    for(const {points,geometry} of markings){
      const p=geometry.attributes.position;let index=0;
      for(let i=1;i<points.length;i++){
        const [ax,az]=points[i-1],[bx,bz]=points[i],length=Math.hypot(bx-ax,bz-az);
        const nx=-(bz-az)/length,nz=(bx-ax)/length;
        const centre=v((ax+bx)/2,C.pitchMarkings.elevation,(az+bz)/2);
        const a=v(ax,centre.y,az).project(camera),b=v(bx,centre.y,bz).project(camera);
        const n=centre.clone().add(v(nx,0,nz)).project(camera).sub(centre.clone().project(camera));
        const aspect=camera.isPerspectiveCamera?camera.aspect:(camera.right-camera.left)/(camera.top-camera.bottom);
        const tx=(b.x-a.x)*aspect,ty=b.y-a.y;
        const pixelsPerUnit=Math.abs(n.x*aspect*ty-n.y*tx)/Math.max(.00001,Math.hypot(tx,ty))*renderHeight/2;
        const half=Math.max(C.pitchMarkings.width/2,.70/Math.max(.01,pixelsPerUnit));
        const dx=nx*half,dz=nz*half,y=centre.y;
        for(const xyz of [[ax+dx,y,az+dz],[bx+dx,y,bz+dz],[ax-dx,y,az-dz],
          [ax-dx,y,az-dz],[bx+dx,y,bz+dz],[bx-dx,y,bz-dz]])p.setXYZ(index++,...xyz);
      }
      p.needsUpdate=true;
    }
  }
  function shadow(w,d) {
    const mesh=plane(pitch,C.colors.shadow,0,0,w,d,.005);
    mesh.material.transparent=true;mesh.material.opacity=.35;mesh.material.depthWrite=false;
    return mesh;
  }
  const ballShadow=shadow(.5,.24),keeperShadow=shadow(1.3,.45),strikerShadow=shadow(1,.42);
  function shadows(){
    ballShadow.position.set(ball.position.x,.005,ball.position.z);
    ballShadow.material.opacity=.4/(1+ball.position.y*1.2);
    keeperShadow.position.set(keeperRig.group.position.x,.005,keeperRig.group.position.z);
    strikerShadow.position.set(strikerRig.group.position.x,.005,strikerRig.group.position.z);
  }
  let theme='light';
  function setTheme(value){theme=value==='dark'?'dark':'light';}
  return {ball,pitch,keeperRig,strikerRig,rippleNet,shadows,setTheme,setRole,setOutfits,prepareFrame,
    ballVisualSize:()=>ballSprite.scale.x,
    dispose:()=>textures.forEach(map=>map.dispose()),
    inspect:()=>({theme,ballStyle:'pixel-art',markingsColor:paint.color.getHex(),
      keeperShirt:keeperRig.shirtColor(),strikerShirt:strikerRig.shirtColor(),
      keeperOutfit:outfits[role==='keeper'?0:1]?.kit?.id||null,strikerOutfit:outfits[role==='keeper'?1:0]?.kit?.id||null,
      keeperNumber:outfits[role==='keeper'?0:1]?.number||10,strikerNumber:outfits[role==='keeper'?1:0]?.number||10,
      goalColor:C.colors.goal,netColor:net.material.color.getHex(),goalOutline:C.structure.goalOutline,
      characterStyle:'pixel-art',spriteTextures:textures.size,environmentVisible:false,stadiumObjects:0,reference:'pixel-art'})};
}
