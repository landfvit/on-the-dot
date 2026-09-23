# Public UI and Community

The public ON THE DOT. interface keeps the bold type and menu/profile drawers
inspired by https://fermi.gg. Its palette now matches the stadium: dark teal,
light text, coral and citrus accents. No Fermi code, content or player data is
imported. Legacy `points_*` cookie/storage names and CSS/JS identifiers stay
unchanged so existing sessions, saved games and integrations keep working.

## Routes

- `/penalties`: existing ten-question penalty game and results.
- `/leaderboard`: Today, 7 days and All time XP rankings.
- `/history`: signed-in player's finished and abandoned games, paginated.
- `/penalties?run=UUID`: owner-authorized result review.
- `/u/username`: existing public profile.

The menu and profile drawers are native modal dialogs with focus trapping,
Escape and return focus. Result sharing copies score, difficulty and the public
game link. It does not expose answer text or private run links.

## Ranking Contract

`api/game_community.py` reads the immutable `game_xp_ledger`. It does not accept
scores from a client and needs no new migration. Registered players with positive
XP in the period are ranked; trial identities never appear. XP from correct
answers remains eligible even if the player ends the game early, matching the
existing award rules. Level always reflects all-time XP.

Today starts at 00:00 UTC. 7 days includes today and the six preceding UTC dates.
Period filtering uses the ledger's award timestamp. Equal XP shares a dense
rank; username stabilizes pagination only. Own position, table rows and score
distribution use the same database snapshot. No emails, account UUIDs, sessions
or password hashes are returned. History requires account authentication and
never accepts an account identifier from the client.

Private PvP remains unranked. Its guest identity must first be linked to an
authenticated account before a trustworthy account-based PvP leaderboard can
be added. No fabricated PvP ratings, streak prizes or badges are displayed.

## Styling and Tests

`points_theme.css` defines the palette; `community.css` owns the public shell,
leaderboard, history and dark gameplay panels. The existing dark 3D world,
camera framing, synchronized reveal and shot physics are unchanged. Icons are
locally hosted Lucide Static 0.468.0, with its license in `static/icons/LICENSE`.

Tests: `tests/test_game_community.py`, the community cases in
`tests/test_solo_database.py`, `tests/test_community.cjs`, `tests/test_solo.cjs`.
`TRIVIA_DB_TEST=1` database tests create and drop isolated schemas.
`python -m tests.community_preview` runs an opt-in loopback-only browser fixture
on port 8013 without database writes. Stop it after visual QA; the actual app
remains on 8002.
