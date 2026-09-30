/* Contracts for the replacement of the old fading stadium with a small scene. */
const test=require('node:test'),assert=require('node:assert/strict');

async function setup(){
  const THREE=await import('../trivia_app/static/vendor/three/three.module.min.js');
  const {createStadiumWorld}=await import('../trivia_app/static/stadium_v6_world.js');
  const scene=new THREE.Scene(),world=createStadiumWorld(scene),materials=new Set(),geometries=new Set();
  scene.traverse(o=>{if(o.geometry)geometries.add(o.geometry);for(const mat of [].concat(o.material||[]))materials.add(mat);});
  return {scene,world,materials,dispose(){world.dispose();for(const r of [...materials,...geometries])r.dispose();}};
}

test('only the penalty area, goal, ball and two simple players are constructed',async()=>{
  const {scene,world,materials,dispose}=await setup();
  try{
    assert.deepEqual(scene.children.map(o=>o.name),['penalty-area','goal','pixel-football','goalkeeper','striker']);
    scene.traverse(o=>{assert(!o.isLight);assert(!/stadium|tunnel|stand|supporter|floodlight/.test(o.name));});
    for(const m of materials){
      assert(!m.isShaderMaterial);assert(!m.gradientMap);
      if(m.map){assert(m.map.isDataTexture);assert.equal(m.map.generateMipmaps,false);}
    }
    assert.equal(world.inspect().stadiumObjects,0);
    assert.equal(world.inspect().characterStyle,'pixel-art');
    assert.equal(world.inspect().ballStyle,'pixel-art');
    const football=scene.getObjectByName('pixel-football-sprite').material.map.image;
    assert.equal(football.width,16);assert.equal(football.height,16);
    assert(football.data.some((value,i)=>i%4===3&&value===0),'Round football has transparent corners');
  }finally{dispose();}
});

test('theme changes do not rebuild, fade or hide any geometry',async()=>{
  const {scene,world,materials,dispose}=await setup();
  try{
    const initial=new Map([...materials].map(m=>[m,[m.version,m.transparent,m.depthWrite,m.opacity]]));
    for(const theme of ['dark','light','dark']){
      world.setTheme(theme);
      assert.equal(world.inspect().theme,theme);
      for(const key of ['markingsColor','goalColor','netColor'])assert.equal(world.inspect()[key],0xffffff);
      scene.traverse(o=>assert(o.visible));
      for(const m of materials)assert.deepEqual([m.version,m.transparent,m.depthWrite,m.opacity],initial.get(m));
    }
  }finally{dispose();}
});

test('the local blue kit follows the role without rebuilding sprites or losing the catch',async()=>{
  const {world,dispose}=await setup();
  try{
    const {PerspectiveCamera,Vector3}=await import('../trivia_app/static/vendor/three/three.module.min.js');
    const camera=new PerspectiveCamera(40,3,.1,100);camera.position.set(29.5,5,-10);camera.lookAt(47.5,.9,0);camera.updateMatrixWorld(true);
    const count=world.inspect().spriteTextures;
    const pixelColors=map=>{
      const colors=new Set(),data=map.image.data;
      for(let i=0;i<data.length;i+=4)if(data[i+3])colors.add(data[i]<<16|data[i+1]<<8|data[i+2]);
      return colors;
    };
    for(const role of ['shooter','keeper','shooter','keeper']){
      world.setRole(role);
      const target=new Vector3(51.8,1.25,1);world.keeperRig.poseHands(target,1);world.prepareFrame(camera,240);
      for(const [rig,local] of [[world.keeperRig,role==='keeper'],[world.strikerRig,role==='shooter']]){
        const shirt=rig.group.getObjectByName('pixel-shirt').children[0].material.map;
        const colors=pixelColors(shirt);
        assert(colors.has(local?0x92a8d1:0x6f2c91));
        assert(!colors.has(local?0x6f2c91:0x92a8d1));
      }
      assert.equal(world.inspect().spriteTextures,count);
      assert(world.keeperRig.handCenter().distanceTo(target)<.001);
    }
  }finally{dispose();}
});

test('continuous turf, complete penalty markings and a deformable sparse net',async()=>{
  const {scene,world,dispose}=await setup();
  try{
    const grass=scene.getObjectByName('penalty-turf');grass.geometry.computeBoundingBox();
    const box=grass.geometry.boundingBox;
    assert(box.max.x-box.min.x>=150&&box.max.y-box.min.y>=200,'Full rectangular grass continues offscreen');
    for(const part of ['penalty-area','goal-area','penalty-arc','goal-line'])assert(scene.getObjectByName('pitch-marking-'+part));
    const spot=scene.getObjectByName('penalty-spot');
    assert.equal(spot.geometry.type,'CircleGeometry');assert.equal(spot.position.x,41.5);assert.equal(spot.position.z,0);
    const net=scene.getObjectByName('goal-net'),positions=net.geometry.attributes.position;
    assert(positions.count<400);assert(net.material.opacity<=.8);
    const original=Array.from(positions.array);world.rippleNet(.15,1,1);
    assert.notDeepEqual(Array.from(positions.array),original);
    world.rippleNet(0);assert.deepEqual(Array.from(positions.array),original);
  }finally{dispose();}
});
