const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const script=fs.readFileSync(require('node:path').join(__dirname,'../trivia_app/static/audio.js'),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup({stored=null,supported=true,broken=false}={}){
 const events={},windowEvents={},contexts=[],storage=new Map(stored?[['onthedot.audio',stored]]:[]),sources=[];
 const param=()=>({value:0,setValueAtTime(){},exponentialRampToValueAtTime(){},setTargetAtTime(value){this.value=value;}});
 const node=()=>({connect(){},disconnect(){}});
 class Audio{
  constructor(){if(broken)throw Error('Audio unavailable');this.state='suspended';this.sampleRate=48000;this.currentTime=10;this.destination={};contexts.push(this);}
  async resume(){this.state='running';}async suspend(){this.state='suspended';}async close(){this.state='closed';}
  createGain(){return {...node(),gain:param()};}
  createDynamicsCompressor(){return {...node(),threshold:param(),knee:param(),ratio:param(),attack:param(),release:param()};}
  createBuffer(_channels,length){return {getChannelData:()=>new Float32Array(length)};}
  createBiquadFilter(){return {...node(),frequency:param(),Q:param()};}
  source(){const n={...node(),starts:[],stops:[],start(t){this.starts.push(t);},stop(t){this.stops.push(t);}};sources.push(n);return n;}
  createBufferSource(){return this.source();}createOscillator(){const source=this.source();source.frequency=param();return source;}
 }
 const doc={hidden:false,querySelectorAll:()=>[],addEventListener(name,fn){(events[name]??=[]).push(fn);}};
 const win={AudioContext:supported?Audio:undefined,addEventListener(name,fn){(windowEvents[name]??=[]).push(fn);}};
 vm.runInNewContext(script,{window:win,document:doc,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)}});
 return {audio:win.PointsAudio,doc,contexts,sources,storage,
   emit(name,event={}){for(const fn of events[name]||[])fn(event);},
   emitWindow(name,event={}){for(const fn of windowEvents[name]||[])fn(event);}};
}
test('audio is locked until a real gesture; blocked cues are not queued',async()=>{
 const s=setup();assert.equal(s.contexts.length,0);assert.equal(s.audio.play('kick'),false);
 s.emit('pointerdown',{isTrusted:false});await flush();assert.equal(s.contexts.length,0);
 s.emit('pointerdown',{isTrusted:true});await flush();assert.equal(s.contexts.length,1);assert.equal(s.sources.length,0);
 assert.equal(s.audio.play('kick'),true);assert.equal(s.sources.length,2);
});
test('every requested cue has a bounded local recipe and ended voices disconnect',async()=>{
 for(const name of ['click','kick','catch','net','win','loss']){
  const s=setup();s.emit('keydown',{isTrusted:true});await flush();
  assert.equal(s.audio.play(name),true,name);assert(s.audio.inspect().activeVoices>0);
  for(const source of s.sources){assert(source.starts[0]>=10);assert(source.stops[0]<11.1);source.onended?.();}
  assert.equal(s.audio.inspect().activeVoices,0);
 }
});
test('mute cancels scheduled notes and stores independent device settings',async()=>{
 const s=setup();s.emit('pointerdown',{isTrusted:true});await flush();s.audio.play('win');
 s.audio.setEnabled(false);assert.equal(s.audio.inspect().activeVoices,0);assert.equal(s.audio.play('catch'),false);
 assert.equal(JSON.parse(s.storage.get('onthedot.audio')).enabled,false);
 s.audio.setVolume(.25);const reloaded=setup({stored:s.storage.get('onthedot.audio')});
 assert.equal(reloaded.audio.getSettings().volume,.25);assert.equal(reloaded.audio.getSettings().enabled,false);
 s.audio.setEnabled(true);assert.equal(s.audio.play('click'),true);
});
test('volume zero is silent; unmute restores an audible volume; invalid input is ignored',async()=>{
 const s=setup();s.emit('pointerdown',{isTrusted:true});await flush();
 s.audio.setVolume(0);assert.equal(s.audio.play('win'),false);s.audio.setEnabled(true);assert.equal(s.audio.getSettings().volume,.5);
 s.audio.setVolume(9);assert.equal(s.audio.getSettings().volume,1);s.audio.setVolume(NaN);assert.equal(s.audio.getSettings().volume,1);
});
test('rapid clicks are bounded; disabled and synthetic clicks make no sound',async()=>{
 const s=setup();s.emit('pointerdown',{isTrusted:true});await flush();
 const control={disabled:false,closest:()=>null,getAttribute:()=>null},event={isTrusted:true,target:{closest:()=>control}};
 for(let i=0;i<100;i++)s.emit('click',event);assert.equal(s.sources.length,1);
 s.contexts[0].currentTime+=1;control.disabled=true;s.emit('click',event);assert.equal(s.sources.length,1);
 control.disabled=false;s.emit('click',{...event,isTrusted:false});assert.equal(s.sources.length,1);
});
test('backgrounding cancels sound and resumption needs a new gesture',async()=>{
 const s=setup();s.emit('pointerdown',{isTrusted:true});await flush();s.audio.play('win');
 s.doc.hidden=true;s.emit('visibilitychange');assert.equal(s.audio.inspect().activeVoices,0);assert.equal(s.audio.play('loss'),false);
 s.doc.hidden=false;s.emit('visibilitychange');assert.equal(s.audio.play('kick'),false);
 s.emit('keydown',{isTrusted:true});await flush();assert.equal(s.audio.play('kick'),true);
 s.emitWindow('pagehide');assert.equal(s.audio.inspect().state,'locked');assert.equal(s.audio.inspect().activeVoices,0);
});
test('cross-tab muting stops current sound',async()=>{
 const s=setup();s.emit('pointerdown',{isTrusted:true});await flush();s.audio.play('win');
 s.storage.set('onthedot.audio',JSON.stringify({enabled:false,volume:.1}));s.emitWindow('storage',{key:'onthedot.audio'});
 assert.equal(s.audio.getSettings().enabled,false);assert.equal(s.audio.inspect().activeVoices,0);
});
test('missing audio support, constructor failure and malformed storage never block the app',async()=>{
 for(const options of [{supported:false},{broken:true},{stored:'invalid-json'}]){
  const s=setup(options);s.emit('pointerdown',{isTrusted:true});await flush();assert.doesNotThrow(()=>s.audio.play('catch'));
  assert.equal(s.audio.play('not-a-cue'),false);
 }
});
