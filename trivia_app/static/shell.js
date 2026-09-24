/* Native dialogs supply focus trapping and Escape, including on mobile. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  for(const dialog of document.querySelectorAll('.shell-drawer')) {
    dialog.querySelector('[data-close-dialog]').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  }
  $('menu-open').addEventListener('click',()=>$('menu-drawer').showModal());
  // Only go back inside this site. A directly opened invite/result goes home.
  let previous=null;
  try{
    const stored=JSON.parse(sessionStorage.getItem('otd-navigation')||'null');
    const current=location.pathname+location.search;
    previous=stored?.current===current?stored.previous:stored?.current;
    if(previous&&!/^\/(?!\/)/.test(previous))previous=null;
    sessionStorage.setItem('otd-navigation',JSON.stringify({current,previous}));
  }catch{}
  for(const button of document.querySelectorAll('[data-back]'))button.addEventListener('click',()=>{location.href=previous||'/';});
  for(const button of document.querySelectorAll('[data-share-game]'))button.addEventListener('click',async()=>{
    const url=$('game-share-link').value;
    try{if(navigator.share){await navigator.share({title:'ON THE DOT. | Football trivia',url});return;}}catch(e){if(e.name==='AbortError')return;}
    if($('menu-drawer').open)$('menu-drawer').close();$('game-share-dialog').showModal();
  });
  $('game-share-copy').addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText($('game-share-link').value);$('game-share-status').textContent='Game link copied.';}
    catch{$('game-share-link').select();$('game-share-status').textContent='Copy the selected link.';}
  });
})();
