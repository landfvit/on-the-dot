# Game Audio

Web Audio in `trivia_app/static/audio.js` synthesizes click, kick, glove catch,
net contact, win, loss and level-up. Audience reactions use two short public-domain WAV
recordings bundled in `trivia_app/static/sounds/` (see its LICENSE.md).
There are no third-party requests, background crowd loops or music.
Cheer means a positive result for the player on this device; groan means a
negative result. This includes keeper saves and both seats in a Friend Duel.
Decoded samples are prepared during camera entry; failed or late loads never
queue a reaction over a later question. Set reaction gain in `crowdVoice()`.

## Timing

`stadium_scene.js` emits a cue when the animation crosses the kick or ball-contact
threshold, once per shot. Keeper run-up is included. `stadium_intro.js` forwards
only newly presented shots: camera changes and restoring a pose stay silent.
With animations disabled there is one short result-contact effect instead of
overlapping kick/contact sounds. `solo.js` plays win/loss after the result reveal,
using the server's shootout winner. History, refresh and repeated polling do not
replay a result sound. Audio never changes a deadline, score or question.

`xp_progress.js` animates committed XP after the result reveal. Each crossed
server-provided level threshold rolls the green bar over and briefly pulses it.
The `level-up` cue is a short ascending three-note chime, played once per result
even when several levels are gained. History, zero-XP rewards and guest games
never celebrate. Reduced motion shows the final balance and a static level
notification; mute and volume use the same controls as other game sounds.

## Controls

- The page toolbar and game header both toggle mute/unmute with one click.
- The volume slider is in Profile > Settings > Sound; it updates immediately.
- `onthedot.audio` in localStorage holds only enabled/volume, shared across tabs on
  this origin. These are device/browser settings, independent from account data.
- Default volume is 50%. A limiter, short envelopes and bounded voices avoid harsh
  transients and unbounded rapid clicks. Change recipes in `play()` to tune timbre.
- No AudioContext is created until a trusted pointer/keyboard interaction.
  If a browser blocks playback, the cue is skipped without retrying later.
- Muting or hiding the page cancels voices. Background tabs do not play effects;
  audio re-unlocks with the next gesture. Missing Web Audio never blocks the game.

## Checks

```sh
node --test tests/test_audio.cjs tests/test_solo.cjs tests/test_xp_progress.cjs
```

Browser checks with Playwright on NODE_PATH and a local preview on port 8013:

```sh
node tests/test_audio_browser.cjs
node tests/test_mobile_layout.cjs
node tests/test_profile_xp_browser.cjs
```
