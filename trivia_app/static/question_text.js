/* Presentation only: never rewrite stored questions, answer IDs or scoring. */
(() => {
    'use strict';
    const normalize=value=>value.normalize('NFKC').replace(/[\u2018\u2019]/g,"'").replace(/\s+/g,' ').trim().toLowerCase();
    function text(question){
        const original=question?.text||'';
        if(!/^(which|who|what|where|when|how)\b/i.test(original))return original;
        const options=[...new Set((question.options||[]).map(o=>normalize(o.text||'')).filter(Boolean))].sort((a,b)=>b.length-a.length);
        // Remove only a complete list made from the actual answer options.
        // A colon introducing a clue, score or extra context stays untouched.
        for(let colon=original.indexOf(':');colon!==-1;colon=original.indexOf(':',colon+1)){
            let rest=normalize(original.slice(colon+1)).replace(/\?$/,'').trim();
            const matched=new Set();
            while(rest){
                const option=options.find(o=>rest.startsWith(o));if(!option)break;
                matched.add(option);rest=rest.slice(option.length).trim();
                if(!rest&&matched.size>=2)return original.slice(0,colon).trim().replace(/\?$/,'')+'?';
                const separator=rest.match(/^(?:[,;]\s*(?:(?:or|and)\s+)?|(?:or|and)\s+|[\/|]\s*)/);
                if(!separator)break;
                rest=rest.slice(separator[0].length);if(!rest)break;
            }
        }
        return original;
    }
    globalThis.PointsQuestion={text};
})();
