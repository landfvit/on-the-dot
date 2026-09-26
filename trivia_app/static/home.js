/* Rules tabs only. Scores, accounts and game eligibility stay server-owned. */
(() => {
  const modes={
    solo:{steps:[['Shoot.', 'Answer given question correctly to score. Wrong answers or missing the timer result in a miss!'],['Save.',"You are the keeper now. Correct answers lead to a save, incorrect or late ones let the ball in!"],['Win!',"Five penalties each, unless it's decided early. Sudden death with equal kicks for both sides if the game is tied!"]],note:'An account is not required to play Solo.'},
    daily:{steps:[['Shoot.','Every correct answer scores a goal. You always take the penalty, with 15 seconds to answer.'],['Keep going.','You have three lives. Wrong answers and timeouts cost one life. Score as many goals as you can.'],['Set your record.','Your first attempt each day counts towards your all-time high score. Keep playing in practice after that.']],note:'An account is required. Your scoring attempt resets at 00:00 UTC.'},
    duel:{steps:[['Invite a friend.','Create a duel and share the invitation link. You can both join without an account.'],['Go head-to-head.','Answer the same question in 15 seconds. Correct beats incorrect and faster wins.'],['Play fair.','Replay the kick if both answers are wrong or if the time difference is within 150 ms.']],note:'XP and other stats are not gained or affected by Friend Duel. This helps keep the integrity of the Leaderboard.'}
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
