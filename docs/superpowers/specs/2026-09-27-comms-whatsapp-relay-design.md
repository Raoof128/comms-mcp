# Comms WhatsApp relay: design

**Status:** the owner approved the design section by section on 2026-09-27. Each section was checked against the 2026 developer docs, and the whole design was gauntleted by execution. **One change after approval needs the owner's decision:** the self-review found that a Worker holding Meta's app secret could forge messages. The design below keeps the app secret off Cloudflare (see Threat model, decision D-R1). This document awaits the owner's review before an implementation plan is written.

## Intent

**What the owner said:**
- The Mac daemon should run only when the owner wants it to.
- WhatsApp messages that arrive while it is off must not be lost, and the AI must still see the complete WhatsApp history.
- Use Cloudflare, with option A (encrypted for the Mac only) and option B (keep queued messages 30 days).

**Why it matters:** the WhatsApp Cloud API has no history method. The only record is what Meta pushes to a webhook, and Meta retries a failed delivery "a few more times with decreasing frequency over the next 36 hours", then drops it. A daemon that is off for more than about a day and a half loses WhatsApp messages for good. Telegram is unaffected: the user account reads history live, and the bot gets 24 hours of held updates.

**Success:** turn the Mac off for a week and back on. Every WhatsApp message from that week is then in the archive, each verified as Meta's, each exactly once, and Cloudflare never held a readable copy.

## Architecture

```
Meta ──POST /webhooks/meta/<path-token>──▶ Worker ──(raw bytes + signature header)──▶ Mailbox (Durable Object, SQLite)
                               │                                   │ age-encrypt to the Mac's key
                               │ GET: verify-token handshake        │ store ciphertext, seq AUTOINCREMENT
                                                                    │ alarm: purge rows older than 30 days
comms daemon (on demand) ──signed POST /pull, /ack──▶ Worker ──▶ Mailbox
   └ decrypt (age key in the daemon's store) → verify Meta's HMAC (only here) → Inbox.accept → ack
```

Meta only ever talks to Cloudflare. The Mac is never reachable from the internet: no tunnel and no public port.

## Components

### 1. `relay/`: the Cloudflare Worker `comms-relay` (new, TypeScript)

- **`POST /webhooks/meta/<path-token>` (D-R1: the Worker never holds Meta's app secret).**
  - The refusals run in order: a path token other than the configured 32-byte token, compared in constant time (404); a rate bound (429); a content type other than JSON (415); a missing or malformed `X-Hub-Signature-256` header (401, format only); a body over 8 MiB (413).
  - The Worker cannot check the HMAC, because it has no app secret. It stores the raw bytes and the signature header unverified, and the Mac is the only verifier.
  - The answer is 200 only after the Mailbox has stored it, and 503 otherwise, so Meta retries.
  - A body is never refused for size below 8 MiB. Meta sets no size limit and batches up to 1000 updates. A body over 1 MiB is stored as several rows sharing one `batch` id and a part index; a Durable Object row holds at most 2 MB.
- **`GET /webhooks/meta/<path-token>`.** The verify-token handshake (`hub.mode=subscribe`, `hub.verify_token` compared in constant time, `hub.challenge` echoed). It never delivers anything.
- **`POST /pull`, `POST /ack`.** Daemon-only, with signed requests (see Keys). `/pull {after, limit}` returns up to 50 rows or 256 KiB of `{seq, received_at, ciphertext}`, plus `purged_through`. `/ack {through}` deletes rows with `seq ≤ through`. It is idempotent: repeating it deletes nothing new.
- **Worker secrets** (`secrets.required`, so a deploy fails if one is missing): `RELAY_PATH_TOKEN`, `META_VERIFY_TOKEN`, `RELAY_PULL_KEY`. Meta's app secret is deliberately absent (D-R1). **Plain variable:** `RELAY_AGE_RECIPIENT`, the public `age1…` key.

### 2. `Mailbox`: one SQLite Durable Object

- **Table:** `mail(seq INTEGER PRIMARY KEY AUTOINCREMENT, received_at INTEGER, batch TEXT, part INTEGER, parts INTEGER, ciphertext BLOB)`.
  - `AUTOINCREMENT` is required. Without it, SQLite reuses the largest ID after that row is deleted, which happens on every full drain. Checked on workerd: after a drain the next `seq` still grows.
- **Encryption happens here, not in the Worker.** A Durable Object request gets 30 s of CPU by default, while a Worker on the free plan gets 10 ms. The encryption is `age` v1 X25519 via `age-encryption` (typage). Measured: about 1.8 ms for a small webhook and about 40 ms for 1 MiB in Node.
- **What is encrypted:** the canonical JSON `{raw_b64, signature, received_at}`. The signature header travels inside the ciphertext, so the Mac can re-verify it.
- **A daily alarm** deletes rows older than 30 days and advances `purged_through`, the highest `seq` ever purged, so a purge is never mistaken for a loss.

### 3. `src/comms/runtime/relay.py`: the collector, a new daemon loop

- It runs at start, then every 60 s, in the supervised `Workers` set with the recoverable failure class.
- **For each row, in `seq` order:**
  1. decrypt with the `relay-age-key` identity;
  2. verify Meta's signature with the app secret (the only place it is checked, D-R1), using the one shared function (see below);
  3. `Inbox.accept(raw)`;
  4. after the page's inbox commits, `/ack {through: last seq}`.
- A row that fails to decrypt or verify is **quarantined**: recorded in the audit log by `seq` and digest only, never acked and never deleted, and reported by `comms doctor`.
- **Crash safety:** a crash between the inbox commit and the ack re-pulls the same rows next time. There are two dedupe layers: the inbox's `ON CONFLICT` on the body's SHA-256, then the archive's `ON CONFLICT` on each message's `semantic_key`.
- **HTTP:** one new pinned network module, `src/comms/transports/whatsapp/relay_client.py` (`pinned_client` to the configured relay origin). It is added to `NETWORK_MODULES` in `tests/security/test_egress.py` and to the egress matrix.

### 4. One copy of the signature rule

The HMAC check leaves `WebhookIngress._signed` and becomes a module-level function in `src/comms/transports/whatsapp/webhooks/signature.py`, imported by the local ingress and the collector. The Worker holds no HMAC check (D-R1), so the rule keeps exactly one copy. The Worker's pull-signature check and the daemon's pull signer share `tests/fixtures/relay/pull_signature_vectors.json`, byte for byte.

### 5. Settings, keys, CLI, doctor

- **`comms.json`** gains `"relay": {"url": "https://comms-relay.<subdomain>.workers.dev"}`. With a relay set, the local webhook listener is not served. Without one, today's direct listener works as before.
- **Two new key purposes** (spec amendment A48, pinned in `purposes.py` and the wire-frozen tests):
  - `relay-age-key`: an X25519 `age` identity; only its public half leaves the Mac;
  - `relay-pull-key`: 32 random bytes shared with the Worker.

  Both are created by `comms keys provision`. `comms credential rotate relay-pull-key` covers both sides. On an `age` key rotation, the old identity stays decrypt-only until the mailbox is empty.
- **The pull signature** is `HMAC-SHA256(pull-key, "comms-relay-pull/v1\0" ‖ method ‖ "\0" ‖ path ‖ "\0" ‖ timestamp ‖ "\0" ‖ body)`, in the headers `X-Comms-Timestamp` and `X-Comms-Signature`.
  - The Worker refuses a timestamp more than 300 s from its clock.
  - Replay is harmless by construction (`/pull` is read-only ciphertext, `/ack` is idempotent), so there is no replay cache.
  - The domain string `comms-relay-pull/v1` is frozen.
- **`comms relay setup`** prints the recipient and the Worker secret names. Every secret is typed by the owner into `wrangler secret put` or `comms credential set`, so no secret passes through an AI transcript.
- **`comms doctor`** gains:
  - `RELAY_UNREACHABLE`;
  - `RELAY_STALE`: no successful pull for 10 minutes while running;
  - the mailbox depth;
  - `RELAY_BACKLOG_OLD`: the oldest queued row is more than 25 days old;
  - `RELAY_GAP`: a `seq` gap not covered by `purged_through`;
  - `RELAY_QUARANTINE`.

## Threat model

**Decision D-R1 (needs the owner's decision): Meta's app secret never goes to Cloudflare.** Whoever holds the app secret can make a validly signed webhook, so a Worker holding it would let a Cloudflare-account attacker forge messages the Mac accepts. Instead:
- Meta's callback URL carries an unguessable 32-byte path token;
- the Worker stores what arrives on it unverified (rate-limited, encrypted to the Mac);
- the Mac is the only verifier: an unsigned or mis-signed row is quarantined and never enters the inbox.

| If an attacker holds… | They can | They cannot |
|---|---|---|
| The Cloudflare account | Read ciphertext, delete or reorder rows, stop the Worker, inject junk (quarantined by the Mac) | Read a message (no `age` private key); forge a message (no app secret) |
| The path token (for example from a leaked Meta config) | Post junk up to the rate limit; the Mac quarantines it | Read or forge |
| The pull key alone | Pull ciphertext, ack (delete) rows | Read or forge |
| Network position | Nothing beyond TLS | — |

**Residual risks, named:**
- a Cloudflare-account holder can drop or delay messages;
- a leaked path token lets junk consume free-tier writes, until `comms relay rotate-path` issues a new token and the owner updates Meta's callback URL.

Gap detection catches accidental loss, not a determined account holder, who can also fake `purged_through`.

**The alternative, rejected unless the owner prefers it:** the Worker verifies the HMAC itself. That rejects junk at the edge, but it gives a Cloudflare compromise the power to forge messages.

## Error handling

- The Mailbox is unavailable, so the Worker answers 503 and Meta retries for 36 hours.
- A pull fails, so the collector retries on the next tick, and nothing is acked.
- A decrypt or verify failure is quarantined, as described in the collector section. Junk posted with a leaked path token lands here too, counted by `RELAY_QUARANTINE`.
- The inbox write fails, so there is no ack and the rows are re-pulled.
- A clock skew over 300 s makes every pull refused. `doctor` reports `RELAY_CLOCK`.
- The Durable Object free tier is exceeded (100,000 requests or writes a day), so the Worker answers 503 and Meta retries. At about 1,440 pulls a day plus one request per webhook, this is far off.

## Testing

- **Worker** (`relay/`, Vitest `^4.1.0` with `@cloudflare/vitest-plugin`, run in workerd):
  - each refusal and its order, including a wrong path token (404) and the absence of any app secret in the Worker's bindings;
  - signed storage and the 503 path;
  - `AUTOINCREMENT` after a drain;
  - storage of a body over 1 MiB;
  - the alarm purge with `purged_through`;
  - pull and ack signatures, stale timestamps and idempotent ack;
  - surviving `evictDurableObject`;
  - the Durable Object CPU budget on a 1 MiB body.
- **Cross-language:**
  - typage ciphertext decrypts with `core/backup/age.py`;
  - the shared signature and pull-signature vectors;
  - the canonical-JSON envelope.
- **Daemon** (pytest, scripted relay transport):
  - pull, decrypt, verify, accept, ack;
  - a crash between the inbox commit and the ack, with no duplicate;
  - a forged or tampered row quarantined, never acked;
  - a gap versus a purge;
  - `doctor` findings;
  - settings and egress pins;
  - the key purposes.
- **Smoke:** a real-daemon check against a local `wrangler dev` relay: a signed webhook is posted to the relay while the daemon is stopped, the daemon starts, and the message is read back once over MCP. The catalog sweep stays green.
- **Gate:** `(cd relay && npm ci && npx vitest run)` joins the gate.
- **Live check (owner-run, D39-B):** a real WhatsApp message while the Mac is off, present after it comes back.

## Evidence from the gauntlet (2026-09-27)

| Assumption | How it was tested | Result |
|---|---|---|
| A re-pulled row is harmless | `Inbox.store` (`ON CONFLICT` on the body's SHA-256), archive `semantic_key UNIQUE` | Two dedupe layers |
| typage output decrypts with the daemon's `age` | typage 0.3.1 in Node, then `core/backup/age.decrypt` | 1 MiB and small bodies byte-exact |
| typage works in workerd | A throwaway Durable Object under `wrangler dev` 4.141.0, then Python decrypt | Works |
| `seq` never repeats after a drain | Insert, delete all, insert again in Durable Object SQLite | 3, then 4 |
| Encryption belongs in the Durable Object | Node timing | About 1.8 ms small, about 40 ms for 1 MiB; over the Worker's 10 ms |

## Docs relied on (read 2026-09-27)

- **Cloudflare:**
  - Workers limits: 10 ms CPU on free, 5 KB per variable, 64 variables;
  - Queues on the free plan: 24 h retention, which rules them out;
  - Durable Objects pricing and limits: SQLite on free, 5 GB, 100,000 requests or writes a day, 2 MB per row, 100 KB per statement, 100 parameters, 30 s CPU per request;
  - Web Crypto support: X25519, HMAC, HKDF and AES-GCM, but not ChaCha20-Poly1305;
  - secrets and `secrets.required`;
  - `@cloudflare/vitest-plugin` v1;
  - `wrangler dev` known issues.
- **Meta (Graph API webhooks):** the `X-Hub-Signature-256` HMAC-SHA256 with the app secret, a valid TLS certificate, the verify handshake, batches of up to 1000, retries over 36 hours.
- **SQLite:** `AUTOINCREMENT` guarantees.
- **typage README:** runtimes, the Web Crypto X25519 identity, the Encrypter API.

## Out of scope

- Telegram: it needs no relay.
- Multiple Macs pulling from one mailbox.
- Delivering to the daemon by push while it runs; polling every 60 s is enough.
- A paid plan: a real message is small, and a batch over the Durable Object's CPU is not expected. If the CPU test ever fails, the Workers Paid plan ($5) is the named fallback.
