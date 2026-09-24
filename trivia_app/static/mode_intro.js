/* First-use rules are local to this browser. No match is created until the
 * player confirms, so reading the rules never spends their answer time. */
(() => {
  const dialog=document.getElementById('mode-intro');if(!dialog)return;
  const copy={
    solo:{title:'Solo penalties',items:['15 seconds per answer. Correct when shooting: goal. Correct when defending: save.','Five penalties each. A lead can win early; a tie goes to paired sudden death.','Earn 10 / 20 / 30 XP per correct Easy / Medium / Hard answer. Winning multiplies XP by 2x / 3x / 4x. Guest XP is not saved.']},
    daily:{title:'Daily Challenge',items:['Registered players share a daily pool: 10 Easy, 20 Medium and 20 Hard questions. Each answer has 15 seconds.','Play a normal shootout. Win it, or use up your remaining daily pool, to earn one Daily win. Maximum one win per UTC day.','Correct answers earn 10 / 20 / 30 XP, without a win multiplier. Opened questions stay out of later games until the weekly reset.']},
    friend:{title:'Friend Duel',items:['Share an invitation link. No account needed. Both players press Ready, then answer the same question in 15 seconds.','Only you are correct: you win that penalty. Both wrong: replay. Both correct: the faster answer wins; within 0.15 seconds: replay.','Take turns shooting and defending, five kicks each, then paired sudden death. No XP, rating or Solo stats. Forfeiting or a prolonged disconnect loses the duel.']}
  };
  let pending=null;
  function show(mode,force=false){
    if(pending)return pending;
    const key='otd-rules-v1-'+mode;
    try{if(!force&&localStorage.getItem(key))return Promise.resolve(true);}catch{}
    const rules=copy[mode]||copy.solo;
    document.getElementById('mode-intro-title').textContent=rules.title;
    document.getElementById('mode-intro-rules').replaceChildren(...rules.items.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    pending=new Promise(resolve=>{
      dialog.returnValue='';dialog.showModal();
      dialog.addEventListener('close',()=>{const accepted=dialog.returnValue==='play';if(accepted)try{localStorage.setItem(key,'1');}catch{}pending=null;resolve(accepted);},{once:true});
    });return pending;
  }
  globalThis.PointsModeIntro={show};
})();
