/* Jediny vizualni renderer je Three.js. Adapter zachovava male rozhrani
 * hernich controlleru, ale neobsahuje SVG, 2D animace ani vlastni casovac.
 * Autoritativni vysledek pochazi ze serveru; zde se losuje jen smer kopu.
 */
(function () {
    'use strict';
    function reset() { window.PointsStadium?.reset(); }
    function shot(outcome,key) {
        const plan=globalThis.PenaltyShots.plan(outcome,key);
        if(!plan)return;
        reset();return window.PointsStadium?.shot(outcome,plan);
    }
    window.PenaltyScene={shot,reset};
})();
