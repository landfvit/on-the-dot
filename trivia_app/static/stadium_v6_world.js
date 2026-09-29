/* Geometrie prevzata z uzivatelem dodaneho stadion_penalty_v6.html.
 * Three.js zustava lokalni r180; puvodni pribalenou r140 znovu nenacitame.
 * Tento modul neobsahuje demo UI, vyber vysledku ani herni casomiru.
 */
import * as THREE from './vendor/three/three.module.min.js';
import {V6_WORLD as CONFIG} from './stadium_config.js?v=16';

export function createStadiumWorld(scene) {
  const v=(x=0,y=0,z=0)=>new THREE.Vector3(x,y,z);
  const clamp=x=>Math.max(0,Math.min(1,x)), lerp=THREE.MathUtils.lerp;
  const environment=new THREE.Group(), fills=new THREE.Group(),pitch=new THREE.Group(),goal=new THREE.Group(),tunnel=new THREE.Group();
  environment.add(fills,tunnel);scene.add(environment,pitch,goal);
  let activeGroup=pitch;
  const fadeUniform={value:0},lineMaterials=new Map(),textures=new Set();
  scene.add(new THREE.HemisphereLight(0xe6f4ed, 0x66806a, 2.1));
  const key = new THREE.DirectionalLight(0xffeed8, 2.7);
  key.position.set(33, 17, -13); scene.add(key);
  const rim = new THREE.DirectionalLight(0xc0e4f2, 1.35);
  rim.position.set(58, 8, 9); scene.add(rim);


  // Materiály stadionu mají VLASTNÍ fade. Materiály brány/čar/figurky se nesdílejí.
  function fadingMaterial(mat) {
    // Stejny shader a depth test po cely prijezd: prepinani transparent/depthWrite
    // pri prvnim fade snimku kompilovalo novy program a odkryvalo zadni hrany.
    // Pri focus=0 ma plast alpha=1 a stale zapisuje hloubku, tedy je nepruhledny.
    mat.transparent = true;
    mat.forceSinglePass = true;
    mat.onBeforeCompile = (shader) => {
      shader.uniforms.uStadiumFade = fadeUniform;
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vFadeWorld;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvFadeWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nuniform float uStadiumFade;\nvarying vec3 vFadeWorld;')
        .replace('#include <opaque_fragment>', `#include <opaque_fragment>
          // Stejna svetova souradnice znamena stejnou masku pro sedacku i jeji
          // obrys. Horni rady mizi prvni; sirka 0.6 odpovida mekke masce UI.
          float row = 1.0 - clamp(vFadeWorld.y / 12.0, 0.0, 1.0);
          float edge = uStadiumFade * 1.6;
          float remaining = smoothstep(edge - 0.6, edge, row);
          // Globalni slozka zacina hned spolecne s UI a zjemni posledni rady.
          gl_FragColor.a *= remaining * (1.0 - uStadiumFade);
        `);
    };
    mat.customProgramCacheKey = () => 'stadium-gradient-fade-v7';
    return mat;
  }
  function isBackground(parent) { return parent === environment || parent === fills || parent === tunnel; }
  function material(color, opacity = 1, parent = activeGroup) {
    const fading = isBackground(parent);
    const key = `${color}:${opacity}:${fading}`;
    if (!lineMaterials.has(key)) {
      let mat = new THREE.MeshBasicMaterial({ color, opacity, transparent: true, depthWrite: false });
      if (fading) mat = fadingMaterial(mat);
      lineMaterials.set(key, mat);
    }
    return lineMaterials.get(key);
  }
  function line(points, color = CONFIG.colors.outline, opacity = 1, parent = activeGroup) {
    // Merged square rods keep a true world-space line width on mobile WebGL.
    const box=new THREE.BoxGeometry(1,1,1).toNonIndexed(),source=box.attributes.position;
    const vertices=[],pose=new THREE.Object3D(),point=v(),up=v(0,1,0);
    for(let i=1;i<points.length;i++){
      const a=v(...points[i-1]),b=v(...points[i]),direction=b.clone().sub(a);
      if(direction.length()<.001)continue;
      pose.position.copy(a).add(b).multiplyScalar(.5);
      pose.scale.set(CONFIG.structure.lineRadius*2,direction.length(),CONFIG.structure.lineRadius*2);
      pose.quaternion.setFromUnitVectors(up,direction.normalize());pose.updateMatrix();
      for(let j=0;j<source.count;j++){point.fromBufferAttribute(source,j).applyMatrix4(pose.matrix);vertices.push(point.x,point.y,point.z);}
    }
    box.dispose();
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
    const object = new THREE.Mesh(geometry, material(color, opacity, parent));
    if(isBackground(parent))object.renderOrder=-1;
    parent.add(object); return object;
  }
  // Malované čáry tvoří ploché trojúhelníkové pásy. WebGL linewidth se nepoužívá.
  // Rohy sdílejí vrcholy: na pokutovém území nevznikají překryvy ani spáry.
  const markingMaterial = new THREE.MeshBasicMaterial({
    color: CONFIG.colors.markings, side: THREE.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
  });
  let markingNumber = 0;
  function paintedLine(points, closed = false) {
    const half = CONFIG.pitchMarkings.width / 2;
    const vertices = [], indices = [];
    const count = points.length;
    for (let i = 0; i < count; i++) {
      const [x, z] = points[i];
      const prev = points[(i - 1 + count) % count];
      const next = points[(i + 1) % count];
      let dx = 0, dz = 0;
      if (!closed && (i === 0 || i === count - 1)) {
        const a = i === 0 ? points[0] : points[count - 2];
        const b = i === 0 ? points[1] : points[count - 1];
        const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
        dx = -(b[1] - a[1]) / length * half;
        dz =  (b[0] - a[0]) / length * half;
      } else {
        const inLength = Math.hypot(x - prev[0], z - prev[1]);
        const outLength = Math.hypot(next[0] - x, next[1] - z);
        const nx1 = -(z - prev[1]) / inLength, nz1 = (x - prev[0]) / inLength;
        const nx2 = -(next[1] - z) / outLength, nz2 = (next[0] - x) / outLength;
        const mx = nx1 + nx2, mz = nz1 + nz2;
        const scale = half / Math.max(0.25, mx * nx2 + mz * nz2);
        dx = mx * scale; dz = mz * scale;
      }
      vertices.push(x + dx, CONFIG.pitchMarkings.elevation, z + dz,
                    x - dx, CONFIG.pitchMarkings.elevation, z - dz);
    }
    const segments = closed ? count : count - 1;
    for (let i = 0; i < segments; i++) {
      const a = i * 2, b = ((i + 1) % count) * 2;
      indices.push(a, b, a + 1, a + 1, b, b + 1);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices); geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, markingMaterial);
    mesh.name = `pitch-marking-${++markingNumber}`;
    mesh.userData.width = CONFIG.pitchMarkings.width;
    pitch.add(mesh); return mesh;
  }
  function flatRect(x1, z1, x2, z2) {
    return paintedLine([[x1,z1],[x2,z1],[x2,z2],[x1,z2]], true);
  }
  function arc(cx, cz, r, start = 0, end = Math.PI*2) {
    const closed = Math.abs(end - start - Math.PI*2) < 1e-6;
    const segments = Math.max(32, Math.ceil(Math.abs(end - start) * 32));
    const points = [];
    for (let i = 0; i < segments + (closed ? 0 : 1); i++) {
      const a = lerp(start, end, i / segments);
      points.push([cx + Math.cos(a)*r, cz + Math.sin(a)*r]);
    }
    return paintedLine(points, closed);
  }
  function dot(x, z, name, radius = 0.13) {
    // JEDEN PLNÝ PUNTÍK. Žádná RingGeometry, obvod ani svítící halo.
    const mesh = new THREE.Mesh(new THREE.CircleGeometry(radius, 40),
      new THREE.MeshBasicMaterial({ color: CONFIG.colors.markings }));
    mesh.rotation.x = -Math.PI/2; mesh.position.set(x, 0.024, z);
    mesh.name = name; pitch.add(mesh); return mesh;
  }
  function surface(color, extras = {}) {
    // Flat, unlit surfaces preserve the graphic palette without glossy casts.
    return new THREE.MeshBasicMaterial({ color });
  }
  function tube(a, b, radius, mat, parent = goal, segments = 12) {
    const object = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 1, segments), mat);
    parent.add(object); setSegment(object, v(...a), v(...b)); return object;
  }
  const axisY = v(0,1,0);
  function setSegment(mesh, start, end) {
    mesh.position.copy(start).add(end).multiplyScalar(0.5);
    const direction = end.clone().sub(start);
    mesh.scale.y = direction.length();
    mesh.quaternion.setFromUnitVectors(axisY, direction.normalize());
  }

  function buildPitch() {
    // Barevný trávník je samostatná plocha. Za brankou přechází měkce do pozadí.
    const turfMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uFocus: fadeUniform,
        uLight: { value: new THREE.Color(CONFIG.colors.pitch) },
        uDark: { value: new THREE.Color(CONFIG.colors.pitchDark) },
      },
      transparent: true,
      depthWrite: true,
      vertexShader: `varying vec3 vWorld;
        void main() { vec4 world = modelMatrix * vec4(position, 1.0); vWorld = world.xyz;
          gl_Position = projectionMatrix * viewMatrix * world; }`,
      fragmentShader: `uniform float uFocus; uniform vec3 uLight; uniform vec3 uDark; varying vec3 vWorld;
        void main() {
          float stripe = 0.5 + 0.5 * cos(vWorld.x * 0.60);
          float lightPool = exp(-0.0007 * pow(vWorld.x - 44.0, 2.0) - 0.0013 * vWorld.z * vWorld.z);
          vec3 col = mix(uDark, uLight, 0.40 + 0.48 * lightPool + 0.025 * stripe);
          float back = 1.0 - smoothstep(54.0, 78.0, vWorld.x);
          float sides = 1.0 - smoothstep(28.0, 68.0, abs(vWorld.z));
          float edgeX = 1.0 - smoothstep(108.0, 120.0, abs(vWorld.x));
          float edgeZ = 1.0 - smoothstep(78.0, 90.0, abs(vWorld.z));
          // Otvor pod tunelem je skutečně vynechaný v geometrii, ne jen průhledný.
          float alpha = edgeX * edgeZ * mix(1.0, back * sides, uFocus);
          if (alpha < 0.001) discard;
          gl_FragColor = vec4(col, alpha);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    });
    // Turf ends at the INNER terrace footprint, including its rounded corners.
    // It cannot protrude beyond the stadium during the overhead outro, and it
    // stops at the tunnel mouth rather than passing underneath the corridor.
    const footprint=ring(59,40,8,0),shape=new THREE.Shape();
    footprint.forEach(([x,,z],i)=>i?shape.lineTo(x,-z):shape.moveTo(x,-z));
    shape.closePath();
    const groundGeometry = new THREE.ShapeGeometry(shape);
    groundGeometry.rotateX(-Math.PI/2);
    const grass = new THREE.Mesh(groundGeometry, turfMaterial);
    grass.position.y = CONFIG.ground.turfY;
    grass.userData.tunnelCutout = true;
    grass.renderOrder = -2; grass.name = 'soft-green-pitch'; pitch.add(grass);
    activeGroup = pitch;
    flatRect(-52.5, -34, 52.5, 34);
    paintedLine([[0,-34],[0,34]]);
    arc(0,0,9.15);
    // Výrazný plný středový puntík: nesplývá s půlicí čárou.
    // Penaltové puntíky si ponechávají původní velikost; další kruh nepřidáváme.
    dot(0,0,'centre-spot',CONFIG.pitchMarkings.centreSpotRadius);
    for (const sign of [-1,1]) {
      // Otevřené U: společná branková čára už patří obvodu hřiště, nekreslí se podruhé.
      paintedLine([[sign*52.5,-20.16],[sign*36,-20.16],[sign*36,20.16],[sign*52.5,20.16]]);
      paintedLine([[sign*52.5,-9.16],[sign*47,-9.16],[sign*47,9.16],[sign*52.5,9.16]]);
      dot(sign*41.5,0,sign===1 ? 'penalty-spot' : 'opposite-penalty-spot');
      const a = Math.acos(5.5/9.15);
      arc(sign*41.5,0,9.15,sign===-1 ? -a : Math.PI-a,sign===-1 ? a : Math.PI+a);
    }
    // Vzdálená brána je součást stadionu a spolu s ním zmizí.
    line([[-52.5,0,-3.66],[-52.5,2.44,-3.66],[-52.5,2.44,3.66],[-52.5,0,3.66]],
      CONFIG.colors.outline, 1, environment);
    // Bez zelených svislých značek u rohů: při výjezdu z tunelu zůstává jen bílé značení.
  }

  // Jeden spojitý, uzavřený rám ve tvaru U. V rozích se sousední úseky
  // dělí o stejný prstenec vrcholů (pokosový spoj), ne o tři překryté válce.
  function continuousFrame(x, halfWidth, height, radius, mat, name) {
    const centres = [[x,0,-halfWidth],[x,height,-halfWidth],
                     [x,height,halfWidth],[x,0,halfWidth]];
    const miters = [[0,-1],[1,-1],[1,1],[0,1]]; // Y/Z, v rozích záměrně délka sqrt(2)
    const radial = 24, positions = [], indices = [];
    for (let row = 0; row < centres.length; row++) {
      const [cx,cy,cz] = centres[row], [my,mz] = miters[row];
      for (let i = 0; i < radial; i++) {
        const a = i / radial * Math.PI * 2;
        positions.push(cx + radius * Math.cos(a),
          cy + radius * Math.sin(a) * my, cz + radius * Math.sin(a) * mz);
      }
    }
    for (let row = 0; row < centres.length - 1; row++) {
      for (let i = 0; i < radial; i++) {
        const j = (i + 1) % radial, a = row*radial+i, b = row*radial+j;
        const c = (row+1)*radial+i, d = (row+1)*radial+j;
        indices.push(a,b,c,b,d,c);
      }
    }
    // Spodní čela rámu: geometrie je uzavřená i u země.
    for (let i = 1; i < radial - 1; i++) {
      indices.push(0,i+1,i);
      const base = (centres.length - 1) * radial;
      indices.push(base,base+i,base+i+1);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
    geometry.setIndex(indices); geometry.computeVertexNormals(); geometry.computeBoundingSphere();
    const frame = new THREE.Mesh(geometry,mat); frame.name = name;
    frame.userData.continuous = true; goal.add(frame); return frame;
  }

  let net, netRest;
  function buildGoal() {
    const x = CONFIG.penalty.goalX, back = x+2, z = 3.66;
    const posts = new THREE.MeshBasicMaterial({color:CONFIG.colors.goal});
    continuousFrame(x,z,2.44,CONFIG.structure.postRadius,posts,'goal-frame-continuous');
    // A slightly larger back-facing shell gives a thin silhouette on both
    // sides of each white post, including the corners and keeper camera view.
    // Do not use stadium ink/theme here: this outline must remain black.
    const border=new THREE.MeshBasicMaterial({color:0x111111,side:THREE.BackSide});
    continuousFrame(x,z,2.44,CONFIG.structure.postRadius+CONFIG.structure.goalOutline,border,'goal-frame-outline');
    const supports = new THREE.MeshBasicMaterial({color:CONFIG.colors.goal});
    continuousFrame(back,z,2.15,0.021,supports,'goal-rear-frame-continuous');
    continuousFrame(back,z,2.15,0.024,border,'goal-rear-frame-outline');
    for (const s of [-1,1]) {
      tube([x,0.02,s*z],[back,0.02,s*z],0.021,supports);
      tube([x,2.44,s*z],[back,2.15,s*z],0.022,supports);
    }
    tube([back,0.02,-z],[back,0.02,z],0.021,supports);
    // Jediný LineSegments objekt: síť vzadu, na obou bocích i nahoře.
    const points = [];
    const segment = (a,b) => points.push(...a,...b);
    const top = (t) => lerp(2.44,2.15,t);
    const nZ = 30, nY = 10, nX = 9;
    for (let j=0;j<=nZ;j++) {
      const zz=lerp(-z,z,j/nZ);
      for (let k=0;k<nY;k++)
        segment([back,2.15*k/nY,zz],[back,2.15*(k+1)/nY,zz]);
      segment([x,2.44,zz],[back,2.15,zz]);
    }
    for (let j=0;j<=nY;j++) {
      const yy=2.15*j/nY;
      for (let k=0;k<nZ;k++)
        segment([back,yy,lerp(-z,z,k/nZ)],[back,yy,lerp(-z,z,(k+1)/nZ)]);
      for (const s of [-1,1]) segment([x,2.44*j/nY,s*z],[back,yy,s*z]);
    }
    for (let j=0;j<=nX;j++) {
      const t=j/nX, xx=lerp(x,back,t);
      segment([xx,top(t),-z],[xx,top(t),z]);
      for (const s of [-1,1]) segment([xx,0,s*z],[xx,top(t),s*z]);
    }
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(points,3));
    netRest=new Float32Array(points);
    net=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({
      color:CONFIG.colors.goal, transparent:true, opacity:CONFIG.structure.netOpacity, depthWrite:false,
    }));
    net.name='goal-net'; goal.add(net);
  }
  function rippleNet(amount=0,targetZ=0,targetY=.6) {
    const attr=net.geometry.attributes.position;
    for (let i=0;i<attr.count;i++) {
      const j=i*3, x=netRest[j], y=netRest[j+1], z=netRest[j+2];
      const spread=Math.exp(-((z-targetZ)**2+(y-targetY)**2)*0.8);
      const depth=clamp((x-CONFIG.penalty.goalX)/2);
      // Síť pruží pouze uvnitř. Obvod zůstává přichycený k rámu i při gólu.
      const roof = lerp(2.44,2.15,depth);
      const pinned = Math.sin(Math.PI*clamp(y/roof))
        * Math.sin(Math.PI*clamp((z+3.66)/7.32));
      attr.setXYZ(i,x+amount*spread*depth*pinned,y,z);
    }
    attr.needsUpdate=true;
  }

  function ring(hx,hz,radius,y) {
    const points=[[4.7,y,hz]];
    const corners=[
      [hx-radius,hz-radius,Math.PI/2,0], [hx-radius,-hz+radius,0,-Math.PI/2],
      [-hx+radius,-hz+radius,-Math.PI/2,-Math.PI],[-hx+radius,hz-radius,Math.PI,Math.PI/2],
    ];
    for (const [cx,cz,a,b] of corners) for(let i=0;i<=12;i++) {
      const t=lerp(a,b,i/12); points.push([cx+Math.cos(t)*radius,y,cz+Math.sin(t)*radius]);
    }
    points.push([-4.7,y,hz]); return points;
  }
  function buildStands() {
    activeGroup=environment;
    const rows=[];
    for(let i=0;i<14;i++) {
      const points=ring(59+i*1.12,40+i*1.05,8+i*0.3,0.8+i*0.85);
      rows.push(points);
      line(points,CONFIG.colors.outline,1);
    }
    const inner=rows[0],outer=rows.at(-1),positions=[];
    const push=(...points)=>points.forEach((p)=>positions.push(...p));
    const floor=p=>[p[0],0,p[2]];
    const quad=(a,b,c,d)=>push(a,b,c,a,c,d);
    // Uzavrene tribuny: svah, celni obruba, zadni plast a boky u tunelu.
    // Bez techto sten jsou ze strany videt zebra a konstrukce protilehle tribuny.
    for(let i=0;i<inner.length-1;i++) {
      // Real terrace steps, not a featureless slope behind floating supporters.
      // Each row has a horizontal tread and an opaque vertical riser.
      for(let row=0;row<rows.length-1;row++){
        const a=rows[row][i],b=rows[row][i+1],c=rows[row+1][i+1],d=rows[row+1][i];
        const cLow=[c[0],a[1],c[2]],dLow=[d[0],a[1],d[2]];
        quad(a,dLow,cLow,b);quad(dLow,d,c,cLow);
      }
      quad(outer[i],floor(outer[i]),floor(outer[i+1]),outer[i+1]);
      quad(inner[i],inner[i+1],floor(inner[i+1]),floor(inner[i]));
    }
    for(const i of [0,inner.length-1])quad(inner[i],floor(inner[i]),floor(outer[i]),outer[i]);
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
    const standMesh=new THREE.Mesh(geometry,fadingMaterial(new THREE.MeshBasicMaterial({
      color:CONFIG.colors.stands, side:THREE.DoubleSide,
      // Plocha zapisuje hloubku; drobny offset ponecha citelne predni obrysy.
      depthWrite:true, transparent:false, polygonOffset:true, polygonOffsetFactor:1, polygonOffsetUnits:1,
    })));
    // Pri alpha fade musi cele pozadi zustat za siti. Sortovani velkeho
    // prstence podle jeho stredu by jinak mohlo prekreslit blizkou sit.
    // Plast pred obrysy: zadni cary zustanou zakryte i behem rozpousteni.
    standMesh.renderOrder=-2;fills.add(standMesh);
    for(const i of [0,1,7,13,14,20,26,27,33,39,40,46,52,53]) line([inner[i],outer[i]],CONFIG.colors.outline,1);
    for(const i of [1,7,13,20,26,33,39,46,52]) {
      const p=outer[i]; line([[p[0],0,p[2]],p],CONFIG.colors.outline,0.45);
    }
    // Bez stožárů a reflektorových ramp; zůstávají pouze nízké obrysy tribun.
  }
  function buildTunnel() {
    const {halfWidth: hw, height: h, startZ: front, endZ: back} = CONFIG.tunnel;
    const y = CONFIG.ground.tunnelFloorY;
    // Jediný neprůhledný plášť. Podlaha, stěny a strop sdílejí hrany;
    // žádné překryté boxy, žádné vnitřní diagonály ani čáry přes podlahu.
    // Tunel ma stejnou fade masku i pri pohledu z brany smerem zpet.
    const positions = [
      -hw,y,front, hw,y,front, hw,h,front, -hw,h,front,
      -hw,y,back,  hw,y,back,  hw,h,back,  -hw,h,back,
    ];
    const indices = [
      0,4,5, 0,5,1,  // podlaha
      0,3,7, 0,7,4,  // levá stěna
      1,5,6, 1,6,2,  // pravá stěna
      3,2,6, 3,6,7,  // strop; oba konce tunelu zůstávají otevřené
    ];
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
    geometry.setIndex(indices); geometry.computeVertexNormals();
    const shellMaterial = fadingMaterial(new THREE.MeshBasicMaterial({
      color: CONFIG.colors.tunnel, side: THREE.DoubleSide,
      transparent: false, depthTest: true, depthWrite: true,
    }));
    const shell = new THREE.Mesh(geometry, shellMaterial);
    shell.name = 'tunnel-solid-shell'; shell.renderOrder = -10;
    tunnel.add(shell);

    // Jemne stropni spary a portal doplnuji pevne hrany a svetla nize.
    // Podlaha zustava volna, bez pricnych ramu pres cestu kamery.
    const inset = 0.035;
    for (const sign of [-1,1]) {
      const seam = line([[sign*(hw-inset),h-inset,back],
                         [sign*(hw-inset),h-inset,front]],
                        CONFIG.colors.outline,0.30,tunnel);
      seam.name = 'tunnel-ceiling-seam';
    }
    const portal = line([[-hw+inset,y+0.04,front+inset],
                          [-hw+inset,h-inset,front+inset],
                          [hw-inset,h-inset,front+inset],
                          [hw-inset,y+0.04,front+inset]],
                         CONFIG.colors.outline,0.55,tunnel);
    portal.name = 'tunnel-exit-outline';
    // Plochy misto WebGL linewidth: hrany maji stabilni skutecnou tloustku.
    // Barvu, rozestupy a sirku svetel men v stadium_config.js.
    function strip(name, size, position, color) {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size),fadingMaterial(new THREE.MeshBasicMaterial({color})));
      mesh.renderOrder=-1;
      mesh.name=name;mesh.position.set(...position);tunnel.add(mesh);
    }
    const {edgeWidth:e,lightSpacing,lightWidth,lightDepth}=CONFIG.tunnel;
    for(const sign of [-1,1])for(const level of [y+.04,h-.04])
      strip('tunnel-wall-edge',[e,e,back-front],[sign*(hw-.04),level,(back+front)/2],CONFIG.colors.outline);
    for(let z=front+3;z<back;z+=lightSpacing) {
      strip('tunnel-ceiling-light',[lightWidth,.035,lightDepth],[0,h-.05,z],CONFIG.colors.bright);
      // Jemny lem vytvari zapusteny drzak bez oslniveho halo efektu.
      strip('tunnel-light-housing',[lightWidth+.16,.025,lightDepth+.14],[0,h-.02,z],CONFIG.colors.outline);
    }
  }
  buildPitch(); buildGoal(); buildStands(); buildTunnel();
  fills.visible=!CONFIG.outlineOnly;

  // ---------- Skutečný panelový vzor: 12 pětiúhelníků + 20 šestiúhelníků ----------
  function buildBall() {
    const root=new THREE.Group(); root.name='football-32-panels';
    const r=CONFIG.penalty.ballRadius;
    const ico=new THREE.IcosahedronGeometry(1,0);
    const input=ico.getAttribute('position');
    const vertices=[],faces=[],lookup=new Map();
    for(let i=0;i<input.count;i+=3) {
      const face=[];
      for(let j=0;j<3;j++) {
        const p=v().fromBufferAttribute(input,i+j).normalize();
        const key=p.toArray().map((n)=>n.toFixed(6)).join(',');
        if(!lookup.has(key)) { lookup.set(key,vertices.length); vertices.push(p); }
        face.push(lookup.get(key));
      }
      faces.push(face);
    }
    ico.dispose();
    const adjacent=vertices.map(()=>new Set());
    for(const [a,b,c] of faces) {
      adjacent[a].add(b).add(c); adjacent[b].add(a).add(c); adjacent[c].add(a).add(b);
    }
    const cut=(a,b)=>vertices[a].clone().multiplyScalar(2).add(vertices[b]).normalize();
    const pentagons=vertices.map((_,i)=>[...adjacent[i]].map((j)=>cut(i,j)));
    const hexagons=faces.map(([a,b,c])=>[cut(a,b),cut(b,a),cut(b,c),cut(c,b),cut(c,a),cut(a,c)]);
    const core=new THREE.Mesh(new THREE.SphereGeometry(r*0.993,48,32),surface(CONFIG.colors.ballBlack));
    root.add(core);
    function panelGeometry(polygons) {
      const positions=[],normals=[];
      function triangle(a,b,c,depth) {
        if(depth>0) {
          const ab=a.clone().add(b).normalize(),bc=b.clone().add(c).normalize(),ca=c.clone().add(a).normalize();
          triangle(a,ab,ca,depth-1); triangle(ab,b,bc,depth-1);
          triangle(ca,bc,c,depth-1); triangle(ab,bc,ca,depth-1); return;
        }
        // Orientace vždy ven z koule, bez závislosti na pořadí sousedů.
        if(b.clone().sub(a).cross(c.clone().sub(a)).dot(a)<0) [b,c]=[c,b];
        for(const p of [a,b,c]) { positions.push(p.x*r,p.y*r,p.z*r); normals.push(p.x,p.y,p.z); }
      }
      for(const polygon of polygons) {
        const center=polygon.reduce((sum,p)=>sum.add(p),v()).normalize();
        const u=polygon[0].clone().sub(center.clone().multiplyScalar(polygon[0].dot(center))).normalize();
        const w=center.clone().cross(u).normalize();
        const ordered=polygon.slice().sort((a,b)=>Math.atan2(a.dot(w),a.dot(u))-Math.atan2(b.dot(w),b.dot(u)));
        // Bold black seams match the flat football icon; the ball remains 3D.
        const inset=ordered.map((p)=>p.clone().lerp(center,0.075).normalize());
        for(let i=0;i<inset.length;i++) triangle(center,inset[i],inset[(i+1)%inset.length],2);
      }
      const geometry=new THREE.BufferGeometry();
      geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
      geometry.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));
      geometry.computeBoundingSphere(); return geometry;
    }
    const whites=new THREE.Mesh(panelGeometry(hexagons),new THREE.MeshBasicMaterial({color:CONFIG.colors.ballWhite}));
    const blacks=new THREE.Mesh(panelGeometry(pentagons),new THREE.MeshBasicMaterial({color:CONFIG.colors.ballBlack}));
    root.add(whites,blacks);
    root.userData.panels={pentagons:pentagons.length,hexagons:hexagons.length};
    scene.add(root); return root;
  }

  function softShadow(sx,sz,opacity) {
    // Měkký stín bez kruhové hrany: není to druhá značka penalty.
    const canvas=document.createElement('canvas'); canvas.width=canvas.height=128;
    const ctx=canvas.getContext('2d');
    const gradient=ctx.createRadialGradient(64,64,0,64,64,64);
    gradient.addColorStop(0,'rgba(0,0,0,0.60)');
    gradient.addColorStop(0.30,'rgba(0,0,0,0.36)');
    gradient.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=gradient; ctx.fillRect(0,0,128,128);
    const texture=new THREE.CanvasTexture(canvas); textures.add(texture);
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(sx,sz),new THREE.MeshBasicMaterial({
      map:texture,transparent:true,opacity,depthWrite:false,
    }));
    mesh.rotation.x=-Math.PI/2; mesh.position.y=0.007; pitch.add(mesh); return mesh;
  }
  const ball=buildBall();
  const ballHome=v(CONFIG.penalty.spotX,CONFIG.penalty.ballRadius+0.025,0);
  const ballShadow=softShadow(0.92,0.66,0.58);
  ballShadow.position.set(ballHome.x,0.007,0);

  // ---------- Stylizovaný brankář: dres, šortky, štulpny, rukavice ----------
  function buildKeeper(numberText="1") {
    const pivot=new THREE.Group(); pivot.name='goalkeeper'; scene.add(pivot);
    const model=new THREE.Group(); model.rotation.y=-Math.PI/2; model.position.y=-0.92; pivot.add(model);
    const mats={};
    for(const name of ['shirt','shirtTrim','shorts','gloves','gloveCuffs','boots','skin','hair']) mats[name]=surface(CONFIG.colors[name]);
    if(numberText==='10'){mats.shirt.color.setHex(CONFIG.colors.strikerShirt);mats.shirtTrim.color.setHex(CONFIG.colors.outline);mats.gloves=mats.skin;mats.gloveCuffs=mats.skin;}
    let kickingLeg=null;
    function ellipsoid(x,y,z,sx,sy,sz,mat,parent=model) {
      const mesh=new THREE.Mesh(new THREE.SphereGeometry(1,20,14),mat);
      mesh.position.set(x,y,z); mesh.scale.set(sx,sy,sz); parent.add(mesh); return mesh;
    }
    function cylinder(a,b,r,mat) { return tube(a,b,r,mat,model,12); }
    // Torzo je širší v ramenou; raději oblý střih než hranatá figurka z kostek.
    const torso=new THREE.Mesh(new THREE.CylinderGeometry(0.34,0.24,0.58,16),mats.shirt);
    torso.scale.z=0.57; torso.position.y=1.27; model.add(torso);
    ellipsoid(0,0.95,0,0.26,0.16,0.17,mats.shorts);
    cylinder([0,1.54,0],[0,1.64,0],0.071,mats.skin);
    ellipsoid(0,1.78,0,0.158,0.20,0.156,mats.skin);
    // Malý nos, uši, oči a vlasy – bez externí textury obličeje.
    ellipsoid(0,1.77,0.158,0.025,0.029,0.026,mats.skin);
    for(const s of [-1,1]) {
      ellipsoid(s*0.158,1.78,-0.003,0.026,0.044,0.022,mats.skin);
      ellipsoid(s*0.051,1.805,0.142,0.012,0.012,0.012,mats.hair);
    }
    const hair=new THREE.Mesh(new THREE.SphereGeometry(1,20,12,0,Math.PI*2,0,Math.PI*0.51),mats.hair);
    hair.scale.set(0.164,0.207,0.162); hair.position.set(0,1.79,-0.008); model.add(hair);
    for(const s of [-1,1]) {
      const hip=[s*0.16,0.95,0],knee=[s*0.29,0.53,0.07],ankle=[s*0.37,0.14,0.015];
      const first=model.children.length;
      cylinder(hip,[s*0.24,0.67,0.05],0.119,mats.shorts);
      cylinder([s*0.24,0.70,0.05],knee,0.077,mats.skin);
      cylinder(knee,ankle,0.068,mats.shirt);
      cylinder([s*0.30,0.49,0.065],[s*0.315,0.445,0.058],0.073,mats.shirtTrim);
      ellipsoid(s*0.38,0.085,0.10,0.096,0.082,0.185,mats.boots);
      // Kontrastní vršek kopačky.
      ellipsoid(s*0.38,0.129,0.16,0.077,0.029,0.091,mats.shirtTrim);
      if(s===1){
        // Articulated kicking leg: rotate around the hip, not around the foot.
        const parts=model.children.slice(first);kickingLeg=new THREE.Group();
        kickingLeg.position.set(...hip);model.add(kickingLeg);
        for(const part of parts){part.position.sub(kickingLeg.position);kickingLeg.add(part);}
      }
    }
    const arms=[];
    for(const s of [-1,1]) {
      const shoulder=v(s*0.30,1.47,0),elbow=v(s*0.54,1.16,0.035),wrist=v(s*0.68,1.01,0.17);
      ellipsoid(shoulder.x,shoulder.y,shoulder.z,0.105,0.118,0.11,mats.shirt);
      const upper=cylinder(shoulder.toArray(),elbow.toArray(),0.088,mats.shirt);
      const lower=cylinder(elbow.toArray(),wrist.toArray(),0.071,mats.shirt);
      const cuff=ellipsoid(wrist.x,wrist.y,wrist.z,0.078,0.056,0.081,mats.gloveCuffs);
      const glove=ellipsoid(wrist.x+s*0.025,wrist.y-0.075,wrist.z+0.035,0.102,0.135,0.074,mats.gloves);
      const thumb=ellipsoid(wrist.x-s*0.065,wrist.y-0.063,wrist.z+0.064,0.038,0.060,0.037,mats.gloves);
      arms.push({s,shoulder,elbow,wrist,upper,lower,cuff,glove,thumb});
      cylinder([s*0.25,1.55,0.045],[s*0.36,1.44,0.085],0.014,mats.shirtTrim);
    }
    // Decentní výstřih a jednička. Číslo vzniká na malém canvasu při startu.
    cylinder([-0.078,1.57,0.13],[0,1.51,0.172],0.011,mats.shirtTrim);
    cylinder([0,1.51,0.172],[0.078,1.57,0.13],0.011,mats.shirtTrim);
    const canvas=document.createElement('canvas');canvas.width=canvas.height=128;
    const ctx=canvas.getContext('2d'); ctx.fillStyle=numberText==='10'?'#111111':'#f6f3eb';ctx.font='bold 94px sans-serif';
    ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(numberText,64,70);
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;textures.add(texture);
    const number=new THREE.Mesh(new THREE.PlaneGeometry(0.17,0.18),new THREE.MeshBasicMaterial({
      map:texture,transparent:true,depthWrite:false,
    }));
    number.position.set(0,1.30,0.187);model.add(number);
    return {pivot,model,torso,arms,kickingLeg};
  }

  // Puvodni model v6 se pouzije i pro protihrace. Pouze jeho cislo je 10.
  const keeper=buildKeeper(),shooter=buildKeeper("10");
  shooter.pivot.rotation.y=Math.PI;
  const keeperShadow=softShadow(1.8,1.6,.62);
  function rig(player) {
    const {pivot,model,arms}=player;
    function poseHands(target=null,amount=0) {
      pivot.updateMatrixWorld(true);
      for(const arm of arms) {
        // Referencni model ma dlane pod zapestim. Offset kompenzujeme tak,
        // aby stred obou rukavic v kazde ze sesti zon opravdu drzel mic.
        const desired=target?model.worldToLocal(target.clone().add(v(0,0,arm.s*.10))):null;
        const offset=v(arm.s*.023,-.075,.035);
        const wrist=arm.wrist.clone();
        if(desired)wrist.lerp(desired.sub(offset),amount);
        const elbow=arm.elbow.clone().lerp(arm.shoulder.clone().lerp(wrist,.52).add(v(0,0,.08)),amount);
        setSegment(arm.upper,arm.shoulder,elbow);setSegment(arm.lower,elbow,wrist);
        arm.cuff.position.copy(wrist);arm.glove.position.copy(wrist).add(offset);
        arm.thumb.position.copy(wrist).add(v(-arm.s*.065,-.063,.064));
      }
    }
    return {group:pivot,poseHands,
      kick:amount=>{player.kickingLeg.rotation.x=amount;},
      handPositions:()=>{pivot.updateMatrixWorld(true);return arms.map(a=>a.glove.getWorldPosition(v()));},
      handCenter:()=>{
      pivot.updateMatrixWorld(true);
      return arms.reduce((sum,a)=>sum.add(a.glove.getWorldPosition(v())),v()).multiplyScalar(.5);
    }};
  }
  function setFocus(value) {
    // Jedina menena hodnota; zadne prepinani shaderu ani skryti jeste viditelnych car.
    const focus=clamp(value);fadeUniform.value=focus;environment.visible=focus<1;
  }
  function shadows() {
    ballShadow.position.set(ball.position.x,.007,ball.position.z);
    ballShadow.material.opacity=.58/(1+ball.position.y*2);
    keeperShadow.position.set(keeper.pivot.position.x,.007,keeper.pivot.position.z);
  }
  let theme='light';
  // Only architecture changes with the UI theme. Never recolor the pitch,
  // painted white markings, football, gloves or player jerseys.
  function setTheme(value){
    theme=value==='dark'?'dark':'light';
    const palette=new Map([[CONFIG.colors.stands,0x272b28],[CONFIG.colors.tunnel,0x333831],[CONFIG.colors.outline,0xb0b5a9]]);
    environment.traverse(o=>{for(const m of [].concat(o.material||[]))if(m.color){
      const day=m.userData.dayColor??m.color.getHex();m.userData.dayColor=day;
      m.color.setHex(theme==='dark'?(palette.get(day)??day):day);
    }});
  }
  return {ball,background:environment,pitch,keeperRig:rig(keeper),strikerRig:rig(shooter),setFocus,rippleNet,shadows,setTheme,
    dispose:()=>{textures.forEach(t=>t.dispose());},
    inspect:()=>({focus:fadeUniform.value,environmentVisible:environment.visible,
      standsSolid:fadeUniform.value===0&&fills.visible&&fills.children.every(o=>o.material.opacity===1&&o.material.depthWrite),
      panels:ball.userData.panels,theme,markingsColor:markingMaterial.color.getHex(),goalColor:CONFIG.colors.goal,netColor:net.material.color.getHex(),goalOutline:CONFIG.structure.goalOutline,reference:'v6'})};
}
