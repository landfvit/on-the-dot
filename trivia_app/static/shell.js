/* Native dialogs supply focus trapping and Escape, including on mobile. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  for(const dialog of document.querySelectorAll('.shell-drawer')) {
    dialog.querySelector('[data-close-dialog]').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  }
  $('menu-open').addEventListener('click',()=>$('menu-drawer').showModal());
})();
