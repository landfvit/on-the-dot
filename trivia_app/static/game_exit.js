/* Leaving a game forfeits it. Visibility changes alone are not an exit: the
 * player may be sharing an invitation or switching tabs. */
(() => {
  'use strict';
  const key='points.pending-game-exits.v1';
  const valid=path=>typeof path==='string'&&/^\/api\/(?:(?:solo|daily)\/runs|friends\/rooms)\/[A-Za-z0-9_-]+\/leave$/.test(path);
  let memory=[];
  function pending(){
    try{const value=JSON.parse(localStorage.getItem(key)||'[]');if(Array.isArray(value))return value.filter(valid).slice(-64);}catch{}
    return memory;
  }
  function save(paths){
    memory=[...new Set(paths)];
    try{if(memory.length)localStorage.setItem(key,JSON.stringify(memory));else localStorage.removeItem(key);}catch{}
  }
  const remember=path=>save([...pending(),path]);
  const forget=path=>save(pending().filter(value=>value!==path));
  const accepted=response=>response.ok||[401,403,404,410].includes(response.status);
  function leave(path){
    remember(path);
    // A queued beacon is not a delivery receipt. Keep the outbox until the
    // next visit confirms it, before looking up any resumable game.
    try{if(navigator.sendBeacon?.(path))return;}catch{}
    try{fetch(path,{method:'POST',credentials:'same-origin',keepalive:true})
      .then(response=>{if(accepted(response))forget(path);}).catch(()=>{});}catch{}
  }
  async function flush(){
    for(const path of pending()){
      try{
        const response=await fetch(path,{method:'POST',credentials:'same-origin',keepalive:true});
        if(!accepted(response))throw new Error('Exit not confirmed');
        forget(path);
      }catch{throw new Error('Could not close your previous game. Reload to retry.');}
    }
  }
  function bind(onExit=()=>{}){
    let active=null,closed=false;
    window.addEventListener('pagehide',()=>{
      if(closed)return;
      closed=true;onExit();
      if(active)leave(active);
    });
    // Back/Forward cache must not restore a question whose match was forfeited.
    window.addEventListener('pageshow',event=>{if(event.persisted&&closed)location.reload();});
    return {
      flush,
      get closed(){return closed;},
      watch(path){
        const next=valid(path)?path:null;
        // Some browsers destroy tabs without pagehide. Journal the open match
        // now, not only during unload. A fresh game page closes that match
        // before loading /active, including after a process kill or crash.
        if(!closed){
          if(active&&active!==next)forget(active);
          if(next)remember(next);
        }
        // Also close a just-created game if its response arrives during exit.
        if(closed&&next&&next!==active)leave(next);
        active=next;
      },
    };
  }
  globalThis.PointsGameExit={bind};
})();
