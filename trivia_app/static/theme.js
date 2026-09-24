/* Apply before CSS paints: a saved choice wins, otherwise follow the device.
 * This preference is local to the device, not part of player/game state. */
(() => {
  'use strict';
  const key='onthedot.theme',root=document.documentElement,system=matchMedia('(prefers-color-scheme: dark)');
  let preference=null;
  const read=()=>{try{const value=localStorage.getItem(key);return ['light','dark'].includes(value)?value:null;}catch{return null;}};
  function sync(){
    const dark=root.dataset.theme==='dark';
    for(const button of document.querySelectorAll('[data-theme-toggle]')){
      const label=dark?'Switch to light mode':'Switch to dark mode';
      button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(dark));
      button.querySelector('img').src='/trivia-assets/icons/'+(dark?'sun':'moon')+'.svg';
    }
  }
  function apply(){
    const theme=preference||(system.matches?'dark':'light');root.dataset.theme=theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content',theme==='dark'?'#191c1a':'#f6f3eb');
    sync();window.dispatchEvent(new CustomEvent('points-theme',{detail:{theme}}));
  }
  preference=read();apply();
  document.addEventListener('DOMContentLoaded',sync,{once:true});
  document.addEventListener('click',event=>{
    if(!event.target.closest('[data-theme-toggle]'))return;
    preference=root.dataset.theme==='dark'?'light':'dark';
    try{localStorage.setItem(key,preference);}catch{/* In-memory choice still works. */}
    apply();
  });
  system.addEventListener('change',()=>{if(!preference)apply();});
  window.addEventListener('storage',event=>{if(event.key===key||event.key===null){preference=read();apply();}});
})();
