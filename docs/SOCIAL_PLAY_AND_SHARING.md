# Social Play and Rich Links

Apply `048_social_play` after `047_daily_friends`, before deploying this code:

```sh
.venv/bin/python -m tools.migrate_account_settings --render --migration 048_social_play
```

The command prompts privately for the external database URL and makes a backup.
It adds friendships and immutable published-result snapshots; existing games
and reward rules are not modified.

## Friends

- Profile has Overview, Friends and Settings. Settings forms are collapsed.
- Registered users send username-based requests. Only the recipient can accept.
- Canonical UUID pairs prevent duplicate/crossed requests from auto-accepting.
- Either party can remove a friendship. Pending requests can be cancelled or
  declined. Maximum 100 relationships (including pending) per account.
- Accepted friends can send a live lobby invitation through the profile.
  Invitations appear in the other player's Friends list, refreshed every 15s
  while the profile is visible. No email or push notifications are sent.
- Link duels also work without accounts, using existing guest session cookies.
- First-use rules are remembered per mode in localStorage. The dialog opens
  before creating/joining a run. How to play can reopen it.
- Forfeit requires a second confirmation; closing the dialog does not forfeit.

## Sharing

- `POST /api/shares/results` accepts only `mode` and `run_id`. The server checks
  session ownership/membership and a terminal state, then derives public data.
- This endpoint runs only after the player clicks Share, never on game finish.
- Retrying returns the same opaque `/s/{token}` link per player and result.
- A share is a URL and title, not a file attachment and not a plaintext score.
- The public HTML has Open Graph and Twitter metadata. Its preview image is
  `/s/{token}/image.png`; social apps render it as a clickable link card.
- Sharing the home page uses `/share/brand.png` and the root site URL.
- Native sharing falls back to a clickable preview and Copy link. Recipient
  apps control preview support, caching, cropping and whether a preview appears.
- `PUBLIC_SITE_URL` is the canonical HTTP(S) origin. The default is
  `https://onthedot.gg`; local browser fixtures explicitly override it.
- Public snapshots contain names, score, attempts, correct count and XP, never
  email, session tokens, private run IDs, questions or answers. Deleted owners'
  links return 404. Friend games still award no XP/rating/Solo stats.
- Pillow renders bounded 1200x630 previews. A bounded LRU avoids repeated work;
  scores use immutable snapshots, never request query parameters.

## Verification

```sh
TRIVIA_DB_TEST=1 .venv/bin/python -m unittest tests.test_social_play.SocialPlayTests tests.test_challenge_database.ChallengeDatabaseTests tests.test_solo_database.SoloDatabaseTests
node --test tests/test_result_share.cjs tests/test_solo.cjs
.venv/bin/python -m tests.challenge_preview
# A second terminal with Playwright/Sharp on NODE_PATH:
node tests/test_social_browser.cjs
```

The preview creates disposable database tables and test accounts, not production
players. Stop it with Ctrl-C to remove its schema. Start a fresh fixture before
running `test_challenge_browser.cjs` because that test changes test usernames.
