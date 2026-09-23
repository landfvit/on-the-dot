/* Sdileny VIZUALNI plan kopu. O vysledku rozhoduje vyhradne server.
 * Stejny identifikator kola dava obema PvP klientum stejny smer v prostoru.
 * side: -1/0/+1 = leva/stred/prava z pohledu strelce, high = pod brevno.
 * Bez identifikatoru se pouzije nahoda, napr. pri nahledu v editoru.
 */
(function (root) {
    'use strict';
    const zones = Object.freeze([
        {id:'low-left',side:-1,high:false}, {id:'low-center',side:0,high:false},
        {id:'low-right',side:1,high:false}, {id:'high-left',side:-1,high:true},
        {id:'high-center',side:0,high:true}, {id:'high-right',side:1,high:true},
    ].map(Object.freeze));
    function plan(outcome, key, random = Math.random) {
        if (!['goal','save','miss','replay'].includes(outcome)) return null;
        if (key !== undefined) {
            // FNV + avalanche: sousedni cisla kol nesmi vytvaret cyklicky vzor.
            let state = 2166136261;
            for (const char of `${key}:${outcome}`) state = Math.imul(state ^ char.charCodeAt(0), 16777619);
            random = () => {
                state += 0x6d2b79f5;
                let t = Math.imul(state ^ state >>> 15, 1 | state);
                t ^= t + Math.imul(t ^ t >>> 7, 61 | t);
                return ((t ^ t >>> 14) >>> 0) / 4294967296;
            };
        }
        const pick = list => list[Math.min(list.length-1, Math.floor(random()*list.length))];
        const target = pick(zones);
        // Pri golu brankar voli opacnou STRANU, ne pouze jinou vysku.
        // Pro stredovou strelu vybira levy/pravy roh; pri save presne cil mice.
        const keeper = outcome === 'save' ? target : pick(zones.filter(z => target.side ? z.side === -target.side : z.side !== 0));
        return Object.freeze({outcome,target,keeper});
    }
    const api = Object.freeze({zones,plan});
    root.PenaltyShots = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
