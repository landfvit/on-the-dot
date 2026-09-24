/* Rules tabs only. Scores, accounts and game eligibility stay server-owned. */
(() => {
  const modes={
    solo:{steps:[['Take your shot.','Get the answer right to score. A wrong answer is saved. Run out of time and you miss.'],['Make the save.',"Now you're in goal. A correct answer saves their penalty. A wrong answer or timeout lets it in."],['Win the shootout.',"Five penalties each, unless it's decided early. Tied? Sudden death, with equal kicks for both sides."]],note:'Play Solo as a guest. An account saves your XP and record.'},
    daily:{steps:[['Sign in.','Your account unlocks Daily Challenge. A fresh shared question pool arrives at 00:00 UTC.'],['Face the challenge.','Play the usual shootout. Correct answers earn XP for their difficulty, without a win multiplier.'],['Chase a Daily win.','Win the shootout or use up your remaining daily pool before a winner is decided. At most one Daily win per UTC day.']],note:'Daily wins are tracked separately from Solo wins. An account is required.'},
    duel:{steps:[['Invite a friend.','Create a duel and share the invitation link. You can both join without an account.'],['Go head-to-head.','Answer the same question in 15 seconds. Correct beats incorrect; if both are correct, faster wins.'],['Keep it fair.','Both wrong, or correct answers less than 150 ms apart? Replay the kick. No XP, rating or streak credit.']],note:'Five kicks each, with early finishes and paired sudden death. Forfeiting loses the duel.'}
  };
  const panel=document.getElementById('rules-panel'),tablist=document.querySelector('.rule-tabs');
  if(!panel||!tablist)return;
  const tabs=[...tablist.querySelectorAll('[role=tab]')],steps=[...panel.querySelectorAll('li')];
  tablist.hidden=false;
  function activate(tab,focus=false){
    const content=modes[tab.dataset.mode];
    for(const item of tabs){const selected=item===tab;item.setAttribute('aria-selected',String(selected));item.tabIndex=selected?0:-1;}
    panel.setAttribute('aria-labelledby',tab.id);
    steps.forEach((step,i)=>{step.querySelector('h3').textContent=content.steps[i][0];step.querySelector('p').textContent=content.steps[i][1];});
    document.getElementById('mode-note').textContent=content.note;if(focus)tab.focus();
  }
  tabs.forEach((tab,index)=>{
    tab.addEventListener('click',()=>activate(tab));
    tab.addEventListener('keydown',e=>{
      const next={ArrowRight:(index+1)%tabs.length,ArrowLeft:(index+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1}[e.key];
      if(next!==undefined){e.preventDefault();activate(tabs[next],true);}
    });
  });
})();
