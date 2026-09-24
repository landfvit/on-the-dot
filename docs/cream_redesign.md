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
  colors, blur strength and supporter density. Crowd shirt palettes are separate
  from the foreground player jerseys.
- `stadium_v6_world.js`: opaque stepped terraces and player meshes.
- `stadium_crowd.js`: instanced low-poly supporters. Twelve rows at spacing 1.25
  create 3,772 people using ten mesh draw calls. `crowd.animate` is false: poses
  change after a resolved shot, but the crowd does not jump or wave continuously.
  There are no stand banners or visible end labels.
- `crowd_reaction.js`: maps authoritative goal/save/miss to fixed physical
  supporter seats. Both Duel clients see the same stand celebrate. A replay is
  neutral; reset clears the previous reaction.
- `stadium_scene.js`: crowd uses the foreground render layer, architecture uses
  the blurred background layer. Shot timing includes a short result hold, still
  below the Duel review interval.

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
- `test_crowd_browser.cjs`: dense colored crowd, white pitch markings, both
  viewers' reactions, saves, moving shots and overhead outro at mobile/desktop.
- `test_challenge_browser.cjs`: actual fixture-backed Daily and two-client Duel.
- `test_crowd_reaction.cjs`, `test_stadium_fade.cjs`, `test_stadium_motion.cjs`:
  pure reaction/geometry contracts and ball/keeper physics.

No database migration is needed.
