# Comms Pinterest actor (A50): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner's standing rule for this repo: no subagents; the main session executes, test-first, inline. Read `CLAUDE.md`, `AGENT.md` and `CHANGELOG.md` before the first edit.

**Goal:** one more comms actor, `pinterest`, serving 18 `comms_pinterest_*` tools over the existing daemon, proxy, executor, secret store and audit chain, so the owner's AI assistant can read boards, Pins and analytics, and publish image, carousel and video Pins to the owner's Pinterest business accounts, with every write audited.

**Spec:** `docs/pinterest-spec-v0.1.md` (revision 1, proposed amendment A50). Section 12 lists every code change; this plan sequences them. The spec wins over this plan; a contradiction stops the task and is recorded as a ruling (A39).

**Architecture:** the Instagram actor's (A49), file for file: a transport package `src/comms/transports/pinterest/`, one service `src/comms/runtime/pinterest.py`, one catalog module `src/comms/mcp/tools/pinterest.py`, one operator module `src/comms/runtime/operator/pinterest.py`. No executor, recovery, relay or proxy change.

## Global constraints

- **Branch:** `comms-pinterest`. Merge, push and the ruling R-PN0 only with the owner's approval.
- **Commits** only when the full gate (`CLAUDE.md` Verify) is green.
- **Secrets.** An authorization code reaches `comms transport pinterest account add` only at the hidden prompt. Never commit, log or print a token, a code, the app secret or an upload parameter. Tests use fake tokens of the documented shape (`pina…`, `pinr…`).
- **Fail closed.** `UNKNOWN` is never `AVAILABLE`; a rejected proof leaves the working slot active; a classifier miss is `OUTCOME_UNKNOWN`.
- **One copy of each rule.** `public_url` stays in `transports/instagram/urls.py` and is imported; the alias grammar in `core/keys/purposes.py`; the status table in `classify.py`; the metric tables in `core/providers/pinterest_analytics.py`.
- **Every call fits 30 s.** No tool sleeps or polls. At most three network calls per tool (D-P13).
- **Egress.** `transports/pinterest/http.py` and `upload.py` are the only new `NETWORK_MODULES` entries. Core never imports a transport; `transports/pinterest` imports from `transports/instagram` only `urls.public_url` and from `transports/whatsapp/cloud/http` only the shared response and error types.
- **Typed egress (A44).** Identities never leave except through `comms_admin_identity_inspect`. Bodies only under `untrusted` and `untrusted_text`.
- **Pins move on purpose.** `tests/mcp/catalog_pin.json` regenerates once per task that changes the catalog; the ledger line records both digests.
- **Audit trail.** A dated `**Raouf:**` entry in `AGENT.md` and `CHANGELOG.md`; rulings R-PN1 onward in `docs/verification/comms-v0.3-rulings.md`; the spec and this plan pinned there.

## Review focus

1. **A write replayed under the same `request_id` makes no second provider effect** at every `crash_at` point (`test_pin_create_replay_makes_one_pin`).
2. **The wrong account cannot write.** `account` is required; a `pnb_` of another account is `NOT_FOUND` before anything is recorded; `writes: false` refuses before any call.
3. **No token, code, app secret or upload parameter in a URL, log, repr, error, audit row or tool result** (`test_token_only_in_authorization_header`, `test_upload_carries_no_bearer`, the operator leak sweep).
4. **The budget holds before Pinterest** (`test_pin_budget_refuses_before_provider`).
5. **A video Pin is created only on `succeeded`** (`test_video_pin_waits_for_processing`).

---

### Task PN-0: Pre-flight and pins
- `docs/verification/comms-v0.3-rulings.md`: pin the SHA-256 of `docs/pinterest-spec-v0.1.md` and this plan; ruling R-PN1 (pre-flight).
- `tests/security/test_v03_preflight.py`: the Pinterest spec joins the pinned documents.

### Task PN-1: The actor exists
Spec sections 3, 4, 12 items 1 to 3, 5 (settings, adapters, operator), 6 (http, upload, config, store, accounts, capability, doctor).
- Enums, prefixes, purposes, audit actor and event, migration v12, settings, `PinterestApi`, `upload.py`, accounts and the lazy identity check, capability, doctor findings, the operator commands (`auth-url`, `account add|list|remove`, `token refresh`, `doctor`), the app-secret proof.
- Tests: `tests/transports/pinterest/{fakes,test_http,test_upload,test_config_purposes,test_store,test_capability}.py`, `tests/runtime/operator/test_pinterest_accounts.py`, `tests/core/providers/test_protocols.py` (`_pinterest_ids`), `test_semantics.py`, `tests/core/keys/test_purposes.py`.

### Task PN-2: Reads
Spec sections 5.1, 7, 12 items 4 to 6.
- `items.py`, `core/providers/pinterest_analytics.py`, `runtime/pinterest.py` (reads, client-bound bookmarks), `mcp/tools/pinterest.py` (13 reads), facades, egress, identity inspect, the actor matrix table.
- Tests: `tests/transports/pinterest/world.py`, `tests/runtime/test_pinterest_reads.py`.

### Task PN-3: Writes
Spec sections 5.2, 6, 8, 9.
- `classify.py`, `publish.py`, `admin.py`, the five write tools with `requires_user_interaction` on three, `.claude/settings.json`, the service's write path, preview and quota.
- Tests: `tests/transports/pinterest/test_classify.py`, `tests/runtime/test_pinterest_writes.py`.

### Task PN-4: Doctor, smoke, runbook, exit test
Spec section 11.
- `comms doctor` offline findings; `runtime/selftest.py` scripted Pinterest; `scripts/smoke_daemon.py` `drive_pinterest`; `scripts/e2e_smoke.py`; `scripts/smoke_sweep.py`; the smoke map; `tests/conformance/pinterest.py`; `docs/runbooks/live-acceptance-pinterest.md`; `tests/security/test_pinterest_exit.py`; `README.md`, `CLAUDE.md`.

### Task PN-5: Owner steps (not for the agent)
- Create the Pinterest app (business account), request Trial access, register the redirect URI, set the app secret: `comms credential set pinterest-app-secret`.
- `comms transport pinterest auth-url sarabi`, sign in, `comms transport pinterest account add sarabi` with the code at the hidden prompt; `comms transport pinterest doctor`.
- Run GP-1 to GP-7 per the runbook; request Standard access with the OAuth demo; ruling R-PN0.

## Not in this plan
Ads, catalogs, board sections, secret boards, saves of others' Pins, search, automatic refresh in the daemon, videos over 16 MiB, webhooks (spec D-P10).
