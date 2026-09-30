/* Presentation only: never changes answers, deadlines, score or game state.
 * Fit long bank questions to the reserved slot, not to the viewport width.
 */
(() => {
    'use strict';
    const panel=document.getElementById('question-panel');
    if(!panel)return;
    const title=document.getElementById('question-title');
    const choices=document.getElementById('choices');
    const feedback=document.getElementById('feedback');
    const expand=document.getElementById('feedback-expand');
    const dialog=document.getElementById('feedback-dialog');
    const compact=matchMedia('(max-width:800px), (max-height:540px) and (max-width:1100px)');
    let pending=0;

    function fit(element,minimum) {
        element.style.removeProperty('font-size');
        let size=parseFloat(getComputedStyle(element).fontSize);
        // Only shrink when actual text overflows; short questions keep the
        // normal font. Half-pixel steps avoid a noticeable typography jump.
        while(size>minimum&&(element.scrollHeight>element.clientHeight+1||element.scrollWidth>element.clientWidth+1)) {
            size=Math.max(minimum,size-.5);element.style.fontSize=`${size}px`;
        }
    }
    function layout() {
        pending=0;
        const active=(document.body.classList.contains('stadium-inline')||compact.matches&&document.body.classList.contains('stadium-playing')&&!document.body.classList.contains('stadium-ending'))&&!panel.hidden;
        title.style.removeProperty('font-size');
        for(const button of choices.children)button.style.removeProperty('font-size');
        expand.hidden=true;
        if(!active)return;
        fit(title,12);
        for(const button of choices.children)fit(button,12);
        // A long answer can be opened in full without shifting any game
        // controls. The question and answer options themselves are never cut.
        expand.hidden=feedback.scrollHeight<=feedback.clientHeight+1;
    }
    function schedule(){if(!pending)pending=requestAnimationFrame(layout);}
    new ResizeObserver(schedule).observe(panel);
    const contentChanges=new MutationObserver(schedule);
    for(const element of [title,choices,feedback])contentChanges.observe(element,{childList:true,subtree:true,characterData:true});
    new MutationObserver(schedule).observe(document.body,{attributes:true,attributeFilter:['class']});
    compact.addEventListener('change',schedule);
    document.fonts.ready.then(schedule);
    expand.addEventListener('click',()=>{
        document.getElementById('feedback-full').textContent=feedback.textContent;
        dialog.showModal();
    });
    document.getElementById('feedback-close').addEventListener('click',()=>dialog.close());
    // End/restart/navigation may change the question while the dialog is open.
    new MutationObserver(()=>{if(dialog.open)dialog.close();}).observe(feedback,{childList:true,characterData:true,subtree:true});
    schedule();
})();
