/* Rules tabs only. Scores, accounts and game eligibility stay server-owned. */
(() => {
  const modes={
    solo:{steps:[['Shoot','Answer correctly to score. Wrong or late answers miss.'],['Save','Answer correctly to save. Wrong or late answers concede.'],['Shootout','Five kicks each, then sudden death if tied.']],note:'No account needed.'},
    daily:{steps:[['Shoot','Answer correctly to score. You have 15 seconds.'],['Three lives','Wrong or late answers cost a life. Lose all three and the run ends.'],['Daily score','Your first attempt each day counts towards your best score. Later runs are practice.']],note:'Account required.'},
    duel:{steps:[['Invite','Share a duel link. No account needed.'],['Answer','You get the same question. A correct answer wins the penalty. If both are correct, faster wins.'],['Replay','Both wrong means a replay. So do correct answers within 0.15 seconds of each other.']],note:'No XP, rating or changes to Solo stats.'}
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
