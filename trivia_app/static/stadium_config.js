/* Pixel-art penalty scene. X = depth, Y = height, Z = goal width.
 * Artwork dimensions are deliberately simplified for a small game viewport.
 * Game outcomes and deadlines are still resolved exclusively by the server.
 */
export const V6_WORLD = {
  pitchMarkings:{width:.15,elevation:.012},
  structure:{postRadius:.07,goalOutline:.025,netOpacity:.80},
  // Framing bounds, NOT the edge of the turf. Grass continues beyond the view.
  ground:{turfY:-.025,halfWidth:15.4,behindSpot:10.2,behindGoal:3.2},
  area:{halfWidth:14,depth:16.5,smallHalfWidth:6.4,smallDepth:5.5,arcRadius:9.15},
  penalty:{spotX:41.5,goalX:52.5,ballRadius:.28,minimumBallPixels:7},
  characters:{landingHalfWidth:.55},
  colors:{
    background:0xf6f3eb,outline:0x202820,
    pitch:0x88b04b,pitchStripe:0x80a745,shadow:0x587535,
    shirt:0x6f2c91,shirtLight:0x8846a5,shirtShade:0x52276f,
    strikerShirt:0x92a8d1,strikerLight:0xa8bfdf,strikerShade:0x6687b2,
    shorts:0x28333b,skin:0xeab477,skinLight:0xf8cd92,skinShade:0xbf895c,
    hair:0x393128,hairLight:0x514532,
    gloves:0xffffff,goal:0xffffff,netShade:0x8c9e88,
    ballWhite:0xffffff,ballBlack:0x202820,markings:0xffffff,
  },
};
export const BETWEEN_SHOT_SPEED=1.3;
export const STADIUM={
  betweenShotSpeed:BETWEEN_SHOT_SPEED,
  introMs:0,roleChangeMs:0,outroMs:180,
  runUpMs:280,shotMs:1500,resultHoldMs:350,
  // A deliberate pixel grid, enlarged without smoothing. Close-up framing
  // makes the action readable; do not replace this with a retina 3D render.
  pixelArt:{maxWidth:480,maxHeight:270},
  maxPixelRatio:1,maxRenderPixels:200000,
  pitch:{length:105,width:68},goal:{width:7.32,height:2.44},
  ground:V6_WORLD.ground,
  penalty:{distance:11,ballRadius:V6_WORLD.penalty.ballRadius},
  keeperHalfWidth:V6_WORLD.characters.landingHalfWidth,
  shot:{postInset:.32,crossbarInset:.30,catchX:.7,flightSeconds:.46,gravity:9.81,bounce:.22},
  camera:{
    // One close-up for both roles. The selected kit follows the local player.
    // Camera is directly behind the taker's starting position (Z = 1.35).
    // Keep target Z identical: no yaw or roll, so the goal line and box edges
    // stay parallel to the UI rules. Lower elevation tightens the fitted shot;
    // the longer viewing distance keeps the goal large relative to the taker.
    offset:[-14,3.5,1.35],lookAt:[6,.9,1.35],
    // Frame the action rather than all four corners of the entire field.
    framingPadding:.93,
  },
};
export const COMPACT_STADIUM={...STADIUM};
