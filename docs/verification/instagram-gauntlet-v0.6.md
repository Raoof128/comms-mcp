# Gauntlet report: SPEC v0.6 (Instagram for comms, proposed amendment A49)

**Run:** 4 October 2026, against `docs/instagram-spec-v0.6.md` at `d9b6aa9` in `Raoof128/telegram-mcp` and its mirror `SPEC.md` at `52759c5` here.
**What this gauntlet covers.** The Meta, MCP and Claude Code facts in v0.6 were verified first-hand earlier today (`GAUNTLET-v0.5.md`), so they are checked here only for faithful transcription. The new material is what v0.6 claims about **comms itself** (amendments, modules, enums, tests, settings), its **internal consistency**, and the **Python SDK** claims. The SDK claims were driven live.

**Legend:** ✅ confirmed, ❌ wrong, 🔧 tighten, 🛠️ a code change the spec implies but does not state, 🧪 stays a gate.

---

## 0. Verdict

**The actor design holds. The spec is not yet adoptable as written.** Every Meta, MCP and Claude Code fact transcribed from the v0.5 gauntlet is correct (no ❌ re-introduced), and the Python SDK and proxy claims passed a live run. What fails is the fit to comms' executor: D-I7's `IN_FLIGHT` and resume story describes behaviour the mutation executor does not have, and the spec lists none of the 14 code changes the design needs. A rev 2 of v0.6 should land before ruling R-IG0.

| Area | ❌ | 🔧 | 🛠️ unstated code changes |
|---|---|---|---|
| A. Python SDK and proxy (live) | 0 | 2 | 1 (`http.py` must pass `meta=`) |
| B. Claims about comms | 8 | 14 | 14 |
| C. Transcription from v0.5 | 0 (1 mis-transcribed TS name, 1 missing rule) | 16 inconsistencies | — |

### What must change before adoption

1. **Rewrite D-I7 and section 6.** Today `IN_FLIGHT` is a mutation's birth state, never a caller-visible result except with `AUDIT_INTEGRITY_DEGRADED`; the executor runs every saga step to completion; `recover_mutations` settles an `IN_FLIGHT` step as `OUTCOME_UNKNOWN` at startup; resume is replay of the same `request_id`, not by `op_ref`; and step records hold no provider ref. Either specify the executor extension (a deliberate pending-exit, by-`op_ref` resume, per-step `provider_ref` persistence, a recovery exemption) as explicit work in MI-4, or drop `IN_FLIGHT` and make a processing Reel a plain `FAILED CONTAINER_NOT_READY` that the owner retries with a new `request_id` against the same container id returned in `detail`.
2. **Fix the retry contradiction (I-1).** Section 8 promises retries and "new container" paths that a resolve-only CREATE saga forbids. Make retries step-scoped (status poll, publish of the same `creation_id`) and every "new container" a new `request_id`.
3. **State the 14 code changes** (B.6) in a new section, with the pins they move: the whole `catalog_pin.json` (the `ACTOR` enum ripple), the typed audit payload actor set, schema migration v9, the parameterised purposes, settings, the actor matrix parser.
4. **Correct the wrong file and mechanism names:** `test_egress.py` is an httpx-import allowlist, not an origin list; `e2e_smoke.py` drives the retired demo, the sweep is `smoke_sweep.py` over `/mcp`; `test_redaction.py` is legacy Telegram; `docs/verification/live-acceptance/` is an evidence path, not a convention directory; `ctx.mcpReq.signal` is a TypeScript name.
5. **Gate wording:** GI-1 must name the refresh call, whose only documented form carries the token in the URL; GI-7 and GI-6 lose their SDK halves (closed here); GI-4 drops `media_product_type`; GI-8 gets its write side in MI-3.

### Closed by this run
- GI-7's SDK half: the lowlevel `Server` the proxy uses served a legacy `initialize`, a modern `server/discover` and a bare modern `tools/list` in one process.
- GI-6's SDK half: a tool `_meta` entered through `ListToolsResult.model_validate` and left on the wire in all three eras. The remaining work for `_meta` is in the daemon (`http.py`), not the SDK.

---

## A. Python SDK and the stdio proxy (sections 0, 11, 13; gates GI-6, GI-7)

Live run on `mcp` 2.2.0 and `mcp-types` 2.2.0 from comms' own `uv` environment. The test server is a copy of `build_server` in `src/comms/mcp/stdio_proxy.py` (lowlevel `Server` with `on_list_tools` returning `ListToolsResult.model_validate(payload)`, served by `stdio_server()`), with a `tools/list` payload whose first tool carries `"_meta": {"anthropic/requiresUserInteraction": true}`.

| Claim | Verdict | Evidence |
|---|---|---|
| `mcp-types` 2.2.0 is dual-era | ✅ | `KNOWN_PROTOCOL_VERSIONS` ends `2025-11-25, 2026-07-28`; `MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)`; `DEFAULT_NEGOTIATED_VERSION = "2025-03-26"` |
| The proxy speaks 2026-07-28 to the daemon | ✅ | `PROTOCOL_VERSION = "2026-07-28"` and the envelope keys in `http_post` |
| The proxy's host side handles both eras | ✅ live | A legacy `initialize` (2025-06-18) negotiated `2025-06-18`; a modern `server/discover` returned `supportedVersions: ["2026-07-28"]`; a bare modern `tools/list` with the envelope was served. The lowlevel `Server` has a default `server/discover` handler (`_handle_discover`) and reserves `initialize` for the runner |
| `_meta` on a tool reaches the host through the proxy | ✅ live | `Tool.meta` is `Field(alias="_meta")`; `ListToolsResult.model_validate` accepted it and all three eras emitted `"_meta": {"anthropic/requiresUserInteraction": true}` on the wire |
| `tools/call` passes through unchanged | ✅ live | `{"content":[...],"isError":false}` in both eras; the modern era adds `resultType` and the `serverInfo` envelope |
| "Nothing Instagram-specific is added to the proxy" | ✅ | The proxy forwards `tools/list` and `tools/call` verbatim; a new `_meta` key needs no proxy change |

**Consequence for the gates.** GI-7's SDK half is closed (the proxy itself is dual-era), and GI-6's SDK half is closed (the flag reaches the host). What remains in both is only "Claude Code and Desktop actually connect and honour it", which is a smoke test, not an unknown. Section 13 should say so.

---

## B. Claims about comms (sections 0 to 5, 8 to 13)

Checked against `src/comms/...`, `tests/...` and `docs/comms-spec-v0.3.md` at `3f6df9a`. Paths are relative to the comms repository.

### B.1 Amendment citations

| Cited | Verdict | Note |
|---|---|---|
| D4, D5, A7, A8, A9, A13, A19, A20, A22, A26, A28, A29, A30, A32, A34, A37, A41, A44, A48, R-A20 | ✅ | Each says what v0.6 attributes to it |
| A18 | ✅ 🛠️ | Lists four actors; A49 must amend `ADAPTER_CONTRACTS` |
| A38 (section 0: "settings are `comms.json`") | 🔧 | A38 governs secrets. `comms.json` is D39-PRE E3 (`runtime/settings.py` docstring) |
| A39 "procedure" (D-I12) | 🔧 | A39 is about plan versus spec contradictions. A45 to A48 were added as "owner decided" entries recorded in the rulings register. Cite that precedent |
| A42 (container id persisted before publish) | 🔧 | A42 is about comms-minted correlation keys stored before the call. The container id is Meta-returned from step 1. Defensible only if new code persists it, and today nothing does (B.4) |
| A44 "encrypted at rest" (D-I5, 4.1) | 🔧 | A44 says nothing about encryption. The phrase is A45's and means the whole `comms.db` is SQLCipher. There is no per-identity encryption (`delivery_identities.identity` is plaintext inside the encrypted database). Cite `test_the_database_files_hold_no_plaintext_canary` |

### B.2 Protocols, refs, catalog, capabilities

| Claim | Verdict | Evidence |
|---|---|---|
| `ADAPTER_CONTRACTS` shape; `snapshot`, `validate`, `invoke(op, target, op_key)`, `read(query)` | ✅ | `core/providers/protocols.py` |
| Provenance `instagram_live` | 🛠️ | `services/context.py` `_PROVENANCE` is a closed map keyed by transport; an unknown one fails closed `PROVIDER_UNAVAILABLE` |
| An adapter can answer `IN_FLIGHT` | ❌ | `ProviderResult.outcome` is `SUCCEEDED \| FAILED \| OUTCOME_UNKNOWN` |
| `iga_`, `igm_`, `igc_` collide with nothing | ✅ | Checked against `CORE_PREFIXES`, Telegram `REF_PREFIXES` (+`tgu_`), WhatsVault `PREFIXES`. Test: `tests/core/test_refs_v03.py::test_v03_prefixes_disjoint_from_telegram_whatsvault_and_5b4` |
| Reuse `cmg_`, `rcp_`, `dst_` for Instagram | 🛠️ | `provider_objects`, `delivery_identities`, `contact_points` carry `transport CHECK IN ('telegram','whatsapp')`; `CONTACT_TRANSPORTS` and `DESTINATION_TRANSPORTS` are `{telegram, whatsapp}`. A schema migration (v9) and directory changes |
| `ToolSpec` has no `requires_user_interaction`; `_entry` emits no `_meta` | ✅ | `mcp/spec.py` (11 fields), `mcp/catalog.py` |
| `_entry` emitting `_meta` reaches the host | 🛠️ | The daemon does not serve `_entry` dicts: `mcp/http.py` `_tools()` builds `types.Tool(...)` field by field and would drop `_meta` unless it passes `meta=`. The proxy side is fine (section A) |
| `provider_result(**extra)`, `OUTCOMES` has `IN_FLIGHT`, `read()`/`write()` signatures | ✅ | `write(capability=...)` overwrites `idempotent` from `SEMANTICS`, ORs `destructive`, and forces `open_world=True` |
| `actor` field accepts `instagram` | 🛠️ | `schemas.py` `ACTOR` is a closed enum of three. Adding one changes **every** write tool's output schema, so the whole `tests/mcp/catalog_pin.json` re-pins, not only the flagged tools |
| `HISTORY_READ`, `MESSAGE_REPLY` exist; `OperationSemantics` fields and literals | ✅ | `semantics.py` |
| New `Capability` members | 🛠️ | `tests/core/providers/test_protocols.py` pins the enum to capability phrases parsed from the v0.3 spec text plus A46 and A47. A49's text must name each new capability as "capability `x.y`", and the test must read A49 |
| `comment.reply`, `message.reply` are `CREATE` | 🔧 | `MESSAGE_REPLY` is in `_SENDS`, so `_semantics()` yields `MESSAGE_SEND, none, resolve_only` |
| `SUPPORT[c]` includes `instagram`; `AUTHORITY_ORDER` unchanged | 🛠️ | `SUPPORT` is derived from fixed Telegram and Cloud sets (`HISTORY_READ` is user-only). `choose_actor` iterates `AUTHORITY_ORDER`, so an actor absent from it is refused `CAPABILITY_UNAVAILABLE` unless `configured="instagram"` is passed. Instagram writes need that or their own path |
| Carousel `steps` built per call from `len(children)` | ❌ as written | `SEMANTICS` is a static `MappingProxyType`; the executor persists `semantics.steps` at insert and indexes `step_args[index]`; the semantics test requires every step to be its own static entry. A per-call step builder is a new executor seam |

### B.3 Secrets, settings, wiring, egress

| Claim | Verdict | Evidence |
|---|---|---|
| Parameterised purpose `meta-ig-access-token/<alias>` | 🛠️ | `PURPOSES` is a static exact-name map; `SECRET_ITEMS`, `FileSecretStore._check`, `_purpose()`, `rotate_credential`, `audit/specs.py` `_CREDENTIALS` and `test_purposes.py` all assume it. A `/` also lands in a filesystem path |
| `staged` rotation, destroy `at_rotation`, proof via `ctx.proofs` | ✅ | Proofs are a fixed per-purpose map built from settings at assembly (`runtime/proofs.py`, `assemble.py`), so per-alias proofs and a reload after `account add` are code |
| "One transaction per purpose" | 🔧 | Rotation is file write, prove, one audited transaction, re-check, delete. Serialisation comes from the audit writer lock |
| `instagram` top-level key in `comms.json` | 🛠️ | `_TOP` is closed; unknown keys raise `SettingsError`. `AdapterSettings` has four fields |
| Alias grammar `[a-z0-9_-]{1,32}` | 🔧 | `_no_secrets` refuses any key containing `token`, `secret`, `key`, `password`, `seed`. An alias like `keystone` would refuse the whole file |
| `_configured(conn, secrets, purpose)`; adapters keyed by actor; `Capability(None)` → `NOT_CONFIGURED` | ✅ | `runtime/adapters.py`, `whatsapp/cloud/account.py` |
| The actor set is open | 🛠️ | `_ACTORS` is hard-coded in `runtime/comms_runtime.py`, `runtime/selftest.py`, and the typed audit payload `admin.mutation_started.actor` (`core/audit/specs.py`). Without the change every Instagram mutation fails A7's closed-enum validation |
| `pinned_client(GRAPH_IG_ORIGIN)` | 🔧 | `timeout` is a required keyword |
| "`test_egress.py` allows `graph.instagram.com` for `transports/instagram/http.py` only" | ❌ | That test is a per-module **httpx-import** allowlist (`NETWORK_MODULES`) and knows no origins. Origins are pinned in code. It also enforces `test_uv_lock_adds_no_new_package` |
| "The egress matrix moves" | 🔧 | `EGRESS_MATRIX` is per-tool **output content classes**, not origins. Relevant anyway: the Instagram writes echo `untrusted.username`, the first write tools to carry `untrusted`, so `_NAMES` must list them or `test_every_tool_declares_its_egress_class` fails |
| `GraphTransportError("not_sent" \| "ambiguous")`; token regex; ids `[0-9]{1,20}`; `retries=0` | ✅ | `whatsapp/cloud/http.py`, `transports/net.py` |

### B.4 Executor, resume, recovery (D-I7, sections 6 and 13)

| Claim | Verdict | Evidence |
|---|---|---|
| The operation "ends `IN_FLIGHT`" and `publish_resume` finishes it | ❌ | `IN_FLIGHT` is the mutation's **birth** state and is returned to a caller only with `AUDIT_INTEGRITY_DEGRADED`. `_run` executes every step to completion; any non-`SUCCEEDED` step finishes the mutation. There is no deliberate "stop after step 1, leave the rest `PENDING`" exit |
| A daemon restart loses nothing | ❌ | `recover_mutations` runs at startup and settles any `IN_FLIGHT` step as `OUTCOME_UNKNOWN`, then finishes the mutation. Only `SUCCEEDED ... PENDING` is resumable today |
| Resume by `op_ref` with a new `request_id` | 🔧 | Resume today is replay of the same `(client, request_id)`. There is no by-`op_ref` entry point |
| Step records carry the container id | ❌ | `mutation_steps` holds `step_no, capability, state, provider_request_key, provider_code`. `provider_request_key` is comms' own `f"{op_key}:{step_no}"`. `ProviderResult.provider_ref` is consumed only at the last step and never persisted per step. The container ledger is new storage |
| `crash_at` seam; `_record_step`; A42 key before the call; `req_` under B is `REQUEST_ID_REUSE` | ✅ | `CRASH_POINTS = (before_call, after_call, after_record, between_steps)`; digest includes `targets.destination`, so the reuse check holds when `destination_ref` is the `iga_` |
| `CapabilityService` cache "keyed by `iga_`" | 🔧 | The key is `(actor, destination_ref)`, so it holds only if the `ProviderTarget.destination_ref` is the `iga_`, which needs a target builder (today `group_targets` builds from `grp_`) |

### B.5 Hosts, matrix, files

| Claim | Verdict | Evidence |
|---|---|---|
| Ask-list rule "every destructive or open-world `request_id` tool" | ✅ | `test_host_permissions.py`. Because `write(capability=...)` forces `open_world=True`, **all nine** Instagram writes are ask tools; the prompt/ask split is additive `_meta` on top |
| `comms mcp --stdio` | 🔧 | `--client-seed <path>` is also required |
| "The proxy never crashes on a daemon error, it answers `isError`" | 🔧 | `ProxyError` propagates; the SDK returns a JSON-RPC error, not `isError` |
| Actor-matrix rows `A done` / `—` | 🛠️ | `test_actor_matrix.py` has `ACTORS` fixed at three and keeps only rows with exactly four cells, so a fifth column is silently skipped and the "every tool is a row" test then fails. Cells need `— : <reason>` with a reason |
| `scripts/e2e_smoke.py` sweeps the 23 tools through the proxy | ❌ | That script drives the retired Phase-1 demo server. The catalog sweep is `scripts/smoke_sweep.py`, over HTTP `/mcp`, not the proxy |
| `tests/security/test_redaction.py` gains the token shape | 🔧 | That file tests the legacy Telegram dispatch. The Graph-token tests are `tests/transports/whatsapp_cloud/test_classify.py` and the secrets sweep in `tests/security/test_v03_egress.py` |
| `docs/verification/live-acceptance/` convention | 🔧 | The directory does not exist. It is `EVIDENCE_DIR` in `tests/conformance/test_live_acceptance.py` (`<date>.json`); runbooks live at `docs/runbooks/live-acceptance-*.md` |
| `clients-claude-code.md` exists; `.python-version` 3.12; `mcp`, `mcp-types` 2.2.0, `httpx` pinned | ✅ | `test_runbooks.py` has a closed `EXPECTED` set and parses `comms ...` commands, so a new runbook or CLI verb must be added there and in `cli_commands/operator.py` first |

### B.6 Code changes the spec implies but does not state (🛠️)

1. `mcp/http.py` `_tools()` passes `meta=` to `types.Tool`.
2. `schemas.py` `ACTOR` gains `instagram`, re-pinning every write tool; also `core/audit/specs.py` `_ACTORS`, `runtime/comms_runtime.py`, `runtime/selftest.py`.
3. Schema migration v9 for the `transport` CHECKs on `delivery_identities`, `contact_points`, `destinations`, `provider_objects`, plus `objects.py` `_TRANSPORTS`, `KIND_PREFIX` and `directory.py` transport sets, if `rcp_`, `cmg_`, `dst_`, `igm_`, `igc_` are objects.
4. `services/context.py` `_PROVENANCE` gains `instagram`.
5. `services/capability.py` `choose_actor` for a non-`AUTHORITY_ORDER` actor, or a dedicated Instagram write path.
6. Executor: a per-call step builder (carousel N+1), a deliberate `IN_FLIGHT` exit leaving later steps `PENDING`, resume by `op_ref`, per-step persistence of `provider_ref` (the container ledger), and `recovery.py` must not settle an in-progress publish as `OUTCOME_UNKNOWN`.
7. Parameterised purposes across `purposes.py`, `secrets.py`, `core/credentials.py`, `operator/credentials.py`, `runtime/proofs.py`, `audit/specs.py`, `test_purposes.py`.
8. `settings.py` `_TOP`, an `_INSTAGRAM` validator, `AdapterSettings` fields, `build_adapters`.
9. `comms_admin_identity_inspect` ref kinds and `core/identities.py` for `iga_`, `igm_`, `igc_`.
10. `mcp/egress.py` `_NAMES` lists every Instagram write that echoes `untrusted.username`.
11. `tests/security/test_egress.py` `NETWORK_MODULES` gains `transports/instagram/http.py`.
12. `test_actor_matrix.py` for a fifth column; `test_protocols.py` to read A49; `test_semantics.py`.
13. `test_runbooks.py` `EXPECTED` and the CLI parser for `instagram account add|list|remove`, `token refresh`, `doctor`.
14. `doctor.py` finding codes.

Also binding: `tests/security/test_comms_layering.py` (core stays transport-neutral; `transports/instagram` must not import `transports/telegram`) and `test_uv_lock_adds_no_new_package`.

---

## C. Transcription from the v0.5 gauntlet and internal consistency

The mirror `SPEC.md` is byte-identical to the comms copy apart from its two-line banner.

### C.1 The 25 recommended edits from `GAUNTLET-v0.5.md` section G

| Status | Items |
|---|---|
| Done | 1, 2, 4, 5, 10, 11 (by removal), 14, 15, 17, 18, 19, 20, 21 (in section 7), 22, 23, 24, 25 |
| Not applicable, the TypeScript stack is retired | 6, 7, 8 (principle kept: no I/O at boot), 13, 16 |
| **Partial** | 3: GI-1 is now a hard gate with no query-param fallback (deliberate, A26). But the fallback text "a POST-body token for reads" is incoherent for GET endpoints, and the **refresh call** `GET /refresh_access_token?grant_type=ig_refresh_token&access_token=...` is the one documented form that puts the token in the URL. GI-1 must name it, or section 4.4 needs a 🧪 |
| **Mis-transcribed** | 9: section 6 says "honouring cancellation (`ctx.mcpReq.signal` on the proxy side)". That is the **TypeScript** SDK 2.3.0 handler name. v0.6 runs the Python `mcp` 2.2.0, where it does not exist. Replace with the Python SDK's cancellation mechanism and mark 🧪 |
| **Missing** | 12: the rule "validate `structuredContent` before returning" (an output-schema violation surfaces as `isError`) is not carried anywhere |

New facts from the v0.5 gauntlet still missing: `content_publishing_limit` `since` must be no older than 24 hours (default field `quota_usage`); `INSTAGRAM_PLATFORM_API__INVALID_LOCATION_ID` is absent from `IG_CODES` although `location_id` is an accepted argument (it would land in `OUTCOME_UNKNOWN`); Claude Code excludes a tool whose schema is not valid JSON Schema 2020-12 (v2.1.216+); the Reel aspect range 0.01:1 to 10:1.

No ❌ fact was re-introduced. Three places put ✅ on something still open: the `conversation_messages` row (GI-8 still tests the shapes), "neither works on live video" for hide and delete (the gauntlet records the live-video restriction only for `comment_enabled`), and error code `0` in the token row (unsourced; the gauntlet lists `190` only). The token shape `[A-Za-z0-9_.\-]{20,512}` is copied from comms' WhatsApp client, not from Meta, and should say so.

### C.2 Internal inconsistencies

| # | Where | Problem | Fix |
|---|---|---|---|
| I-1 | 8 vs 5.3, 13 | **Contradiction.** The error table says `2207003` "one retry, same container", `2207032` "one retry, then new", `2207008` "1 to 2 retries, then new container", while the footer, 5.3 and 13 say CREATE is resolve-only and never creates a second container for one `req_` | Make the Kind column step-scoped: retries only on `MEDIA_CONTAINER_STATUS` (a read) and on `MEDIA_PUBLISH` of the **same** `creation_id`. Every "then new container" becomes `FAILED CONTAINER_FAILED`; a new container needs a new `request_id` |
| I-2 | 6 vs 11 | "Poll once a minute for at most 5 minutes" exceeds Claude Code's 2-minute backgrounding, yet 11 says a Reel ends `IN_FLIGHT` "well before that" | State the in-request poll budget (for example 90 s) that returns `IN_FLIGHT`; keep "once a minute for 5 minutes" as Meta's advice, not the executor's budget |
| I-3 | 3 vs 5 | The module layout has no home for `tag_list`, `publish_preview`, `publish_quota`, `media_list`, `media_get`, `profile_get`, `whoami`, nor for the 23 `ToolSpec` entries | Add `media.py`, put tags beside comments, put preview, quota and the ledger in `publish.py`, and name the catalog module (`src/comms/mcp/tools/instagram.py`) |
| I-4 | 5.1 vs 4.1, 9 | `conversation_messages` takes a conversation id, which is an identity with no ref | The tool takes an `rcp_`; comms resolves the conversation internally |
| I-5 | 5.2 vs 4.1 | `message_send` names no recipient argument; `dst_` is introduced and never used | Recipient is `rcp_`; drop `dst_` |
| I-6 | 0 vs 5.2, D-I3 | Section 0 says the flag is on "public-posting" tools; seven are flagged including `comment_delete` and `message_send` | "public-posting and irreversible", as D-I3 says |
| I-7 | 5.1 vs 15 Q3 | `preview_digest` is returned in 5.1 but still an open question | Mark "(proposed, Q3)" or resolve Q3 |
| I-8 | 13 vs body | GI-2, GI-7, GI-8 are referenced only in 13 and 14 | Add 🧪 GI-2 to 4.4, GI-7 to the dual-era sentence, GI-8 to the `conversation_messages` row in place of ✅ |
| I-9 | 7 vs GI-4 | GI-4 tests `media_product_type`, which 7 says never to request | Drop it and `is_comment_enabled` (no restriction) from GI-4 |
| I-10 | D-I8 vs 7, 5.2 | D-I8 says 24 hours; 7 says 24 hours or 7 days after a Click-to-Direct ad | Live check enforces 24 h and reports the 7-day case as `WINDOW_CLOSED`, because without webhooks comms cannot see the ad origin. Mark ℹ️ |
| I-11 | 5.3 vs 6 | Only `publish_reel` "may return `IN_FLIGHT`"; carousel child types are unstated | State child types; if video children are allowed, `publish_carousel` may end `IN_FLIGHT` too |
| I-12 | 13 vs 14 | GI-8's write side ("a send inside the window") is assigned to no milestone | Add "GI-8 (write side)" to MI-3 |
| I-13 | 13 | GI-7 says "`legacy` and `auto`", the host matrix also has "unset" | Add "unset" |
| I-14 | 3 vs 8 | `GraphTransportError("not_sent")` is never mapped in 8 | Add `not_sent` → `FAILED_TRANSIENT` (as `classify.py` does for WhatsApp) |
| I-15 | 5 vs 5.1 | "Every tool takes `account`" but `account_list` lists all aliases | Exempt it |
| I-16 | References | Dropped: MCP *Versioning and Compatibility* (source of the era claims) and *Transports*. Listed but uncited: *Security Best Practices*, *Permissions Reference* | Restore Versioning; drop or cite the other two |

Passed: 23 tools (14 reads, 9 writes); every write has a semantics entry; every capability in the tool tables is in 5.3; the nine ask-list tools match section 11; every D-I resolves; the 21 error rows match the gauntlet; `IN_FLIGHT` is consistent across D-I7, 6 and 5.3 apart from I-2 and I-11.

### C.3 Hygiene

- Unmarked assertions among marked neighbours: the publish, reply and send endpoint cells in 5.2 (all gauntleted ✅), the `whoami` row, the whole of section 10 (webhook field names, `subscribed_apps`, `entry[].messaging[]`: Meta facts with no gauntlet row, mark ℹ️ or defer to a v2 gate), and "`mcp-types` 2.2.0 is dual-era" in 13 (now verified in section A of this report).
- Undefined before use: "standing", `req_` (not in 4.1's prefix list), the schema DSL in 5.2, "the three other actors", and A49 and R-IG0 in the header before D-I12.
- Casing: `<ig_id>` in 5 versus `<IG_ID>` in 2 and 10.
- Harvard: split the PyPI entry into two works; point the GAUNTLET reference at the file and commit `cdae96e`; pick one date convention (the gauntlet has page stamps for every Meta page); order by author.
- Repetition worth trimming: the `/me` call (four places), "never fetched" (four), N+1 (four), the preview description (two).

---

## D. Sourcing

- comms source read at `3f6df9a` (main) and `d9b6aa9` (the spec branch) in `/home/user/telegram-mcp`.
- SDK facts from the wheels `mcp-2.2.0` and `mcp_types-2.2.0` on PyPI, run inside comms' locked environment (`uv sync --locked`, exit 0).
- No Meta or Claude Code page was re-fetched: those facts carry the first-hand verification in `GAUNTLET-v0.5.md` from earlier the same day.
