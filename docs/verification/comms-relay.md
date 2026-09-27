# The WhatsApp relay: evidence (spec A48)

Branch `comms-relay`.
- **Plan:** `docs/superpowers/plans/2026-09-27-comms-whatsapp-relay.md`.
- **Design:** `docs/superpowers/specs/2026-09-27-comms-whatsapp-relay-design.md`, approved by the owner on 2026-09-27 with D-R1.
- **Rulings:** R-R0 to R-R5 in `comms-v0.3-rulings.md`.
- **Runbook:** `docs/runbooks/whatsapp-relay.md`.

## What it does

The daemon can now run on demand without losing WhatsApp messages. A Cloudflare Worker, `relay/`, receives Meta's webhooks on a secret path. It stores each one `age`-encrypted to the Mac in one SQLite Durable Object, for 30 days. The daemon pulls with signed requests every 60 seconds, then:

1. decrypts;
2. verifies Meta's `X-Hub-Signature-256`, the only place it is checked (D-R1: the relay never holds the app secret);
3. stores the body through the existing inbox;
4. moves its progress forward, then acks.

A refused row is quarantined on the Mac with its ciphertext.

## Tasks and their tests

| Task | What | Owning tests |
|---|---|---|
| R0 | A48, `relay-age-key` (new kind `x25519`, rotation refused), `relay-pull-key`, the frozen `comms-relay-pull/v1` with 8 vectors; one key-id rule in `slots` | `tests/core/test_relay_sig.py`, purposes, wire-frozen, provision |
| R1 | Meta's signature rule in one place (`webhooks/signature.py`); the listener takes 8 MiB | `tests/transports/whatsapp_webhooks/test_signature.py` |
| R2 | The Worker and the Mailbox; the export defect found under `wrangler dev` | 15 Vitest tests in workerd; `tests/security/test_relay_static.py` |
| R3 | The relay client, the collector, schema v9, the settings, the wiring | `tests/runtime/test_relay_collector.py`, `test_relay_wiring.py`, `tests/transports/test_relay_client.py` |
| R4 | `comms relay recipient\|export-pull-key\|new-path\|status\|setup`; the doctor's relay findings | `tests/runtime/test_relay_operator.py`, `tests/core/test_doctor_relay.py` |
| R5 | Two real-daemon checks against `wrangler dev`; the runbook; this page | `tests/runtime/test_selftest_relay.py`, `tests/security/test_relay_exit.py` |

## Executed, not only read

- **The real Worker under `wrangler dev`, with the real selftest daemon.** A signed webhook and a forged one are posted while the daemon is stopped. The daemon then starts:
  - it reads the signed one back over MCP (`comms_context_person`), exactly once;
  - it quarantines the forged one;
  - the mailbox drains to depth 0;
  - `audit verify --all` stays clean.

  These are the D39-A checks "a webhook the relay held while the daemon was off is read over MCP once it starts" and "an unsigned delivery through the relay is quarantined, never inboxed, and the mailbox drains". The Worker's secrets come from the daemon's own keys through the installed CLI's pipes.
- **Ciphertext across languages.** typage in workerd encrypts and `core/backup/age.py` decrypts: a captured page (`tests/fixtures/relay/wrangler_dev_page.json`) and the live smoke.
- **The pull signature.** The same 8 vectors are checked in Python and in workerd.
- **A defect found only by running it:** workerd refuses a main module that exports a constant (R-R2).

## Limits, named

- **Owner-run steps:**
  - `wrangler login`;
  - putting the four Worker secrets (`comms relay setup` prints them in order);
  - `wrangler deploy`;
  - setting Meta's callback URL.

  No secret passes through an AI transcript: the pull key and the path token go only into pipes.
- **Live acceptance (D39-B, owner-run):** a real WhatsApp message sent while the Mac is off is present once it is back.
- **What a Cloudflare-account holder can do:** delay or delete messages. Deletions show as `RELAY_GAP` unless they fake `purged_through`. They can never read or forge a message.
- **Rotating the `age` key** is refused in this version.
- **The Durable Object's CPU time** could not be measured under test, because the Workers clock stops during CPU work. It rests on about 40 ms per MiB in Node, against a 30 s budget.
