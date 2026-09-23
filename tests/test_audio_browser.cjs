/* Mocked gameplay plus real Web Audio rendering. No account/database changes. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8013';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const audioScript=fs.readFileSync(path.join(__dirname,'../trivia_app/static/audio.js'),'utf8');
const output='/tmp/on-the-dot-audio';fs.mkdirSync(output,{recursive:true});
const rules={format:'shootout',bonus_mode:'win',answer_ms:15000,xp_per_correct:10,xp_by_difficulty:{easy:10,medium:20,hard:30},win_multipliers:{easy:2,medium:3,hard:4}};
const catalog={categories:[{code:'ALL',label:'All clubs',counts:{easy:100,medium:100,hard:100}}],topics:[{code:'ALL',label:'Mixed topics',counts_by_team:{ALL:{easy:100,medium:100,hard:100}}}],rules};
const question={text:'Who won the Premier League in 2017/18?',options:[{id:'0',text:'Manchester City'},{id:'1',text:'Chelsea'}]};
let run=null;
function start(){run={run_id:'sound-test',phase:'READY',position:0,role:'shooter',rules,question:null,review:[],
 category:{label:'All clubs',topic_label:'Mixed topics'},difficulty:'easy',is_trial:true,correct:0,total_xp:0,base_xp:0,bonus_xp:0,multiplier:1,
 shootout:{player:0,opponent:0,kicks:{player:0,opponent:0},attempts:[],round:1,next_role:'shooter',winner:null,sudden_death:false}};}
function wav(samples){
 const out=Buffer.alloc(44+samples.length*2);out.write('RIFF');out.writeUInt32LE(out.length-8,4);out.write('WAVEfmt ',8);out.writeUInt32LE(16,16);out.writeUInt16LE(1,20);out.writeUInt16LE(1,22);out.writeUInt32LE(48000,24);out.writeUInt32LE(96000,28);out.writeUInt16LE(2,32);out.writeUInt16LE(16,34);out.write('data',36);out.writeUInt32LE(samples.length*2,40);
 samples.forEach((value,i)=>out.writeInt16LE(Math.round(Math.max(-1,Math.min(1,value))*32767),44+i*2));return out;
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const url=new URL(route.request().url()).pathname;let data={},status=200;
   if(url==='/api/players/me'){data={detail:'Sign in'};status=401;}
   else if(url==='/api/solo/catalog')data=catalog;
   else if(url==='/api/solo/active')data={run:run?{...run,server_now:Date.now()}:null,trial_available:true};
   else if(url==='/api/solo/runs'){start();data=run;}
   else if(url.endsWith('/next')){run.position++;run.phase='ANSWERING';run.role=run.position%2?'shooter':'keeper';run.question=question;run.deadline=Date.now()+120000;data=run;}
   else if(url.endsWith('/answers')){
    run.phase='REVIEW';const keeper=run.role==='keeper';run.correct++;run.total_xp+=10;
    run.review.push({position:run.position,outcome:keeper?'save':'goal',option_id:'0',correct:'0',is_correct:true,text:question.text,explanation:'Manchester City won the title.'});
    run.shootout.next_role=keeper?'shooter':'keeper';data=run;
   }else if(url.endsWith('/leave')){run.phase='ABANDONED';run.shootout.winner='opponent';data=run;}
   else if(url==='/api/solo/runs/sound-test')data=run;
   else {errors.push('Unexpected API '+url);status=404;}
   await route.fulfill({status,json:data===run?{...data,server_now:Date.now()}:data});
  });
  await page.goto(origin+'/penalties');assert.equal(await page.evaluate(()=>PointsAudio.inspect().state),'locked');
  await page.locator('#menu-open').click();await page.waitForFunction(()=>PointsAudio.inspect().state==='running');
  await page.locator('#sound-volume').fill('25');assert.equal(await page.evaluate(()=>PointsAudio.getSettings().volume),.25);
  await page.locator('#menu-drawer [data-sound-toggle]').click();assert.equal(await page.evaluate(()=>PointsAudio.getSettings().enabled),false);
  await page.reload();assert.equal(await page.evaluate(()=>PointsAudio.getSettings().enabled),false);assert.equal(await page.evaluate(()=>PointsAudio.getSettings().volume),.25);
  await page.locator('#menu-open').click();await page.locator('#menu-drawer [data-sound-toggle]').click();await page.waitForFunction(()=>PointsAudio.inspect().state==='running');
  await page.screenshot({path:output+'/sound-menu.png'});await page.locator('#menu-drawer [data-close-dialog]').click();
  await page.evaluate(()=>{window.soundCues=[];const play=PointsAudio.play;PointsAudio.play=name=>{const played=play(name);soundCues.push({name,played,time:performance.now(),caught:PointsStadium.inspect().caught});return played;};});
  await page.setViewportSize({width:320,height:568});await page.locator('#start').click();
  await page.waitForSelector('#stadium-skip:not([hidden])');
  const header=await page.locator('#stadium-controls').boundingBox();
  for(const control of await page.locator('#stadium-controls button:visible').all()){
   const b=await control.boundingBox();assert(b.x>=0&&b.x+b.width<=320&&b.y+b.height<=header.y+header.height+1);
  }
  await page.screenshot({path:output+'/intro-320.png'});await page.locator('#stadium-skip').click();
  await page.locator('#next').click();await page.waitForSelector('#choices button:not([disabled])');await page.locator('#choices button').first().click();
  await page.waitForFunction(()=>!document.getElementById('next').disabled);
  assert.deepEqual(await page.evaluate(()=>soundCues.map(c=>c.name)),['kick','net']);
  await page.locator('#next').click();await page.waitForSelector('#choices button:not([disabled])');await page.locator('#choices button').first().click();
  await page.waitForFunction(()=>!document.getElementById('next').disabled);
  const cues=await page.evaluate(()=>soundCues);assert.deepEqual(cues.map(c=>c.name),['kick','net','kick','catch']);
  assert(cues.every(c=>c.played));assert(cues.at(-1).caught);assert(cues[3].time-cues[2].time>300);
  await page.locator('#stadium-controls [data-sound-toggle]').click();
  assert.equal(await page.evaluate(()=>PointsAudio.inspect().activeVoices),0);assert.equal(await page.evaluate(()=>PointsAudio.play('win')),false);
  await page.locator('#stadium-controls [data-sound-toggle]').click();await page.locator('#leave').click();
  await page.waitForFunction(()=>soundCues.some(c=>c.name==='loss'&&c.played));
  assert.equal(await page.evaluate(()=>soundCues.filter(c=>c.name==='loss').length),1);
  await page.reload();assert.equal(await page.evaluate(()=>PointsAudio.inspect().state),'locked');assert(await page.locator('#summary').isVisible());
  assert.deepEqual(errors,[]);console.log('PASS mobile mute/volume, persistence, kick/catch timing, result cue and silent history');

  // Render the production sound recipes to actual samples without using a
  // speaker or allowing the output device to affect a deterministic check.
  for(const name of ['click','kick','catch','net','win','loss']){
   const sample=await browser.newPage();await sample.setContent('<button>Unlock</button>');
   await sample.evaluate(()=>{
    window.AudioContext=class{
     constructor(){const ctx=new OfflineAudioContext(1,57600,48000);window.renderAudio=()=>ctx.startRendering();this.sampleRate=ctx.sampleRate;this.currentTime=0;this.state='suspended';this.destination=ctx.destination;
      for(const method of ['createGain','createDynamicsCompressor','createBuffer','createBufferSource','createBiquadFilter','createOscillator'])this[method]=ctx[method].bind(ctx);}
     async resume(){this.state='running';}async suspend(){this.state='suspended';}async close(){this.state='closed';}
    };
   });
   await sample.addScriptTag({content:audioScript});await sample.getByRole('button').click();
   const samples=await sample.evaluate(async cue=>{PointsAudio.stop();if(!PointsAudio.play(cue))throw Error('Cue blocked');const buffer=await renderAudio();return [...buffer.getChannelData(0)];},name);
   const peak=samples.reduce((n,x)=>Math.max(n,Math.abs(x)),0),energy=samples.reduce((n,x)=>n+x*x,0);
   assert(peak>.001&&peak<.98,`${name} is silent or clipping: ${peak}`);assert(energy>.0001);
   fs.writeFileSync(output+'/'+name+'.wav',wav(samples));console.log(`PASS rendered ${name}: peak ${peak.toFixed(3)}`);await sample.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
