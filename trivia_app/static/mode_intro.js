/* First-use rules are local to this browser. No match is created until the
 * player confirms, so reading the rules never spends their answer time. */
(() => {
  const dialog=document.getElementById('mode-intro');if(!dialog)return;
  const copy={
    solo:{title:'Solo penalties',items:['You have 15 seconds. Answer correctly to score or save. Wrong or late answers lose the penalty.','Five kicks each, then sudden death if tied. An unbeatable lead ends it early.','Correct answers earn XP. Wins add a bonus. Guest progress is not saved.']},
    daily:{title:'Daily Challenge',items:['You only shoot, with 15 seconds per answer. Wrong or late answers cost a life. Three mistakes end the run.','Your first attempt each day counts, even if you quit. Later runs are practice. Rankings use your best score.','Mixed difficulty. Correct answers earn XP, including practice, with no win bonus. Questions reset weekly.']},
    friend:{title:'Friend Duel',items:['Share a link. No account needed. Both press Ready, then answer the same question in 15 seconds.','A correct answer wins the penalty. If both are correct, faster wins. Both wrong or correct within 0.15 seconds means a replay.','Five kicks each, then sudden death if tied. No XP or rating. Forfeiting or a long disconnect loses the duel.']}
  };
  let pending=null;
  function show(mode,force=false){
    if(pending)return pending;
    const key=(mode==='daily'?'otd-rules-v2-':'otd-rules-v1-')+mode;
    try{if(!force&&localStorage.getItem(key))return Promise.resolve(true);}catch{}
    const rules=copy[mode]||copy.solo;
    dialog.querySelector('.mode-intro-scenes').hidden=mode==='daily';
    document.getElementById('mode-intro-title').textContent=rules.title;
    document.getElementById('mode-intro-rules').replaceChildren(...rules.items.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    pending=new Promise(resolve=>{
      dialog.returnValue='';dialog.showModal();
      // Reading begins at the title, not at an automatically outlined Back.
      document.getElementById('mode-intro-title').focus({preventScroll:true});
      dialog.addEventListener('close',()=>{const accepted=dialog.returnValue==='play';if(accepted)try{localStorage.setItem(key,'1');}catch{}pending=null;resolve(accepted);},{once:true});
    });return pending;
  }
  globalThis.PointsModeIntro={show};
})();
