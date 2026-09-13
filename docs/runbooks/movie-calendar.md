# Cinemateca movie calendar

## Architecture

`Cinemateca HTML → reviewed film identities → Trakt list/watchlist → ICS / Google Calendar`

The `movie_calendar` Python package is the reusable execution layer. A thin
`skills/cinemateca/SKILL.md` teaches agents how to operate it. The optional MCP
adapter calls exactly the same Python functions. A scheduled run needs no LLM.
Add future venue adapters here; do not duplicate the sync for each agent host.

## Install

Requires Python 3.12+ on macOS/Linux (the process lock uses `flock`).

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,gws]'
mkdir -p ~/.config/benjaminos
cp packages/movie_calendar/config.example.json ~/.config/benjaminos/cinemateca.json
export CINEMATECA_CONFIG="$HOME/.config/benjaminos/cinemateca.json"
```

Edit that private config with the intended Trakt username/list ID and existing
dedicated Google calendar. `selection` is `all` (every programme entry), `list`
(reviewed films in the Cinemateca list, including planned additions), or
`watchlist` (reviewed films in the main Trakt movie watchlist). Set
`add_reviewed_to_list` false for matching without list additions.

`catalog` may point to a private replacement JSON file; otherwise the bundled
public catalog is used. Relative paths resolve from the working directory;
absolute paths are recommended for service configuration.

## Credentials

Inject only the needed secrets from Infisical `pharoah/dev` at runtime. Do not
dump the workspace's secret values. Configure:

Pharoah was verified as project `97a8ec8d-c2af-44ce-94b2-71b806434076` on
2026-09-13. For the existing authenticated VPS wrapper, add this to the private
config (substitute the actual wrapper path on your host):

```json
"infisical": {
  "command": ["/home/benjaminbot/bin/infisical-self-hosted", "--project", "pharoah"],
  "environment": "dev",
  "path": "/"
}
```

With a directly authenticated CLI, use `"command": ["infisical"]`,
`"project_id": "97a8ec8d-c2af-44ce-94b2-71b806434076"` and
`"domain": "https://infisical.expertecosystems.com/api"`. The adapter retrieves
only named keys and captures values in memory. It maps the existing
`benjaminos-trakt-clientid`, `benjaminos-trakt-secret`, access/refresh token,
token-created-at and token-expires-in keys to the CLI's environment variables.
`BENJAMINOS_SA_JSON` is used in memory, without writing another Google key file.
The command array is trusted operator configuration; agents must not accept it
from website text or tool-call arguments.

| Variable | Purpose |
|---|---|
| `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET` | Existing registered Trakt app |
| `TRAKT_REFRESH_TOKEN` | Optional initial seed; subsequent rotated tokens are saved locally |
| `TRAKT_CLIENT_FILE` | Alternative private JSON containing client_id/client_secret |
| `TRAKT_TOKEN_FILE` | Optional existing token JSON; default state_dir/trakt-tokens.json |
| `GOOGLE_APPLICATION_CREDENTIALS` | Private file containing the BenjaminOS service-account key |
| `BENJAMINOS_SA_JSON` | In-memory alternative from Pharoah; preferred for the existing setup |

Google's configured `subject` and `service_account` are explicitly checked;
the runner refuses a different service-account key or the primary calendar.
It requests Calendar scope only. It does not request Gmail, change delegation,
or use the broader EIR agent account. Domain-wide delegation is broader than
this application's configured subject; the code's constraint does not narrow
Google's grant itself. Existing calendar sharing is preserved.

Connect a new Trakt session if needed:

```bash
.venv/bin/movie-calendar login --config "$CINEMATECA_CONFIG"
```

Complete the printed device-code flow. Tokens are stored atomically with mode
0600, refreshed before expiry, and kept on a persistent volume. A preview may
refresh OAuth tokens, but never changes Trakt lists or Google events. Existing
private lists work with OAuth; making them public is unnecessary.

## Preview, then apply within the authorized scope

```bash
.venv/bin/movie-calendar run --config "$CINEMATECA_CONFIG" --trakt --google
.venv/bin/movie-calendar run --config "$CINEMATECA_CONFIG" --trakt --google --apply
```

For public extraction only, use selection `all` and omit integration flags.
`--fresh` bypasses the one-hour public HTML cache. `--from YYYY-MM-DD` changes
the lower date bound; the default is today's Lisbon date.

Outputs under the private `state_dir`:

- `programme.json`: source coverage and upcoming screenings.
- `selected-screenings.json`, `calendar.ics`: selected screenings and an RFC 5545 snapshot.
- `plan.json`: additions, watchlist matches, unresolved identities, Google changes and applied status.
- `trakt-tokens.json`, `run.lock`, `cache/`: runtime credentials, overlap protection and public-page cache.

All downstream plans are completed before list/event writes. Writes may still
partially succeed on an API failure; rerun after fixing the error. Trakt re-reads
membership and Google looks up the stable `cinemateca-<id>@personal-movie-calendar`
iCalUID before writing. Post-write reads verify the result. Existing imported
events are patched, preserving reminders and unrelated properties. New events
are free/transparent with no default reminders. Cancelled events stay cancelled.
Run one scheduler against one persistent state directory; the local lock is not
a distributed lock across machines.

## Maintaining matches

The bundled catalog starts with 43 film identities reviewed against public
Trakt director credits on 2026-09-13. It contains no user's list membership.
Unseen films appear in `unresolved`; monthly programmes will require new reviews.
Match title, year, director and external IDs before updating the catalog.
Some works exist only as Trakt TV entries and must remain unresolved as movies.
Known multi-film sessions use explicit screening overrides; new ones require
review. A partial match can select an entire session, but cannot shorten it to
one film. Total session runtime is used only when published explicitly.

No native iCal feed was found in the initial investigation. The scraper covers
all pages of cycles linked from Cinemateca's current programme homepage; it is
not independently reconciled with the PDF/day view or all educational events.
Markup changes fail the crawl instead of triggering destructive reconciliation.
Missing screenings never cause automatic deletion. Cancellations and removals
need review; no hosted ICS subscription is deployed by this package.

## Scheduling

Recommend a daily refresh on the existing Pharoah VPS, with a persistent private
state directory and Infisical injection. Monthly-only runs can miss programme
changes. A timer can run the same CLI manually, daily or monthly. The example
in `infrastructure/cron/cinemateca.cron.example` is inert until installed; choose
one cadence. No schedule is activated by installing this package or skill.

Use `infrastructure/vps-scripts/cinemateca-sync.sh` after setting
`BENJAMINOS_ROOT` and `CINEMATECA_CONFIG`. With the `infisical` config above,
the application retrieves its specific keys through the existing wrapper.
Start with a preview and verify Google service-account access before enabling
writes. Alert on failures or new unresolved matches; quiet unchanged runs are
preferable to daily notifications. GitHub Actions is suitable for tests, but
ephemeral runners need a secure persistent token store before scheduling this
OAuth workflow; do not put personal reports into public Actions artifacts.

## Agent hosts and MCP

Codex/Claude Code discovery links point at the same skill. For another host,
copy the `skills/cinemateca` directory into its supported skill path and make
the installed CLI available. This does not install credentials or grant access.

For a local MCP-capable client:

```bash
.venv/bin/pip install -e '.[gws,movie-mcp]'
CINEMATECA_CONFIG="$HOME/.config/benjaminos/cinemateca.json" .venv/bin/movie-calendar-mcp
```

Add `"mcp_integrations": ["trakt", "google"]` to the private config for those
connections; the default is public extraction only. Tools expose previews and
the last plan. Set `CINEMATECA_ALLOW_SYNC=1` in the operator-controlled environment
to expose the write tool. The model cannot supply another account or file path.
The server uses the maintained MCP SDK v1 line with a `<2` version bound.

Rotated Trakt credentials live in the private persistent state directory and
take precedence over the initial Infisical seed. Do not run independent token
refreshers on multiple hosts. Back up that directory securely or reconnect
Trakt when migrating. This package does not yet write rotated tokens back to
Infisical; it does not claim a stateless runtime.

ChatGPT web needs an authenticated reachable MCP service; local stdio alone is
not that connection. A future remote adapter should wrap this package behind
OAuth, pin the personal account server-side, and expose the same narrow tools.
Do not publish the service-account key or an unauthenticated sync endpoint.
See [OpenAI MCP server documentation](https://developers.openai.com/plugins/build/mcp-server)
and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## Validation

```bash
.venv/bin/ruff check packages/movie_calendar tests/movie_calendar
.venv/bin/ruff format --check packages/movie_calendar tests/movie_calendar
.venv/bin/pytest
```

Offline tests cover HTML structure, multi-film duration, Lisbon daylight saving,
ICS escaping/folding, unresolved matching, pagination, token refresh and repeat
calendar sync behavior. A real Google round trip still requires the configured
BenjaminOS key at runtime. API reference: [Google event imports](https://developers.google.com/workspace/calendar/api/v3/reference/events/import)
and [iCalUID lookup](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).
