# Install comms

Owner-run. Nothing here touches a provider until the credential steps.

The steps below are the service-account install. To run under your own user instead (this Mac
since 2026-09-27), skip step 1 and give every command the same directories:
`comms daemon --state-dir <state> --runtime-dir <run>`, and `TELEGRAM_MCP_RUNTIME_DIR=<run>` (plus
`TELEGRAM_MCP_STATE_DIR=<state>` for the local commands) for the rest. Keep both directories 0700.

1. Create the service accounts and the runtime paths. Both installers are idempotent; read the plan first.

   ```bash
   scripts/install_service_users.sh install --dry-run
   scripts/install_paths.sh install --dry-run
   ```

2. Provision the comms keys (audit chain, checkpoints, campaign commitments, backups). Material goes into the daemon's 0600 slot store only.

   ```bash
   comms keys provision
   ```

3. Start the daemon, run the cutover (on a fresh install it seals the empty legacy chain and
   opens the comms chain; until it completes, the daemon serves reads and holds every write),
   then check it.

   ```bash
   comms daemon
   comms cutover run
   comms keys list
   comms doctor
   ```

   Retention runs daily inside the daemon once the cutover completes.

4. Add provider credentials (each is proved live before it activates), and log the Telegram user session in.

   ```bash
   comms credential set telegram-bot-token
   comms credential set meta-access-token
   comms transport telegram login
   ```

   The user login needs a Telegram app from my.telegram.org first. Put its public
   `telegram_api_id` in `comms.json`, and its `api_hash` in the login Keychain (service
   `telegram-mcp`, account `api_hash`). The daemon reads the hash once at start: without it the
   user account stays `AUTH_REQUIRED`, and everything else still runs. Restart the daemon after
   adding it. `security` prompts for the value, so it never enters argv or your shell history.

   ```bash
   security add-generic-password -s telegram-mcp -a api_hash -U -w
   ```

   WhatsApp needs `meta.phone_number_id` and `meta.waba_id` in `comms.json` before
   `meta-access-token` can be proved. For Meta's webhooks, see `whatsapp-relay.md`.

   Instagram (proposed A49) is per account: describe each in `comms.json` under
   `instagram.accounts` (alias, label, `writes`, `dms`; no token and no ids), then add it. The
   dashboard token is typed at the hidden prompt and proved with `GET /me` before it is active.
   Tokens last 60 days: refresh them before `comms doctor` reports `IG_TOKEN_EXPIRING`.

   ```bash
   comms transport instagram account add main
   comms transport instagram doctor
   comms transport instagram token refresh --all
   ```

5. Add each MCP client. Its `cml1` seed goes to that client's helper only.

   ```bash
   comms client add --name claude-code --helper-path ~/.config/comms/claude-code.seed
   ```

`comms doctor` must report no finding except `CREDENTIAL_NOT_CONFIGURED` for providers you do not use (and `IG_TOKEN_EXPIRING`, a warning), and `"ok": true`. A Meta webhook secret reads `CREDENTIAL_UNCONFIRMED` until Meta has used it once (R-E6).
