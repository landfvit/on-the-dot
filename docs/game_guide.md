# Public game guide

`/how-to-play` is a public, read-only rulebook linked from the navigation menu,
the penalties selection screen, and the profile's team section. It does not
create games, query the database, load Three.js, or request player data.

## Sources of truth

- `trivia_app/game_guide.py` reads `api.solo_engine.RULES` and uses `shootout()`
  for the early finish, last kick and sudden death examples. It uses `rewards()`
  for the Medium win example, which intentionally includes incorrect answers.
- `trivia_app/templates/game_guide.html` describes the current account and game
  behaviour. Update its prose when changing streak eligibility, weekly question
  rotation, guest persistence, club affiliation or leaderboard capabilities.
- Joining a club currently adds a badge only. Club membership is independent of
  the Team / scope question filter. There is no team XP bonus or club leaderboard.
- `trivia_app/static/game_guide.js` progressively enhances the examples using
  native radio controls. All examples remain visible without JavaScript.
- The guide reuses the gameplay scoreboard styles and football masks. Its two
  scene images are captures of the actual game renderer, not a separate design.

## Updating the illustrations

With a local server running and Playwright plus Sharp available to Node:

```sh
GUIDE_CAPTURE_URL=http://127.0.0.1:8013 node tools/capture_guide_assets.cjs
```

The script only accepts a local URL, checks for a nonblank scene and a visible
keeper catch, and updates `trivia_app/static/guide/shooter.png` and `keeper.png`.
It does not start a real game or write database records.

## Verification

```sh
.venv/bin/python -m unittest tests.test_game_guide tests.test_public_shell tests.test_hosted_boot tests.test_stadium_assets
node tests/test_game_guide_browser.cjs
node tests/test_mobile_layout.cjs
```

The browser tests use a local preview on port 8013 by default and mock player
and gameplay API calls where required. They check mobile/desktop overflow,
keyboard operation, stable example positions, no-JavaScript content, team-help
navigation, fixed gameplay controls and the live 3D scene.

These checks are functional tests, not stress tests. Load testing requires a
separate plan and an isolated environment with disposable test data.
