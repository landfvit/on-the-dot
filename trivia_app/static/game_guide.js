/* Presentation only. Examples are precomputed by the server's shootout engine.
 * Without JavaScript all three remain readable; native radios handle keyboards. */
(() => {
    'use strict';
    const controls=document.querySelector('.guide-scenarios');
    if(!controls)return;
    const inputs=[...controls.querySelectorAll('input')],panels=[...document.querySelectorAll('.guide-example')];
    function show(){const selected=inputs.find(input=>input.checked)?.value;for(const panel of panels)panel.hidden=panel.id!=='example-'+selected;}
    for(const input of inputs)input.addEventListener('change',show);
    document.querySelector('.guide-example-stage').dataset.enhanced='true';controls.hidden=false;show();
})();
