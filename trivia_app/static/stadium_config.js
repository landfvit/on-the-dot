/* V6: zde men vzhled, rozmery a casy. X=delka, Y=vyska, Z=sirka (metry).
 * Predloha stadion_penalty_v6.html zustala v Downloads beze zmeny.
 * V6_WORLD obsahuje vizualni nastaveni predlohy, STADIUM aplikacni kameru a kop.
 */
export const V6_WORLD = {
  duration: 8.4,
  maxPixelRatio: 1.75,
  outlineOnly: false, // Plne tribuny zakryvaji zadni konstrukci i behem rozostreni.
  pitchMarkings: { width: 0.22, elevation: 0.012, centreSpotRadius: 0.30 }, // skutečná šířka pásu, nikoli 1px WebGL line
  ground: { turfY: -0.025, tunnelFloorY: 0 },
  tunnel: {
    halfWidth: 4.25, height: 5.4, startZ: 40, endZ: 80,
    lightSpacing: 6, lightWidth: 2.4, lightDepth: .10, edgeWidth: .045,
  }, // Minimalisticke stropni pruhy a sirka hran sten v metrech.
  approach: { turnStartZ: 12 }, // rovně až 22 m ZA postranní čáru, potom oblouk k bráně
  focus: { duration: 1.65 }, // Plynule rozostreni pozadi az po dojezdu kamery, bez mizení geometrie.
  penalty: {
    spotX: 41.5,
    goalX: 52.5,
    ballRadius: 0.17, // záměrně mírně zvětšené pro čitelnost herního míče
    cameraBehind: 4.6,
    cameraHeight: 1.75,
    shotDuration: 2.2, // Let + doskok brankare + utlumeni mice na zemi.
  },
  colors: {
    background: 0x222326,
    outline: 0x92a8d1,
    bright: 0xf7f6f2,
    accent: 0x88b04b,
    pitch: 0x88b04b, // Exact supplied green; the second tone is the mowing stripe.
    pitchDark: 0x789c42,
    stands: 0x34363b,
    tunnel: 0x2b2d32,
    shirt: 0x6f2c91,
    shirtTrim: 0xf7cac9,
    shorts: 0x222326,
    gloves: 0xf7f6f2,
    gloveCuffs: 0x92a8d1,
    boots: 0x191a1e,
    skin: 0xd7a17d,
    hair: 0x302922,
    ballWhite: 0xf7f6f2,
    ballBlack: 0x191a1e,
  },
};

export const STADIUM = {
    introMs: (V6_WORLD.duration + V6_WORLD.focus.duration) * 1000,
    focusMs: V6_WORLD.focus.duration * 1000,
    roleChangeMs: 1800, // Plynuly oblouk od puntiku do brany a zpet.
    outroMs: 6200, // Navrat detailu, vylet nad stred, spolecny fade vysledku.
    runUpMs: 700, // Rozbeh soupere pred kontaktem s micem.
    keeperHoldMs: 800, // Cas navic pro zretelne ukazani mice v rukavicich.
    // Contiguous samples (radius=1) prevent comb-like copies of bright seat
    // edges. Increase downsample for a softer background, not sample spacing.
    backgroundBlur: { downsample:6, radius:1 },
    shotMs: V6_WORLD.penalty.shotDuration * 1000,
    maxPixelRatio: V6_WORLD.maxPixelRatio,
    pitch: {length: 105, width: 68},
    goal: {width: 7.32, height: 2.44},
    penalty: {
        distance: V6_WORLD.penalty.goalX - V6_WORLD.penalty.spotX,
        ballRadius: V6_WORLD.penalty.ballRadius,
    },
    // Rezervy od tyci a brevna, vzdalenost dlani pred brankovou carou.
    shot: {postInset: .32, crossbarInset: .30, catchX: .7, flightSeconds: .46, gravity: 9.81, bounce: .22},
    camera: {
        height: V6_WORLD.penalty.cameraHeight,
        behindBall: V6_WORLD.penalty.cameraBehind,
        // Sikmy pohled pred branou: zvys height pro vyssi nadhled,
        // side pro bocni pohled. Kamera se pri skoku nehybe s brankarem.
        keeperBehindLine: -5,
        keeperHeight: 4.7,
        keeperSide: 11,
        entryFov: 66,
        framingPadding: .84,
    },
};
