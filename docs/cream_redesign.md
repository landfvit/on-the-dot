# Cream UI and stadium

The September 2026 redesign changes presentation only. Server decisions, answer
deadlines, rewards and friend-duel rules remain authoritative and unchanged.

## Visual controls

- `trivia_app/static/points_theme.css`: shared cream/ink/green palette and logo
  glyph/disc colors. `redesign.css` is the final shared outline/type treatment.
- `home.html`, `home.css`, `home.js`: public homepage and accessible rules tabs.
- `solo_mobile.css` and `solo_results.css` still own the timed mobile layout.
  Do not add panel padding in the theme without rerunning the mobile tests.
- `stadium_config.js`: green pitch, WHITE markings, goal/line thickness, jersey
  colors and background blur. There are no spectator meshes or stand banners.
- `stadium_v6_world.js`: opaque terraces, players and turf bounded by the inner
  terrace footprint. `setTheme()` only recolors architecture, never pitch paint.
- `crowd_reaction.js`: maps authoritative goal/save/miss to viewer reactions.
  Audio follows the actual result, not whether a Duel answer was correct.
- `stadium_scene.js`: architecture stays blurred during play and comes into
  focus on the overhead outro. Shot timing includes a short result hold.
- `audio.js`: generated stereo audience ambience, cheers and groans. No remote
  audio files. `crowdVoice` amplitudes control audience loudness; the existing
  master volume/mute still applies. Ambience stops on exit, mute or hidden tabs.
- `theme.js` applies device/saved appearance before first paint. `dark_mode.css`
  overrides semantic colors. Use `onthedot.theme` in localStorage to inspect the
  explicit choice; absent means follow the device. Both toolbars toggle it.

## Assets

Logo circles stay palette green with cream letters on a transparent background.
`brand/logo.svg` and `brand_wordmark.html` are editable vector sources.

`node tools/export_brand_assets.cjs` exports PNG variants through Sharp.
`node tools/capture_guide_assets.cjs` renders the actual Three.js scene for the
guide's shooter and keeper screenshots. It does not contact production APIs.

## Checks

Browser checks require Playwright/Sharp on NODE_PATH and a LOCAL preview URL in
MOBILE_TEST_URL. Use `python -m tests.challenge_preview` for an isolated database
fixture; stop it with Ctrl-C to remove its temporary schema.

- `test_redesign_browser.cjs`: eight public pages, 320/390/768/1440 widths,
  palette, overflow, rules tabs and no-JavaScript homepage.
- `test_navigation_browser.cjs`: header links, help/back/share/sound controls.
- `test_mobile_layout.cjs`: stationary question/answer/Next layout, results,
  network recovery and real WebGL pixels across ten viewports.
- `test_crowd_browser.cjs`: audio-only audience, white markings in both themes,
  viewer reactions, saves and bounded overhead stadium at mobile/desktop.
- `test_theme_browser.cjs`: dark pages, icon pixels, preference persistence,
  system default, keyboard/cross-tab changes and unavailable localStorage.
- `test_audio_browser.cjs`: actual PCM output, shot timing, mute and lifecycle.
- `test_challenge_browser.cjs`: actual fixture-backed Daily and two-client Duel.
- `test_crowd_reaction.cjs`, `test_stadium_fade.cjs`, `test_stadium_motion.cjs`:
  pure reaction/geometry contracts and ball/keeper physics.

No database migration is needed.
