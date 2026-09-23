/* Analyticke pohyby v metrech a sekundach. Nezavisi na FPS ani hernim vysledku.
 * Gravitace je kladna; rychlost smerem vzhuru je kladna. Zadny Euleruv krok,
 * takze uspani zalozky nezpusobi propadnuti mice pod travnik.
 */
export function ballistic(height, velocity, seconds, gravity=9.81) {
    return height + velocity*seconds - .5*gravity*seconds*seconds;
}

// Dopad, maly odskok a klid. Kazdy odraz ztrati energii (restitution < 1).
export function bounceHeight(height, velocity, seconds, floor, gravity=9.81, restitution=.22) {
    let y=height,v=velocity,t=Math.max(0,seconds);
    for(let bounce=0;bounce<8;bounce++) {
        const impact=(v+Math.sqrt(v*v+2*gravity*Math.max(0,y-floor)))/gravity;
        if(t<impact)return Math.max(floor,ballistic(y,v,t,gravity));
        t-=impact;v=Math.abs(v-gravity*impact)*restitution;y=floor;
        if(v<.08)return floor;
    }
    return floor;
}
