/* Pure presentation mapping. An outcome is the server's actual kick result,
 * NOT whether this viewer answered correctly (both can be correct in a Duel).
 * Seats never swap when the camera changes from shooter to keeper. */
export function reactionForShot(outcome, role, viewerSeat=0) {
  const viewer=viewerSeat===1?1:0;
  const shooter=role==='keeper'?1-viewer:viewer;
  const winner=outcome==='goal'?shooter:['save','miss'].includes(outcome)?1-shooter:null;
  return {winner,moods:[0,1].map(seat=>winner===null?'neutral':seat===winner?'cheer':'sad')};
}
