/* Inspect procedural character assets without accounts, API calls or game writes. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),sharp=require('sharp');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/tmp/on-the-dot-players';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
(async()=>{
  const name=process.env.TEST_BROWSER||'chrome';
  const browser=name==='webkit'?await webkit.launch({headless:true}):await chromium.launch({channel:'chrome',headless:true});
  try{
    for(const [width,height] of [[1000,620],[360,300]]){
      const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:2}),errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
      await page.route('**/players-check',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><style>body{margin:0}canvas{display:block}</style>'}));
      try{
        await page.goto(origin+'/players-check');
        const diagnostics=await page.evaluate(async()=>{
          const THREE=await import('/trivia-assets/vendor/three/three.module.min.js');
          const {createStadiumWorld}=await import('/trivia-assets/stadium_v6_world.js?v=20');
          const {STADIUM}=await import('/trivia-assets/stadium_config.js?v=22');
          const scene=new THREE.Scene(),world=createStadiumWorld(scene);
          const keeper=world.keeperRig,striker=world.strikerRig;
          for(const child of scene.children)child.visible=[keeper.group,striker.group].includes(child);
          keeper.group.position.set(0,.92,-.85);striker.group.position.set(0,.92,.85);striker.group.rotation.y=0;
          const camera=new THREE.PerspectiveCamera(32,innerWidth/innerHeight,.1,30);
          const renderer=new THREE.WebGLRenderer({antialias:false});renderer.setSize(innerWidth/3,innerHeight/3);renderer.domElement.style.cssText='width:100vw;height:100vh;image-rendering:pixelated';document.body.append(renderer.domElement);
          window.renderPlayers=(theme='light',back=false)=>{
            world.setTheme(theme);scene.background=new THREE.Color(theme==='dark'?0x191d19:0xf6f3eb);
            camera.position.set(back?5.5:-5.5,2.7,back?-3.3:3.3);camera.lookAt(0,1.03,0);camera.updateMatrixWorld(true);world.prepareFrame(camera,renderer.domElement.height);renderer.render(scene,camera);
          };
          renderPlayers();
          const head=keeper.group.getObjectByName('pixel-head');
          const maps=new Set();let sprites=0;
          for(const player of [keeper,striker])player.group.traverse(o=>{
            if(o.isSprite){sprites++;maps.add(o.material.map);}
          });
          // Both hands must reach the same world-space catch target after the
          // new elbow and mitten meshes are posed, including a rotated keeper.
          const catches=[],landingFloors=[];
          for(const roll of [-1.52,0,1.52]){
            keeper.group.rotation.x=roll;
            keeper.group.position.y=.92*Math.cos(Math.abs(roll))+STADIUM.keeperHalfWidth*Math.sin(Math.abs(roll));
            for(const y of [.35,1.1,2.14]){
              const target=new THREE.Vector3(-.5,y,-.85);
              keeper.poseHands(target,1);catches.push(keeper.handCenter().distanceTo(target));
            }
            keeper.group.updateMatrixWorld(true);
            const boots=[];keeper.group.traverse(o=>{if(o.name==='pixel-boot')boots.push(o.getWorldPosition(new THREE.Vector3()).y-.085);});
            landingFloors.push(Math.min(...boots));
          }
          keeper.group.rotation.x=0;keeper.group.position.y=.92;keeper.poseHands();renderPlayers();
          window.disposePlayers=()=>{
            world.dispose();const resources=new Set();scene.traverse(o=>{if(o.geometry)resources.add(o.geometry);for(const m of [].concat(o.material||[]))resources.add(m);});
            resources.forEach(r=>r.dispose());renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();
          };
          return {style:world.inspect().characterStyle,head:!!head,sprites,textures:maps.size,
            nearest:[...maps].every(m=>m.isDataTexture&&m.minFilter===THREE.NearestFilter&&m.magFilter===THREE.NearestFilter&&!m.generateMipmaps),
            catches,landingFloors,drawCalls:renderer.info.render.calls};
        });
        assert.equal(diagnostics.style,'pixel-art');assert(diagnostics.head&&diagnostics.nearest);
        assert.equal(diagnostics.sprites,30);assert(diagnostics.textures<diagnostics.sprites);assert(diagnostics.drawCalls<50);
        assert(diagnostics.catches.every(d=>d<.001),'New mittens retain exact catch anchors');
        assert(diagnostics.landingFloors.every(y=>y>-.01),'Wider boots must not sink through the turf on landing');
        for(const theme of ['light','dark'])for(const back of [false,true]){
          await page.evaluate(({theme,back})=>renderPlayers(theme,back),{theme,back});
          const buffer=await page.screenshot({path:`${out}/${name}-${width}-${theme}-${back?'back':'front'}.png`});
          const stats=await sharp(buffer).stats();assert(stats.channels.some(c=>c.stdev>20),'Character pixels must render, not just the background');
        }
        await page.evaluate(()=>disposePlayers());assert.equal(await page.locator('canvas').count(),0);
        assert.deepEqual(errors,[]);console.log(`PASS ${name} pixel players ${width}: ${diagnostics.drawCalls} draws, reusable nearest-filtered sprites, catch anchors, both themes`);
      }finally{await page.close();}
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
