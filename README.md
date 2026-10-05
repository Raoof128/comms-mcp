# comms: a Telegram and WhatsApp MCP gateway for one owner

comms lets an AI assistant (Claude Code, Codex, ChatGPT) read and act on one person's Telegram
and WhatsApp through a single MCP server, with every write audited. It runs on the owner's Mac.

- **Telegram:** a bot (Bot API) and the owner's own account (MTProto, through Telethon).
- **WhatsApp:** the Cloud API for sending. Meta's webhooks reach the Mac through a Cloudflare
  Worker relay that holds them encrypted while the Mac is off (`relay/`).
- **Instagram (proposed amendment A49, this branch):** one or more professional accounts through
  the Instagram API with Instagram Login: posts, insights, comments and DMs to read; publishing
  posts, Reels, carousels and Stories, reading your live Stories and their insights, comment moderation, and DM replies inside Meta's 24-hour
  window to write. Design and history:
  [`Raoof128/Instagram-MCP`](https://github.com/Raoof128/Instagram-MCP); specification:
  `docs/instagram-spec-v0.6.md`.
- **One MCP catalog of 130 tools** (154 with the 24 Instagram tools): messages, media, groups
  and their admin, a directory of people, locations and audiences, campaigns, context reads, and
  account status.
- **Authority:** an owner command is the authorization (comms spec v0.3, `owner_full_admin`).
  The MCP host's own permission prompts are the only confirmation layer. Every consequential
  write goes on a signed, anchored audit chain, and a repeated `request_id` never repeats an
  effect.

**Status.** Comms v0.3 is built and gated: the suite, the end-to-end smoke against a real
daemon and the bounded formal models all pass (see `CLAUDE.md`, Verify). Since 2026-09-27 it
runs live on the owner's Mac, under the owner's user: the bot and the user account are logged
in, and the relay is deployed. Owner-run live acceptance (D39-B) is still open, and there is no
production claim until Gates A–R pass for the exact artifact. The Instagram actor is implemented
and gated against a scripted Graph API; its live gates (GI-1 to GI-8) are still to run, and it is
adopted only by ruling R-IG0.

## Requirements

- macOS (the Keychain and the service installers are macOS-specific).
- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- Node.js, only for the relay Worker (developed on Node 24).

## Set up

```bash
uv sync --locked
```

Then follow `docs/runbooks/install.md`, in order:
1. provision the keys (`comms keys provision`);
2. start the daemon (`comms daemon`);
3. run the one-time cutover (`comms cutover run`);
4. add provider credentials;
5. log in to Telegram;
6. add each MCP client with `comms client add`.

`comms doctor` checks the result read-only, and `comms --help` lists every command.

Connecting a client: `docs/runbooks/clients-claude-code.md`, `clients-codex.md` and
`clients-chatgpt.md`. The WhatsApp relay: `docs/runbooks/whatsapp-relay.md`. Instagram accounts:
`docs/runbooks/install.md` (adding an account) and `docs/runbooks/live-acceptance-instagram.md`.

## Verify

The full gate is listed in `CLAUDE.md` under Verify. At minimum:

```bash
uv run pytest -q
uv run python scripts/e2e_smoke.py     # drives the installed CLI and a real daemon end to end
uv run pytest tests/formal -q -s       # the bounded formal models
(cd relay && npm ci && npm run check)  # the relay Worker in workerd
```

## Layout

| Path | What |
|---|---|
| `src/comms/core/` | Transport-neutral core: `comms.db` (SQLCipher), the directory, campaigns, the audit chain, keys, backup, retention |
| `src/comms/services/` | Every read and write the tools perform |
| `src/comms/mcp/` | The tool catalog, dispatch, HTTP `/mcp`, the stdio proxy (`comms mcp --stdio`), OAuth for remote clients |
| `src/comms/runtime/` | The daemon's composition, listeners, workers, settings (`comms.json`) and operator commands |
| `src/comms/transports/telegram/` | The Telegram bot and user adapters; the only Telethon importer |
| `src/comms/transports/whatsapp/` | The WhatsApp Cloud API, webhooks and relay client |
| `src/comms/transports/instagram/` | The Instagram actor (proposed A49): the pinned Graph client, accounts, the publishing ledger and the outcome table |
| `transports/whatsapp/` | WhatsVault, imported with its history (`docs/provenance/whatsvault.md`) |
| `relay/` | The Cloudflare Worker relay (TypeScript) |
| `formal/` | Bounded executable models of the safety rules (`formal/README.md`) |
| `site/` | The public W-Vault pages (privacy policy), published by `.github/workflows/pages.yml` |
| `src/telegram_mcp/` | The legacy `telegram-mcp` CLI forwarder |

## Documents

- **Specifications:** `docs/comms-spec-v0.3.md` (current). It says which parts of
  `docs/comms-spec-v0.2.md` and the frozen `telegram-mcp-v0.1.10-final-engineering-spec.md`
  still apply. The proposed Instagram amendment is `docs/instagram-spec-v0.6.md`.
- **Evidence and rulings:** `docs/verification/` (`comms-v0.3.md`, `comms-v0.3-rulings.md`,
  `comms-relay.md`, the actor matrix and the Telegram RPC review).
- **Runbooks:** `docs/runbooks/`.
- **Designs and plans,** kept as they were approved: `docs/superpowers/`.
- **The audit trail of every change:** `AGENT.md` and `CHANGELOG.md`.

Never commit credentials, session files or keys. `.gitignore` carries the baseline, and secrets
live in the daemon's secret store and the macOS Keychain only.
