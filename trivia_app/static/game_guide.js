/* Presentation only. Examples are precomputed by the server's shootout engine.
 * Without JavaScript all three remain readable; native radios handle keyboards. */
(() => {
    'use strict';
    const controls=document.querySelector('.guide-scenarios');
    if(!controls)return;
    const inputs=[...controls.querySelectorAll('input')],panels=[...document.querySelectorAll('.guide-example')];
    function show(){
        const selected=inputs.find(input=>input.checked)?.value;
        for(const panel of panels){
            const inactive=panel.id!=='example-'+selected;
            // Shared grid tracks take the tallest actual example, without an
            // oversized fixed spacer. Inactive text stays out of the a11y tree.
            panel.classList.toggle('is-inactive',inactive);panel.inert=inactive;
            panel.setAttribute('aria-hidden',String(inactive));
        }
    }
    for(const input of inputs)input.addEventListener('change',show);
    document.querySelector('.guide-example-stage').dataset.enhanced='true';controls.hidden=false;show();
})();
