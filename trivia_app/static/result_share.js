/* Result cards are rendered locally from a small public-data snapshot.
 * No question text, answers, account email or private run ID leaves this module.
 * Prepare the PNG before the click: Web Share requires fresh user activation.
 */
(function(root){
  'use strict';
  const colors={background:'#222326',surface:'#2b2d32',text:'#f7f6f2',muted:'#bcbfc8',accent:'#88b04b',line:'#54565f',miss:'#ff6f61'};
  const count=value=>Math.max(0,Math.floor(Number(value)||0));
  function snapshot(run,user,origin){
    const url=new URL('/penalties',origin);
    if(!['https:','http:'].includes(url.protocol))throw new Error('Invalid game URL');
    const shootout=run.shootout;
    const difficulty=['easy','medium','hard'].includes(run.difficulty)?run.difficulty:'easy';
    const total=shootout?run.review.length:count(run.rules.questions);
    const status=run.phase==='ABANDONED'?'Shootout ended':shootout?.winner==='player'?'Shootout won':shootout?.winner==='opponent'?'Opponent wins':'Shootout complete';
    const score=shootout?`${count(shootout.player)} : ${count(shootout.opponent)}`:`${count(run.correct)} / ${total}`;
    return {
      title:'ON THE DOT. | '+status,url:url.href,
      text:`ON THE DOT. · ${difficulty[0].toUpperCase()+difficulty.slice(1)} penalties\n${shootout?score+' · ':''}${count(run.correct)}/${total} correct · ${count(run.total_xp)} ${run.is_trial?'trial XP':'XP'}`,
      status,difficulty,score,total,correct:count(run.correct),xp:count(run.total_xp),trial:Boolean(run.is_trial),
      multiplier:Math.max(1,count(run.multiplier)),winBonus:run.rules.bonus_mode==='win',
      player:String(user?.username||'You').slice(0,24),team:String(user?.club?.name||'').slice(0,80),
      attempts:shootout?['player','opponent'].map(side=>shootout.attempts.filter(a=>a.side===side).map(a=>Boolean(a.goal))):null,
    };
  }
  function draw(data,document){
    const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=630;
    const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Canvas unavailable');
    const text=(value,x,y,size=24,color=colors.text,align='left',max=1104,weight=600)=>{
      value=String(value);ctx.textAlign=align;ctx.fillStyle=color;
      // Fixed card dimensions; long usernames/club names shrink within their
      // own lane rather than pushing the score or neighbouring text around.
      do{ctx.font=`${weight} ${size}px Arial, sans-serif`;if(ctx.measureText(value).width<=max)break;size--;}while(size>12);
      ctx.fillText(value,x,y,max);
    };
    const line=y=>{ctx.fillStyle=colors.line;ctx.fillRect(48,y,1104,1);};
    function ball(x,y,goal){
      ctx.beginPath();ctx.arc(x,y,12,0,Math.PI*2);
      if(goal===undefined){ctx.strokeStyle=colors.line;ctx.lineWidth=2;ctx.stroke();return;}
      ctx.fillStyle=goal?colors.text:colors.miss;ctx.fill();
      ctx.beginPath();for(let i=0;i<5;i++){const angle=-Math.PI/2+i*Math.PI*2/5;const px=x+5*Math.cos(angle),py=y+5*Math.sin(angle);i?ctx.lineTo(px,py):ctx.moveTo(px,py);}ctx.closePath();
      ctx.fillStyle=colors.background;ctx.fill();
    }
    ctx.fillStyle=colors.background;ctx.fillRect(0,0,1200,630);
    text('ON THE DOT.',48,80,38,colors.text,'left',750,800);
    text(data.difficulty.toUpperCase(),1152,75,20,colors.accent,'right');
    text(data.status.toUpperCase(),600,144,26,colors.accent,'center');line(180);
    text(data.player,246,270,28,colors.text,'center',340,700);
    if(data.team)text(data.team,246,300,19,colors.muted,'center',340,400);
    text('Opponent',954,270,28,colors.text,'center',340,700);
    text(data.score,600,312,86,colors.text,'center',340,800);
    if(data.attempts)data.attempts.forEach((attempts,side)=>{
      const total=Math.max(5,attempts.length),indices=Array.from({length:total},(_,i)=>i).filter(i=>total<=7||i<5||i>=total-2);
      const center=side?954:246;
      indices.forEach((index,i)=>ball(center+(i-(indices.length-1)/2)*34,350,attempts[index]));
    });
    text(`${data.total} ${data.attempts?(data.total===1?'penalty':'penalties'):(data.total===1?'question':'questions')}`,600,359,18,colors.muted,'center');line(393);
    const metrics=[[`${data.correct} / ${data.total}`,'CORRECT ANSWERS'],[data.xp,data.trial?'TRIAL XP (NOT SAVED)':'XP EARNED'],[`${data.multiplier}x`,data.winBonus?'WIN MULTIPLIER':'BONUS MULTIPLIER']];
    metrics.forEach(([value,label],i)=>{const x=246+i*354;text(value,x,464,42,colors.text,'center');text(label,x,500,15,colors.muted,'center',320);});
    line(547);text(data.url,48,592,20,colors.accent,'left',870,400);text('PLAY PENALTIES',1152,592,17,colors.text,'right',230);
    return canvas;
  }
  async function prepare(run,user,origin){
    const data=snapshot(run,user,origin),canvas=draw(data,root.document);
    const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('Image export failed')),'image/png'));
    const file=new File([blob],'on-the-dot-result.png',{type:'image/png'}),imageUrl=URL.createObjectURL(blob);
    let disposed=false;
    return {data,file,imageUrl,dispose(){if(!disposed){URL.revokeObjectURL(imageUrl);disposed=true;}}};
  }
  async function share(card,navigator){
    if(!navigator.share||!navigator.canShare?.({files:[card.file]}))return 'fallback';
    try{
      await navigator.share({title:card.data.title,text:card.data.text,url:card.data.url,files:[card.file]});
      return 'shared';
    }catch(error){if(error.name==='AbortError')return 'cancelled';throw error;}
  }
  const api={snapshot,draw,prepare,share};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.PointsResultShare=api;
})(globalThis);
