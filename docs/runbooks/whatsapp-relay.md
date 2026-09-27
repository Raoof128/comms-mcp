# The WhatsApp relay (spec A48)

Meta retries a failed webhook for only 36 hours, and the WhatsApp Cloud API has no history method. The relay is a Cloudflare Worker (`relay/`). It holds Meta's webhooks, encrypted to this Mac, for 30 days, so the daemon can run only when you want it to. The daemon pulls what arrived, verifies each message as Meta's, and archives it once.

**What Cloudflare holds:**
- ciphertext only;
- the pull key, the path token and the verify token;
- the public `age1…` recipient.

**What it never holds:** Meta's app secret (D-R1). Only the daemon verifies Meta's signature, so a Cloudflare compromise cannot forge a message. Junk posted to the relay is quarantined on the Mac.

Every step below is run by you, in your own terminal. A secret goes only into a pipe: `comms relay export-pull-key` and `comms relay new-path` refuse a terminal. Print this checklist at any time with:

```bash
comms relay setup
```

## Deploy

1. **Install the Worker and log in to Cloudflare.**

   ```bash
   cd relay && npm ci && npx wrangler login
   ```

2. **Give the Worker its four values.** The path token is shown once on your own terminal (`tee /dev/tty`), because it ends Meta's callback URL. Type a new random value for the verify token.

   ```bash
   comms relay export-pull-key | npx wrangler secret put RELAY_PULL_KEY
   comms relay recipient | npx wrangler secret put RELAY_AGE_RECIPIENT
   comms relay new-path | tee /dev/tty | npx wrangler secret put RELAY_PATH_TOKEN
   npx wrangler secret put META_VERIFY_TOKEN
   npx wrangler deploy
   ```

3. **Point Meta at the relay.** In Meta's WhatsApp Configuration, set:
   - the callback URL to `https://comms-relay.<your-subdomain>.workers.dev/webhooks/meta/<path token>`;
   - the verify token to the value from step 2.

   Meta verifies the callback with a handshake the Worker answers.

4. **Point the daemon at the relay.** In `comms.json`, add `"relay": {"url": "https://comms-relay.<your-subdomain>.workers.dev"}` and remove `webhook_port`. With a relay, the local listener is not served. Restart the daemon.

5. **Check it.**

   ```bash
   comms relay status
   comms doctor
   ```

   `acked_through` grows as messages arrive. The mailbox drains within a minute of the daemon running.

## Day to day

- **Stop and start the daemon freely.** Anything that arrives while it is off waits in the relay for up to 30 days. The daemon collects it on its first tick after starting, then every 60 seconds.
- **After 25 days,** `comms doctor` reports `RELAY_BACKLOG_OLD`. Start the daemon before day 30, when the relay purges.

## When doctor reports a relay problem

| Finding | Meaning | Do |
|---|---|---|
| `RELAY_UNREACHABLE` | the last pull did not reach the relay | check the network and `npx wrangler deployments list` |
| `RELAY_REFUSED` | the relay refused the pull key | re-run `comms relay export-pull-key \| npx wrangler secret put RELAY_PULL_KEY` |
| `RELAY_CLOCK` | this Mac's clock is more than 300 s off | fix the clock (System Settings, Date & Time) |
| `RELAY_STALE` | the daemon is running but no pull succeeded for ten minutes | as for `RELAY_UNREACHABLE` |
| `RELAY_GAP` | rows vanished that were neither acked nor purged | someone with the Cloudflare account deleted rows; treat as a suspect account (below) |
| `RELAY_QUARANTINE` | rows that did not decrypt or verify | usually junk sent to a leaked path; if they keep coming, rotate the path |

## Rotate

- **The path token**, if it leaked (junk keeps arriving): run the command below, then update Meta's callback URL.

  ```bash
  comms relay new-path | tee /dev/tty | npx wrangler secret put RELAY_PATH_TOKEN
  ```

- **The pull key**: rotate it, send the new key to the Worker, then restart the daemon, which reads its keys at start. Until both sides agree, pulls are refused and nothing is lost.

  ```bash
  comms keys rotate relay-pull-key
  comms relay export-pull-key | npx wrangler secret put RELAY_PULL_KEY
  ```

- **The `age` key** cannot be rotated in this version. A queued row could outlive the only key that opens it.

## A suspect Cloudflare account

1. Rotate Meta's app secret in Meta's App Dashboard, then rotate it in comms:

   ```bash
   comms credential rotate meta-app-secret
   ```

2. Rotate the path token, the pull key and the verify token (above).
3. Review `comms relay status` for gaps and quarantine.

An account holder could delay or delete messages, but could never read or forge one.
