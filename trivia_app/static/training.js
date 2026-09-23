(function () {
    const $ = id => document.getElementById(id);
    const results = window.PointsTrainingResults;
    function element(tag, text, className) {
        const node=document.createElement(tag); if(text!==undefined)node.textContent=text;
        if(className)node.className=className; return node;
    }
    function clearProbe() { probeGeneration++; $('probe-result').hidden=true; }
    function renderProbe(data,model,phrase) {
        const view=results.probe(data);
        $('probe-heading').textContent=view.heading; $('probe-assessment').textContent=view.assessment;
        $('probe-seen').textContent=view.seen;
        $('probe-facts').replaceChildren(...[
            ['Phrase',phrase],['Model suggestion',results.label(data.label)],['Exact-match rules',results.label(data.rule_label)],
            ['Trained categories',data.trained_labels.map(results.label).join(', ')],['Training phrases',String(data.training_phrase_count)]
        ].flatMap(([key,value])=>[element('dt',key),element('dd',value)]));
        $('probe-scores').replaceChildren(...view.scores.map(([name,score])=>{
            const row=element('div',undefined,'training-score'), meter=document.createElement('meter');
            meter.min=0;meter.max=1;meter.value=score;meter.setAttribute('aria-label',results.label(name)+' class score');
            row.append(element('span',results.label(name)),meter,element('span',score.toFixed(3)));return row;
        }));
        if(!view.scores.length)$('probe-scores').textContent='No scores available.';
        $('probe-neighbors').replaceChildren(...data.neighbors.map(n=>element('p',`${n.phrase} | ${results.label(n.label)} | similarity ${n.similarity.toFixed(3)}`)));
        if(!data.neighbors.length)$('probe-neighbors').textContent='No matching training features.';
        $('probe-json').textContent=JSON.stringify({model,phrase,...data},null,2);
        $('probe-result').hidden=false;
    }
    let current = null, saved = null, offset = 0, next = null, inboxNext = 0, generation = 0, listGeneration = 0, probeGeneration = 0, busy = false;
    function status(text,error=false) { $('training-status').textContent=text; $('training-status').classList.toggle('error',error); }
    async function request(path,body) {
        const response=await fetch('/api/query/training'+path,body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
        const data=await response.json();
        if (!response.ok) throw new Error(Array.isArray(data.detail)? data.detail.map(d=>d.msg).join('; '):data.detail||'Request failed');
        return data;
    }
    function controls() {
        $('annotation-save').disabled=busy;
        $('annotation-verify').disabled=busy||!saved||saved.reviewed_at||!$('annotation-confirm').checked;
    }
    function invalidate() { generation++; saved=null; $('annotation-confirm').checked=false; controls(); $('annotation-revision').textContent='Unsaved changes'; }
    function open(row) {
        generation++; current=row; saved=row;
        $('annotation-text').value=row?.query_text||''; $('annotation-text').readOnly=!!row?.example_id;
        $('annotation-phrase').value=row?.phrase||''; $('annotation-label').value=row?.label||'';
        $('annotation-family').value=row?.family_key||''; $('annotation-split').value=row?.split||'train';
        $('annotation-note').value=row?.note||''; $('annotation-confirm').checked=false;
        $('annotation-revision').textContent=row?.revision? `Revision ${row.revision} | ${row.reviewed_at?'Human verified by '+row.reviewed_by:'Draft'}`:'No saved annotation';
        controls();
    }
    function row(text,detail,label,action) {
        const article=document.createElement('article'); article.className='trivia-library-row';
        const content=document.createElement('div'), p=document.createElement('p'), small=document.createElement('small'), button=document.createElement('button');
        p.textContent=text; small.textContent=detail; content.append(p,small); button.type='button'; button.textContent=label;
        button.addEventListener('click',action); article.append(content,button); return article;
    }
    async function loadExamples() {
        const serial=++listGeneration;
        const data=await request('/examples?offset='+offset);
        if(serial!==listGeneration)return;
        const selected=$('annotation-label').value;
        $('annotation-label').replaceChildren(...[['','Choose label'],...Object.entries(data.labels)].map(([value,definition])=>{
            const item=document.createElement('option'); item.value=value; item.textContent=value||definition; item.title=definition; return item;
        }));
        $('annotation-label').value=selected;
        $('training-counts').textContent=data.counts.map(c=>`${c.split}: ${c.verified}/${c.total} verified`).join(' | ')||'No examples';
        $('training-examples').replaceChildren(...data.examples.map(e=>row(e.query_text,`${e.phrase} | ${e.label} | ${e.split} | ${e.family_key} | ${e.reviewed_at?'Verified':'Draft'}`,'Review',()=>{open(e); $('annotation-text').focus();})));
        next=data.next_offset; $('training-prev').disabled=offset===0; $('training-next').disabled=next===null; $('training-page').textContent=`Page ${Math.floor(offset/25)+1}`;
    }
    async function loadInbox(reset=false) {
        if(reset){inboxNext=0;$('training-inbox').replaceChildren();}
        if(inboxNext===null)return;
        const data=await request('/inbox?offset='+inboxNext);
        for(const q of data.queries) $('training-inbox').append(row(q.query_text,q.issues.join('; '),'Annotate',()=>{
            open(null); $('annotation-text').value=q.query_text; $('annotation-note').value='From failed query log #'+q.query_id; $('annotation-phrase').focus();
        }));
        inboxNext=data.next_offset; $('training-inbox-more').hidden=inboxNext===null;
    }
    async function loadModels() {
        const data=await request('/models'),selected=$('probe-model').value;
        $('training-models').replaceChildren(); $('probe-model').replaceChildren();
        for(const m of data.models) {
            const title=`${new Date(m.created_at).toLocaleString('en-GB')} | ${m.model_id.slice(0,8)}`;
            const section=element('section',undefined,'training-evaluation');
            section.append(element('h4',title),element('p',`Training: ${m.report.counts.train} phrases | Categories: ${m.report.classes.map(results.label).join(', ')}`));
            const counts=['validation','test'].map(split=>{const t=results.tally(m,split);return `${split}: ${t.correct}/${t.total} correct`;});
            section.append(element('p',counts.join(' | '),'training-summary'),element('p',m.report.warning+' Not deployed.'));
            const scroll=element('div',undefined,'training-table-scroll'),table=element('table'),head=element('thead'),headRow=element('tr'),body=element('tbody');
            for(const name of ['Split','Phrase','Expected','Model','Result','']){const th=element('th',name);th.scope='col';headRow.append(th);}
            head.append(headRow);table.append(head,body);
            for(const split of ['validation','test'])for(const example of m.evaluation_examples[split]) {
                const correct=example.expected===example.predicted,tr=element('tr');
                tr.append(element('td',split),element('td',example.phrase),element('td',results.label(example.expected)),element('td',results.label(example.predicted)),element('td',correct?'Correct':'Incorrect',correct?'training-correct':'training-incorrect'));
                const action=element('td'),button=element('button','Test phrase');button.type='button';
                button.addEventListener('click',()=>{clearProbe();$('probe-model').value=m.model_id;$('probe-phrase').value=example.phrase;$('probe-phrase').focus();});
                action.append(button);tr.append(action);body.append(tr);
            }
            scroll.append(table);section.append(scroll);
            const details=document.createElement('details'), summary=document.createElement('summary'), pre=document.createElement('pre');
            summary.textContent='Technical evaluation report'; pre.textContent=JSON.stringify({manifest:m.manifest,report:m.report},null,2); details.append(summary,pre);section.append(details);$('training-models').append(section);
            const option=document.createElement('option'); option.value=m.model_id; option.textContent=title; $('probe-model').append(option);
        }
        if(data.models.some(m=>m.model_id===selected))$('probe-model').value=selected;
        if(selected!==$('probe-model').value)clearProbe();
        if(!data.models.length)$('training-models').textContent='No trained models';
        $('probe-submit').disabled=!data.models.length;
    }
    async function refresh() { try { await loadExamples(); await loadInbox(true); await loadModels(); } catch(e){status(e.message,true);} }
    $('training-tab').addEventListener('click',()=>{document.dispatchEvent(new CustomEvent('trivia-view',{detail:'training'}));refresh();});
    $('training-refresh').addEventListener('click',refresh);
    $('annotation-new').addEventListener('click',()=>open(null));
    $('annotation-form').addEventListener('input',invalidate);
    $('annotation-confirm').addEventListener('change',controls);
    $('annotation-form').addEventListener('submit',async event=>{
        event.preventDefault(); if(busy)return; busy=true;controls(); const serial=generation;
        const body={example_id:current?.example_id||null,base_revision:current?.revision||0,query_text:$('annotation-text').value,
            phrase:$('annotation-phrase').value,label:$('annotation-label').value,family_key:$('annotation-family').value,
            split:$('annotation-split').value,note:$('annotation-note').value};
        try { const data=await request('/examples',body); if(serial===generation)open({...body,...data});
            status('Draft saved. Not eligible for training until verified.'); await loadExamples();
        } catch(e){status(e.message,true);} finally{busy=false;controls();}
    });
    $('annotation-verify').addEventListener('click',async()=>{
        if(busy||!saved||!$('annotation-confirm').checked)return;
        busy=true;controls();const serial=generation, annotation=saved;
        try { await request(`/examples/${annotation.annotation_id}/verify`,{confirmed:true});
            if(serial===generation){saved={...annotation,reviewed_at:true};$('annotation-revision').textContent=`Revision ${annotation.revision} | Human verified`;}
            status('Metric phrase verified. No model was trained or deployed.');await loadExamples();
        }catch(e){status(e.message,true);}finally{busy=false;controls();}
    });
    $('training-prev').addEventListener('click',()=>{offset=Math.max(0,offset-25);loadExamples().catch(e=>status(e.message,true));});
    $('training-next').addEventListener('click',()=>{if(next!==null){offset=next;loadExamples().catch(e=>status(e.message,true));}});
    $('training-inbox-more').addEventListener('click',()=>loadInbox().catch(e=>status(e.message,true)));
    for (const id of ['probe-model','probe-phrase']) $(id).addEventListener('input',clearProbe);
    $('model-probe').addEventListener('submit',async event=>{
        event.preventDefault();$('probe-submit').disabled=true;
        clearProbe();const serial=probeGeneration, model=$('probe-model').value, phrase=$('probe-phrase').value;
        try{const data=await request(`/models/${model}/probe`,{phrase});
            if(serial===probeGeneration){renderProbe(data,model,phrase);status('Model test complete. No data changed.');}
        }catch(e){if(serial===probeGeneration)status(e.message,true);}finally{$('probe-submit').disabled=!$('probe-model').value;}
    });
})();
