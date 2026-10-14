(() => {
  'use strict';
  const $=id=>document.getElementById(id),page=document.querySelector('.question-workspace'),admin=page.dataset.review==='true';
  const selected=new Set();let rows=[],topics=[],offset=0,total=0,editing=null,reviewing=null,busy=false,createId=null,duelRequest=null;
  const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  function message(id,text=''){const e=$(id);e.textContent=text;e.hidden=!text;}
  async function api(path,body,method='POST'){
    const r=await fetch(path,{credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},method:body?method:'GET',body:body?JSON.stringify(body):undefined});
    const d=await r.json();if(!r.ok){const err=new Error(typeof d.detail==='string'?d.detail:'Check the question and all four answers.');err.status=r.status;throw err;}return d;
  }
  async function action(fn,error='workspace-error'){
    if(busy)return;busy=true;message(error);document.querySelectorAll('.question-dialog button[type=submit]').forEach(b=>b.disabled=true);
    try{await fn();}catch(e){message(error,e.message);}finally{busy=false;document.querySelectorAll('.question-dialog button[type=submit]').forEach(b=>b.disabled=false);syncSelection();}
  }
  function button(text,fn){const b=el('button',text);b.type='button';b.addEventListener('click',fn);return b;}
  function syncSelection(){if(admin)return;$('selected-count').textContent=selected.size;$('create-custom-duel').disabled=busy||!selected.size;}
  function answers(q){const ul=el('ul',undefined,'review-answers');q.options.forEach((text,i)=>{const li=el('li',text,i===q.correct?'correct':'');if(i===q.correct)li.append(el('span','  ✓'));ul.append(li);});return ul;}
  function render(){
    const shown=admin?rows:rows.slice(offset,offset+25);$('question-list').replaceChildren();
    for(const row of shown){
      const q=row.content,article=el('article',undefined,'question-row');
      if(!admin){const box=el('input');box.type='checkbox';box.checked=selected.has(row.submission_id);box.setAttribute('aria-label','Select '+q.question);box.addEventListener('change',()=>{if(box.checked&&selected.size>=100){box.checked=false;message('workspace-error','Select up to 100 questions.');return;}box.checked?selected.add(row.submission_id):selected.delete(row.submission_id);duelRequest=null;syncSelection();});article.append(box);}else article.append(el('span',''));
      const copy=el('div');copy.append(el('h2',q.question));const state=el('span',row.status,'question-state');state.dataset.status=row.status;copy.append(state,el('span',q.difficulty));
      copy.append(el('p','Answer '+q.options[q.correct]));if(admin)copy.append(el('p',row.username));if(row.review_note)copy.append(el('p',row.review_note));
      const actions=el('div',undefined,'question-actions');
      if(admin){actions.append(button(row.status==='pending'?'Review':'View',()=>openReview(row)));}
      else{
        if(row.status!=='approved')actions.append(button('Edit',()=>openEditor(row)));
        if(row.status==='draft')actions.append(button('Submit for review',()=>action(async()=>{await api(`/api/players/questions/${row.submission_id}/submit`,{revision:row.revision});await load();message('workspace-message','Sent for review. You can still use it in a private duel.');})));
      }
      copy.append(actions);article.append(copy);$('question-list').append(article);
    }
    $('page-position').textContent=total?`${offset+1}–${Math.min(offset+25,total)} of ${total}`:'No questions yet';$('page-previous').disabled=offset===0;$('page-next').disabled=offset+25>=total;
    if(!admin)$('library-count').textContent=`${total} ${total===1?'question':'questions'}`;syncSelection();
  }
  async function load(){
    const d=await api(admin?`/api/trivia/community-questions?status=${$('queue-status').value}&offset=${offset}&limit=25`:'/api/players/questions');
    rows=d.questions;total=admin?d.total:rows.length;
    if(offset && offset>=total){offset=Math.max(0,Math.floor((total-1)/25)*25);if(admin)return load();}
    if(!admin){topics=d.topics;$('question-topic').replaceChildren(...topics.map(t=>{const o=el('option',t);o.value=t;return o;}));}render();
  }
  function openEditor(row=null){
    editing=row;createId=crypto.randomUUID();const f=$('question-form');f.reset();message('editor-error');$('editor-heading').textContent=row?'Edit question':'New question';
    if(row){const q=row.content;for(const key of ['question','difficulty','topic','explanation'])f.elements[key].value=q[key]||'';q.options.forEach((s,i)=>f.elements['option'+i].value=s);f.elements.correct.value=String(q.correct);}
    $('question-editor').showModal();f.elements.question.focus();
  }
  $('question-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
    const f=e.target,d=new FormData(f),body={question:d.get('question'),options:[0,1,2,3].map(i=>d.get('option'+i)),correct:Number(d.get('correct')),difficulty:d.get('difficulty'),topic:d.get('topic'),explanation:d.get('explanation')};
    if(editing)body.revision=editing.revision;else body.request_id=createId;
    await api('/api/players/questions'+(editing?'/'+editing.submission_id:''),body,editing?'PUT':'POST');$('question-editor').close();await load();message('workspace-message','Question saved.');
  },'editor-error');});
  function openReview(row){
    reviewing=row;const q=row.content,c=$('review-content');c.replaceChildren(el('h3',q.question),answers(q));
    if(q.explanation)c.append(el('p',q.explanation));if(row.review_note)c.append(el('p',row.review_note));
    $('review-form').reset();$('review-form').hidden=row.status!=='pending';message('review-error');$('question-review').showModal();
  }
  $('review-form').addEventListener('submit',e=>{e.preventDefault();const decision=e.submitter.value;action(async()=>{
    const f=e.target;await api(`/api/trivia/community-questions/${reviewing.submission_id}/review`,{revision:reviewing.revision,decision,note:f.elements.note.value,verified:f.elements.verified.checked});$('question-review').close();await load();message('workspace-message',decision==='approved'?'Published to the public bank.':'Returned to the author with your note.');
  },'review-error');});
  document.querySelectorAll('[data-question-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
  $('page-previous').addEventListener('click',()=>{offset=Math.max(0,offset-25);admin?action(load):render();});$('page-next').addEventListener('click',()=>{offset+=25;admin?action(load):render();});
  if(admin)$('queue-status').addEventListener('change',()=>{offset=0;action(load);});
  else{
    $('new-question').addEventListener('click',()=>openEditor());
    $('bank-fallback').addEventListener('change',()=>{$('fallback-difficulty').hidden=!$('bank-fallback').checked;duelRequest=null;});$('duel-difficulty').addEventListener('change',()=>duelRequest=null);
    $('create-custom-duel').addEventListener('click',()=>action(async()=>{
      duelRequest ||= crypto.randomUUID();const d=await api('/api/friends/rooms',{request_id:duelRequest,difficulty:$('duel-difficulty').value,question_ids:[...selected],bank_fallback:$('bank-fallback').checked});location.assign('/friends/'+encodeURIComponent(d.code));
    }));
  }
  load().catch(e=>{if(e.status===401&&!admin){$('question-signin').hidden=false;$('new-question').disabled=true;document.querySelector('.custom-duel-controls').hidden=true;}else message('workspace-error',e.message);});
})();
