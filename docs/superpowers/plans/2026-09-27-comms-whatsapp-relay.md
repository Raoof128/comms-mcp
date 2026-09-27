# Comms WhatsApp relay: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner's standing rule for this repo: no subagents; the main session executes, test-first, inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WhatsApp webhooks land in an always-on Cloudflare mailbox, encrypted to the Mac, so the comms daemon can run on demand and still archive every message exactly once.

**Architecture:**
- **Cloudflare side:** a Cloudflare Worker (`relay/`) accepts Meta's webhooks on a secret path. It holds no app secret (D-R1). It hands raw bytes and the signature header to one SQLite Durable Object, which `age`-encrypts them to the Mac's X25519 key and stores them under an `AUTOINCREMENT` `seq`, purging after 30 days.
- **Mac side:** a new daemon loop pulls signed pages, decrypts, verifies Meta's HMAC (the only place it is checked), writes through the existing `Inbox`, and only then acknowledges.

**Tech Stack:**
- **Relay:** TypeScript on Workers; `age-encryption` (typage) 0.3.x; `wrangler` 4.x; Vitest `^4.1.0` with `@cloudflare/vitest-plugin`.
- **Mac:** Python 3.12 with the existing `comms.core.backup.age`, `httpx` (pinned client), SQLCipher and pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-comms-whatsapp-relay-design.md` (approved 2026-09-27, with D-R1: the app secret stays off Cloudflare).

## Global Constraints

- **Branch and approvals.** Work on branch `comms-relay`. Merge, push, tag push and `wrangler deploy` only with the owner's approval.
- **Commits.** Commit only when the full gate log shows `GATE ok=1`. Write nothing in-tree while a gate runs.
- **Secrets.** Never commit, log or print a secret. The pull key and the path token reach Wrangler only through a pipe (`comms relay export-pull-key | npx wrangler secret put RELAY_PULL_KEY`), never on screen or in a transcript. `relay/.dev.vars` and `relay/.wrangler/` are gitignored.
- **D-R1.** The Worker's bindings never include Meta's app secret. A test asserts it.
- **One copy of each rule.** Meta's signature check exists once, in `webhooks/signature.py`. The pull signature has one Python copy and one TypeScript copy, bound by a shared vector file.
- **Fail closed.** Anything undecryptable or unverified is quarantined, never acked, never deleted.
- **Frozen wire.** `comms-relay-pull/v1`, the pull-signature layout and the Mailbox table. Changing any of them is a new version.
- **Limits.** An accepted body is at most 8 MiB, a Mailbox row at most 1 MiB of plaintext (Durable Object rows cap at 2 MB), a pull page at most 50 rows or 256 KiB. Retention is 30 days, the pull runs every 60 s, and the timestamp window is 300 s.
- **Audit trail.** Add dated `**Raouf:**` entries to AGENT.md and CHANGELOG.md, a ledger line per task, and rulings R-R1 onward.

## Review Focus

1. **Meta sends a batch larger than 1 MiB.** It is stored as parts, and the Mac reassembles one body only when every part is present, then verifies it once. Test: R2 step 1 `test_a_large_batch_is_stored_in_parts`, R3 step 1 `test_parts_reassemble_into_one_verified_body`.
2. **The daemon crashes after the inbox commit and before the ack.** The next run re-pulls the rows, stores nothing new, and acks. Test: R3 `test_crash_between_commit_and_ack_duplicates_nothing`.
3. **Junk arrives on a leaked path.** It is quarantined, never reaches the inbox, and `doctor` counts it. Test: R3 `test_junk_is_quarantined_not_acked_not_inboxed`.
4. **The Mac's clock is skewed.** Every pull is refused with 401; `doctor` says `RELAY_CLOCK`, and nothing is acked. Test: R4 `test_clock_skew_is_reported`.
5. **The relay is unreachable for hours while the daemon runs.** Each tick fails quietly, `RELAY_STALE` appears after 10 minutes, and everything arrives on reconnect. Test: R3 `test_an_unreachable_relay_loses_nothing`.

---

### Task R0: Spec amendment A48, key purposes, the frozen pull signature

**Files:**
- `docs/comms-spec-v0.3.md`: add A48 (the relay, D-R1, the two key purposes, the frozen domain).
- `docs/verification/comms-v0.3-rulings.md`: a new spec pin, and R-R0.
- `src/comms/core/keys/purposes.py`: `Kind` gains `"x25519"`; two new purposes, `_p("relay-age-key", "x25519", "new_id", False, "at_rotation")` (a first version only: rotating it is refused in this version) and `_p("relay-pull-key", "hmac", "new_id", False, "at_rotation")`.
- `src/comms/core/keys/ids.py`: `x25519_key_id(public: bytes) -> str`, following the `<kind>:sha256:<64 hex>` rule.
- `src/comms/core/keys/slots.py`: `key_id_for` handles `x25519` (the public half comes from `X25519PrivateKey.from_private_bytes`).
- `src/comms/runtime/provision.py`: `PROVISIONED_KEYS` gains both.
- `src/comms/core/domains.py`: `RELAY_PULL = b"comms-relay-pull/v1\0"`.
- `src/comms/core/relay_sig.py` (new): the one Python pull signer.
- `src/comms/core/backup/age.py`: `identity_from_raw(raw: bytes) -> str`.
- `tests/fixtures/relay/pull_signature_vectors.json` (new, generated by the signer and committed).
- Tests: `tests/core/test_relay_sig.py`, `tests/security/test_comms_wire_frozen.py`, `tests/core/keys/test_purposes.py`.

**Interfaces produced:**
- `relay_sig.sign(key: bytes, method: str, path: str, timestamp: int, body: bytes) -> str` (lowercase hex).
- `relay_sig.verify(key, method, path, timestamp, body, signature, *, now: int, window: int = 300) -> bool`.
- `age.identity_from_raw(raw) -> "AGE-SECRET-KEY-1…"`.

- [ ] **Step 1: Failing tests.**

```python
from comms.core import relay_sig
from comms.core.backup import age

KEY = bytes(range(32))

def test_the_signature_is_the_frozen_layout():
    body = b'{"after":0,"limit":50}'
    expected = hmac.new(KEY, b"comms-relay-pull/v1\0POST\0/pull\0" + b"1790000000\0" + body,
                        hashlib.sha256).hexdigest()
    assert relay_sig.sign(KEY, "POST", "/pull", 1790000000, body) == expected

def test_verify_refuses_stale_and_altered():
    sig = relay_sig.sign(KEY, "POST", "/ack", 1000, b"{}")
    assert relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig, now=1200)
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig, now=1301)  # > 300 s
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b'{"through":9}', sig, now=1000)

def test_the_vector_file_matches_the_signer():
    for v in json.loads(VECTORS.read_text()):
        assert relay_sig.sign(bytes.fromhex(v["key"]), v["method"], v["path"], v["timestamp"],
                              bytes.fromhex(v["body"])) == v["signature"]

def test_an_age_identity_from_raw_round_trips():
    identity = age.identity_from_raw(bytes(32))
    assert age.decrypt(age.encrypt(b"x", [age.recipient_of(identity)]), identity) == b"x"
```

Plus: `PURPOSES` holds both new purposes with the kinds above; `comms-relay-pull/v1` is pinned in the wire-frozen test; `provision` creates both.
- [ ] **Step 2:** Run the tests and watch them fail.
- [ ] **Step 3:** Implement. The signer is:

```python
def _message(method: str, path: str, timestamp: int, body: bytes) -> bytes:
    return domains.RELAY_PULL + b"\0".join(
        (method.encode("ascii"), path.encode("ascii"), str(int(timestamp)).encode("ascii"), body))
def sign(key, method, path, timestamp, body):
    return hmac.new(key, _message(method, path, timestamp, body), hashlib.sha256).hexdigest()
def verify(key, method, path, timestamp, body, signature, *, now, window=300):
    if not isinstance(signature, str) or abs(int(now) - int(timestamp)) > window:
        return False
    return hmac.compare_digest(sign(key, method, path, timestamp, body), signature)
```

Generate eight vectors (edge bodies: empty, 1 byte, UTF-8, 64 KiB) with a one-off script, and commit them.
- [ ] **Step 4:** Pin the spec in the rulings register (the preflight test), then run the gate and commit.

### Task R1: One copy of Meta's signature, and the local cap fixed

**Files:**
- `src/comms/transports/whatsapp/webhooks/signature.py` (new): `meta_signed(secret: bytes, raw: bytes, header: bytes | None) -> bool`.
- `src/comms/transports/whatsapp/webhooks/ingress.py`: `_signed` delegates to it; `MAX_BODY_BYTES = 8 * 1024 * 1024`, since Meta sets no limit and batches up to 1000 updates.
- Tests: `tests/transports/whatsapp_webhooks/test_signature.py`, plus the existing ingress tests.

- [ ] **Step 1: Failing tests.**
  - `meta_signed` accepts `sha256=<hex of HMAC-SHA256(secret, raw)>`.
  - It refuses a missing header, a wrong prefix, an uppercase hex copy, a truncated one, or one signed over altered bytes.
  - The ingress module holds no `hmac.new` of its own (an AST check).
  - A signed 2 MiB body is accepted by the local ingress (it used to be refused 413).
- [ ] **Steps 2 to 4:** Watch them fail, implement, watch them pass. Run the gate and commit.

### Task R2: The Worker and the Mailbox (`relay/`)

**Files (new):**
- `relay/package.json`: pinned exact versions of `age-encryption`, `wrangler`, `vitest@^4.1.0`, `@cloudflare/vitest-plugin` and `typescript`.
- `relay/package-lock.json`.
- `relay/wrangler.jsonc`: `name: comms-relay`; a Durable Object binding `MAILBOX`/`Mailbox`; a `new_sqlite_classes: ["Mailbox"]` migration; `secrets.required: ["RELAY_PATH_TOKEN", "META_VERIFY_TOKEN", "RELAY_PULL_KEY"]`; a plain variable `RELAY_AGE_RECIPIENT`; `compatibility_date: "2026-09-01"`.
- `relay/src/index.ts`: the routes, the path-token check, the rate bound, and the pull-signature check.
- `relay/src/mailbox.ts`: the Durable Object — table, encryption, parts, pull, ack, alarm.
- `relay/src/pull_sig.ts`: the TypeScript copy of the pull signer, using Web Crypto HMAC.
- `relay/test/*.test.ts` and `relay/vitest.config.ts`.
- `relay/.dev.vars.example`, holding test values only.

**Also modified:** `.gitignore` gains `relay/node_modules/`, `relay/.wrangler/` and `relay/.dev.vars`.

**Interfaces (the frozen wire):**
- `POST /webhooks/meta/:token`.
- `GET /webhooks/meta/:token?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…`.
- `POST /pull {after: int, limit: int ≤ 50}` returns `{rows: [{seq, received_at, batch, part, parts, ciphertext_b64}], purged_through: int}`.
- `POST /ack {through: int}` returns `{deleted: int}`.
- Pull requests carry `X-Comms-Timestamp` and `X-Comms-Signature`.
- The plaintext of each row is the canonical JSON `{"raw_b64": …, "signature": "sha256=…", "received_at": <unix ms>}`. For a body over 1 MiB, the raw bytes are split across parts before encryption, and each part carries `raw_b64` of its slice; the signature header travels in part 0.

**The Mailbox, in sketch:**

```ts
export class Mailbox extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      ctx.storage.sql.exec(`CREATE TABLE IF NOT EXISTS mail (seq INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at INTEGER NOT NULL, batch TEXT NOT NULL, part INTEGER NOT NULL,
        parts INTEGER NOT NULL, ciphertext BLOB NOT NULL)`);
      ctx.storage.sql.exec(`CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v INTEGER NOT NULL)`);
      if ((await ctx.storage.getAlarm()) === null) await ctx.storage.setAlarm(Date.now() + DAY);
    });
  }
  async store(raw: ArrayBuffer, signature: string): Promise<void> { /* split at 1 MiB; encrypt each part with age.Encrypter + RELAY_AGE_RECIPIENT; INSERT … */ }
  pull(after: number, limit: number) { /* SELECT … WHERE seq > ? ORDER BY seq LIMIT ?, capped at 256 KiB; purged_through from meta */ }
  ack(through: number) { /* DELETE FROM mail WHERE seq <= ? */ }
  async alarm() { /* DELETE rows older than 30 days, raise purged_through, set the next alarm */ }
}
```

- [ ] **Step 1: Failing Vitest tests.**
  - A wrong path token is 404, a non-JSON body 415, a missing or malformed signature header 401, a body over 8 MiB 413, and a burst beyond the rate bound 429.
  - A good POST answers 200 only after storage. With `store` made to throw, the answer is 503.
  - The GET handshake echoes the challenge with the right token and is 403 with a wrong one.
  - After storing, draining and storing again, the new `seq` is greater than the old one (`AUTOINCREMENT`).
  - `test_a_large_batch_is_stored_in_parts`: 2.5 MiB becomes three rows sharing one batch id.
  - The alarm (`runDurableObjectAlarm`) deletes a row older than 30 days and raises `purged_through`.
  - `/pull` and `/ack` refuse a bad or stale signature (401). An ack repeated twice deletes nothing the second time.
  - The Mailbox survives `evictDurableObject`.
  - `env` has no key that looks like an app secret (D-R1).
  - `pull_sig.ts` reproduces every entry in `tests/fixtures/relay/pull_signature_vectors.json`.
  - Round trip: a test writes `relay/test/out/typage.age`, encrypted to the committed test-only recipient in `tests/fixtures/relay/test_identity.txt`, for Python to decrypt in R3.
- [ ] **Step 2:** Run `(cd relay && npm ci && npx vitest run)` and watch it fail.
- [ ] **Step 3:** Implement `index.ts`, `mailbox.ts` and `pull_sig.ts`.
- [ ] **Step 4:** Watch the tests pass. Measure a 1 MiB `store` in the Durable Object through the Vitest integration and record the time in R-R2. Add `(cd relay && npm ci && npx vitest run)` to the gate, then run the gate and commit.

### Task R3: The collector (the Mac side)

**Files:**
- `src/comms/transports/whatsapp/relay_client.py` (new): `RelayClient(base_url: str, pull_key: bytes, *, transport=None)`, with `pull(after: int, limit: int) -> RelayPage` and `ack(through: int) -> int`. It uses `pinned_client(base_url)` and raises only `RelayUnavailable(stage)` or `RelayRefused(status)`, with fixed messages.
- `src/comms/runtime/relay.py` (new): `Collector(conn, client, inbox, *, identity: str, app_secret: bytes, clock, audit)` with `run_once() -> CollectReport(pulled, stored, quarantined, acked_through)`.
- `src/comms/runtime/settings.py`: `_TOP` gains `"relay"` (`{"url": https}`), and `DaemonSettings.relay_url`.
- `src/comms/runtime/adapters.py` and `workers.py`: with a relay URL set, the webhook listener is not built and `Loop("relay", collector.run_once, 60.0, False)` runs.
- `tests/security/test_egress.py`: `NETWORK_MODULES` gains `transports/whatsapp/relay_client.py`.
- Migration v9: `relay_state(k TEXT PRIMARY KEY, v)` for `last_pull_at`, `acked_through`, `purged_through` and `seen_max`; `relay_quarantine(seq PRIMARY KEY, digest, reason, at)`.
- Tests: `tests/runtime/test_relay_collector.py` and `tests/transports/test_relay_client.py`.

**Interfaces consumed:** `relay_sig.sign`; `age.decrypt(ciphertext, identity)`; `signature.meta_signed`; `Inbox.store(raw) -> bool`.

- [ ] **Step 1: Failing tests** (a scripted `httpx.MockTransport` relay that holds rows):
  - `test_rows_are_decrypted_verified_inboxed_then_acked`: the ack goes after the commit, and `acked_through` equals the last `seq`.
  - `test_crash_between_commit_and_ack_duplicates_nothing`: raise after `Inbox.store` and before `ack`; the second run stores nothing new and acks.
  - `test_junk_is_quarantined_not_acked_not_inboxed`: an unsigned body, a wrong signature, undecryptable ciphertext.
  - `test_parts_reassemble_into_one_verified_body`: three parts arriving across two pages; nothing is stored until every part is present.
  - `test_a_gap_not_covered_by_purge_is_recorded`, and a purge-covered gap is not.
  - `test_an_unreachable_relay_loses_nothing`: a connect error on the tick, then success.
  - `test_typage_ciphertext_decrypts`: reads R2's committed fixture ciphertext.
  - The relay client refuses a non-https URL, redirects and other hosts (the pinned client).
  - Settings accept `relay.url` and refuse `http://`.
  - With a relay URL, `serve` builds no webhook listener.
- [ ] **Steps 2 to 4:** Watch them fail, implement, watch them pass. Run the gate and commit.

### Task R4: Operator commands and doctor

**Files:**
- `src/comms/runtime/operator/relay.py` (new).
- `src/comms/cli_commands/…` (registration, following the existing operator pattern).
- `src/comms/core/doctor.py`.
- Tests: `tests/runtime/operator/test_relay.py` and `tests/core/test_doctor_relay.py`.

**Commands:**
- `comms relay recipient`: prints the public `age1…` key, which is not a secret.
- `comms relay export-pull-key`: writes the raw key as hex to stdout only when stdout is **not** a TTY, so it can only go into a pipe. On a TTY it refuses with "pipe it into: npx wrangler secret put RELAY_PULL_KEY".
- `comms relay new-path`: 32 random bytes as base64url; the same pipe-only rule.
- `comms relay setup`: prints the ordered checklist.
  1. `cd relay && npm ci`.
  2. The two pipes above.
  3. `npx wrangler secret put META_VERIFY_TOKEN`, typed by the owner.
  4. `npx wrangler deploy`.
  5. Set the callback URL `https://comms-relay.<sub>.workers.dev/webhooks/meta/<token>` in Meta's WhatsApp Configuration.
  6. Put `relay.url` in `comms.json`.

**Doctor findings:** `RELAY_UNREACHABLE`, `RELAY_STALE` (over 10 min), `RELAY_BACKLOG_OLD` (over 25 days), `RELAY_GAP`, `RELAY_QUARANTINE` (a count), `RELAY_CLOCK` (the relay answered 401 with a server `Date` more than 300 s from local).

- [ ] **Step 1: Failing tests.**
  - `export-pull-key` refuses on a TTY and writes on a pipe.
  - Each doctor finding appears from a seeded `relay_state` or a scripted relay.
  - `test_clock_skew_is_reported`.
  - No command ever prints the pull key or path token to a TTY.
- [ ] **Steps 2 to 4:** Watch them fail, implement, watch them pass. Run the gate and commit.

### Task R5: End to end, the runbook, the evidence

**Files:**
- `scripts/smoke_daemon.py` and `scripts/e2e_smoke.py`: `phase_v03_daemon` gains `relay_offline_catchup`:
  - start `npx wrangler dev` in `relay/`, with `.dev.vars` written to a temporary directory holding test values;
  - post a Meta-signed body to it while the daemon is stopped;
  - start the daemon with `relay.url` set to the dev URL;
  - read the message back over MCP once, and confirm the mailbox is empty.
  - When `relay/node_modules` is absent, the check fails with that reason. It never reports success.
- `docs/runbooks/whatsapp-relay.md` (new): deploy, rotate the pull key or path, suspect-account steps (rotate Meta's app secret and purge the relay-delivered window).
- `docs/verification/comms-relay.md` (new) with the counts.
- `tests/security/test_relay_exit.py`: the checklist from this plan's headings, re-run with nothing skipped.
- `docs/verification/comms-v0.3-smoke-map.json`.
- `tests/security/test_d39_pre_exit.py` (the daemon check count).
- `CLAUDE.md` (the Verify block adds the relay line).
- AGENT.md, CHANGELOG.md, the ledger.

- [ ] **Step 1:** Write the smoke check and the exit test, and watch both fail.
- [ ] **Step 2:** Make them pass, run the full gate, commit, and add a local tag `comms-relay-v1`.
- [ ] **Step 3:** Ask the owner before merging, pushing and `wrangler deploy`. The deployment needs the owner's own `wrangler login` and secret entry.

## Not in this plan

Multiple Macs pulling from one mailbox, a paid-plan-only design, and push delivery to a running daemon (the spec's out-of-scope list).
