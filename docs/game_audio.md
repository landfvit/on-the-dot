# Game Audio

All effects are synthesized locally with Web Audio in `trivia_app/static/audio.js`.
There are no external recordings, audio downloads, third-party requests or music.
The recipes cover click, kick, glove catch, net contact, win and loss.

## Timing

`stadium_scene.js` emits a cue when the animation crosses the kick or ball-contact
threshold, once per shot. Keeper run-up is included. `stadium_intro.js` forwards
only newly presented shots: camera changes and restoring a pose stay silent.
With animations disabled there is one short result-contact effect instead of
overlapping kick/contact sounds. `solo.js` plays win/loss after the result reveal,
using the server's shootout winner. History, refresh and repeated polling do not
replay a result sound. Audio never changes a deadline, score or question.

## Controls

- The game header has a mute/unmute icon.
- The menu has the same control and a volume slider.
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
node --test tests/test_audio.cjs tests/test_solo.cjs
```

Browser checks with Playwright on NODE_PATH and a local preview on port 8013:

```sh
node tests/test_audio_browser.cjs
node tests/test_mobile_layout.cjs
```
