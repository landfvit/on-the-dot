# Account Settings and Guest Games

Apply `045_account_settings` BEFORE deploying this code. The migration adds
private preferences and hashed recovery tokens, permits anonymization, and
removes the one-game guest restriction. Existing games and XP are not modified.

From the local On The Dot. project:

```sh
.venv/bin/python -m tools.migrate_account_settings --render
```

The command prompts privately for the External Database URL, requires `MIGRATE`,
backs up the complete database under ignored `backups/`, and applies this one
migration and its marker atomically. It is safe to repeat. Never commit backups,
paste database URLs into chat, or run the initial empty-database restore again.
Without `--render` it upgrades the local database from `.env`.

## Account Behavior

- Password change and email change require the current password and revoke all
  other sessions and outstanding recovery links. The current session is rotated.
- Username, bio and club are public; email and preferences remain private.
- Username is chosen at registration and cannot be edited. The profile API
  rejects a `username` field. Usernames are normalized to lowercase and protected
  by the database's UNIQUE constraint, including concurrent registrations.
- Account deletion requires the password and explicit `DELETE`. It removes email,
  password hash, username, bio, club, sessions and recovery tokens. A random
  tombstone identity remains for frozen, non-public gameplay/XP records. Deleted
  accounts cannot sign in, appear on leaderboards, or be restored.
- Guests can play repeatedly. Scores are per-game and never enter registered XP,
  streaks or leaderboards. Their own active run is resumed across tabs. Registered
  players retain weekly no-repeat allocation; guests have fresh shuffled decks.
- Animation preferences are saved to the account and mirrored locally for the
  first frame. System reduced-motion remains authoritative.

## Optional Password Recovery

No email verification is required at registration. Password recovery stays
disabled and its button hidden until all these Render environment fields exist:

```text
PUBLIC_SITE_URL=https://onthedot.gg
RESEND_API_KEY=<secret entered only in Render>
ACCOUNT_EMAIL_FROM=ON THE DOT. <account@onthedot.gg>
```

Configure a sender/domain in Resend before enabling. Sender-domain verification
is infrastructure configuration, not verification of player email addresses.
This task does not create a paid service or send real emails.

Recovery uses the HTTPS Resend API, not SMTP. Links use the configured origin,
never the request Host, and keep their token in a URL fragment, cleared immediately
by the account page. Only SHA-256 token hashes are stored, for 30 minutes. A token
works once and reset revokes all sessions; players then sign in normally. The
request endpoint gives the same response for known and unknown emails, uses IP
and account throttles, and logs only a generic delivery failure.

## Badges and Seasons

`tools.export_public_branding` exports only game-club badges and metadata from the
local PL-Analytics-derived dataset. Badges are served locally, with their existing
provider source URLs recorded in `public_metadata.json`. Names remain in image
alt text and tooltips. A failed image falls back to its club name.

The footer is generated from season references in the published question bank,
not the much wider analytics database. Current range: PL Seasons 16/17 - 25/26.
Regenerate and verify metadata when publishing another season. This range means
questions include those seasons, not complete statistical coverage for every one.

## Advertising Slots

Six inactive placements are available:

| Slot | Position | Desktop | Mobile |
| --- | --- | --- | --- |
| game-selection | Below game selection | Up to 728 x 90 | Up to 320 x 100 |
| shootout-results | Below results/actions and registration offer | Up to 728 x 90 | Up to 320 x 100 |
| leaderboard-bottom | Below ranking and pagination | Up to 728 x 90 | Up to 320 x 100 |
| sidebar-left | Left of selection, results or leaderboard | 160 x 600 | Hidden |
| sidebar-right | Right of selection, results or leaderboard | 160 x 600 | Hidden |
| gameplay-bottom | Below question/answer controls during a game | 320 x 50 | Hidden |

Preview with `/penalties?ad_preview=1` or `/leaderboard?ad_preview=1`. Empty normal
placements occupy no space. Preview does not load any ad network, analytics,
tracking pixels or cookies. During a game only `gameplay-bottom` can appear: it
is outside the question grid, has a 32px gap below controls and follows the same
panel reveal as the questions. Its desktop breakpoint is 1101 x 760; side rails
require at least 1280 x 780. Both also require a fine pointer and hover support.
Smaller windows and touch devices retain the original layout without these slots.
Side rails never overlay the live pitch; they fade back with the results.
Account, login, history and recovery pages contain no ad placements.

The desktop public UI is capped at 800px (including its header and footer).
Both side rails follow that shared width and keep a 24px gap from the content.
Rails are also prepared on Home, How to play, Daily and Friend Duel selection;
append `?ad_preview=1` to inspect the empty placements. Mobile layout and the
full-screen stadium remain unchanged. No ad provider is loaded.

When adding a provider, keep each creative inside `.ad-creative`, reserve these
dimensions before requesting an ad, and integrate the appropriate consent flow
before loading external code. Keep the gameplay banner's separation from answer
buttons and do not intercept New shootout; no interstitials or timed popups have
been implemented. Never expand a creative beyond its reserved bounds.

## Checks

Database tests use disposable schemas and mocked email delivery:

```sh
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest tests.test_account_settings tests.test_shootout_database
node --test tests/test_solo.cjs tests/test_community.cjs
```

With Playwright and Sharp on `NODE_PATH` and a local preview on port 8013:

```sh
node tests/test_settings_browser.cjs
node tests/test_mobile_layout.cjs
node tests/test_ad_layout.cjs
```
