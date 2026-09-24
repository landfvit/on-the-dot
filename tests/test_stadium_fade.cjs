const test=require('node:test'),assert=require('node:assert/strict');

async function setup(){
  const THREE=await import('../trivia_app/static/vendor/three/three.module.min.js');
  const {createStadiumWorld}=await import('../trivia_app/static/stadium_v6_world.js');
  // Only textures need a canvas; no renderer or GPU is mocked in these contract tests.
  const previous=global.document;
  global.document={createElement:()=>({getContext:()=>({
    createRadialGradient:()=>({addColorStop(){}}),fillRect(){},fillText(){},
  })})};
  const scene=new THREE.Scene();
  let world;
  try{world=createStadiumWorld(scene);}finally{global.document=previous;}
  const environment=scene.children.find(o=>o.isGroup),materials=new Set();
  environment.traverse(o=>{if(o.material)materials.add(o.material);});
  return {THREE,scene,world,environment,materials};
}

test('stadium fade never recompiles or changes occlusion during the transition',async()=>{
  const {world,environment,materials}=await setup();
  const initial=new Map([...materials].map(m=>[m,[m.version,m.transparent,m.depthWrite,m.forceSinglePass]]));
  assert.equal(world.inspect().standsSolid,true);
  for(const focus of [0,.00001,.25,.5,.75,.99995]){
    world.setFocus(focus);
    assert.equal(environment.visible,true,'do not hide lines before zero alpha');
    for(const m of materials)assert.deepEqual([m.version,m.transparent,m.depthWrite,m.forceSinglePass],initial.get(m));
  }
  world.setFocus(1);assert.equal(environment.visible,false);
  world.setFocus(0);assert.equal(world.inspect().standsSolid,true);
  world.dispose();
});

test('all stadium meshes, lines and tunnel lights share the same final-output mask',async()=>{
  const {THREE,world,materials,scene,environment}=await setup();
  const uniforms=[];
  for(const mat of materials){
    const shader={uniforms:{},...THREE.ShaderLib.basic};
    mat.onBeforeCompile(shader);
    assert.ok(shader.uniforms.uStadiumFade,mat.type+' is missing its fade');
    assert.match(shader.vertexShader,/vFadeWorld =/);
    assert.ok(shader.fragmentShader.indexOf('gl_FragColor.a *=')>shader.fragmentShader.indexOf('#include <opaque_fragment>'));
    assert.equal(mat.transparent,true);
    assert.equal(mat.forceSinglePass,true);
    uniforms.push(shader.uniforms.uStadiumFade);
  }
  world.setFocus(.5);
  assert.ok(uniforms.every(u=>u===uniforms[0]&&u.value===.5));
  for(const group of scene.children.filter(o=>o!==environment))group.traverse(o=>{
    if(o.material)assert.notEqual(o.material.customProgramCacheKey(),'stadium-gradient-fade-v7','foreground must stay visible');
  });
  world.dispose();
});

test('no spectators, bounded turf and white paint in both themes',async()=>{
  const {scene,world}=await setup();
  assert.equal(scene.getObjectByName('supporters'),undefined);
  const grass=scene.getObjectByName('soft-green-pitch');grass.geometry.computeBoundingBox();
  const box=grass.geometry.boundingBox;
  assert(box.min.x>=-59&&box.max.x<=59&&box.min.z>=-40&&box.max.z<=40);
  for(const theme of ['dark','light','dark']){
    world.setTheme(theme);assert.equal(world.inspect().markingsColor,0xffffff);
    assert.equal(world.inspect().theme,theme);
  }
  world.dispose();
});
