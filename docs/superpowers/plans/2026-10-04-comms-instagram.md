# Comms Instagram actor (A49): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner's standing rule for this repo: no subagents; the main session executes, test-first, inline. Steps use checkbox (`- [ ]`) syntax for tracking. Read `CLAUDE.md`, `AGENT.md` and `CHANGELOG.md` before the first edit.

**Goal:** one more comms actor, `instagram`, serving 24 `comms_instagram_*` tools (22 at IG-6; IG-9 adds two Story reads) over the existing daemon, proxy, executor, secret store and audit chain, so the owner's AI assistant can read, publish to, moderate and reply on Instagram professional accounts, with every write audited.

**Spec:** `docs/instagram-spec-v0.6.md` (revision 2, proposed amendment A49). Section 14 lists every code change; this plan sequences them. The spec wins over this plan; a contradiction stops the task and is recorded as a ruling (A39).

**Architecture:**
- **Transport package** `src/comms/transports/instagram/`: `GraphIgApi` pinned to `https://graph.instagram.com`, capability, admin, context, publish ledger, classifier, CLI. The only `httpx` importer is `http.py`.
- **Service** `src/comms/runtime/instagram.py` (R-IG4): the one place tools call. It builds `iga_`-keyed `ProviderTarget`s and calls `MutationExecutor.provider` directly.
- **Catalog** `src/comms/mcp/tools/instagram.py`: 22 `ToolSpec`s; four carry `requires_user_interaction`.
- **No executor, recovery, relay or proxy change.** Publishing is three single-effect CREATE tools on a durable `igk_` row (spec D-I7, D-I13).

**Tech stack:** Python 3.12, `uv`, `httpx` through `pinned_client`, SQLCipher `comms.db`, `mcp` 2.2.0, pytest. No new dependency (`test_uv_lock_adds_no_new_package`).

## Global constraints

- **Branch and approvals.** Work on branch `comms-instagram-spec` (this plan and the spec are already on it). Merge, push and the ruling R-IG0 only with the owner's approval.
- **Commits.** Commit only when the full gate shows `GATE ok=1`. Write nothing in-tree while a gate runs. Executed with a development worktree (branch `ig-work`): each task is committed there, gated in the main checkout on that exact commit, and only then is `comms-instagram-spec` moved to it (R-IG1).
- **Secrets.** A token reaches `comms transport instagram account add` only on a pipe. Never commit, log or print one. Tests use fake tokens of the documented shape.
- **Fail closed.** `UNKNOWN` is never `AVAILABLE`; a rejected proof leaves the working slot active; a classifier miss is `OUTCOME_UNKNOWN`.
- **One copy of each rule.** URL validation in `urls.py`; the error table in `classify.py`; the insight tables in `insights.py`; the alias grammar in `settings.py`.
- **Every call fits 30 s** (the proxy's `_TIMEOUT_S`). No tool sleeps or polls. At most two Graph calls per tool.
- **Egress.** `transports/instagram/http.py` is the only new entry in `NETWORK_MODULES`. Core never imports a transport; `transports/instagram` never imports `transports/telegram` or `transports/whatsapp` except `whatsapp/webhooks/signature.py` in v2.
- **Typed egress (A44).** Identities (`user_id`, IGSIDs, media and comment ids, `creation_id`) never leave except through `comms_admin_identity_inspect`. Bodies only in `untrusted_text`.
- **Pins move on purpose.** `tests/mcp/catalog_pin.json` regenerates **once**, in Task IG-1, when `ACTOR` gains `instagram`; every later task that adds tools regenerates it again under its exit assertion. Record each regeneration in the task's ledger line with the old and new `catalog_digest`.
- **Audit trail.** A dated `**Raouf:**` entry in `AGENT.md` and `CHANGELOG.md` per task, a ledger line per task, rulings R-IG1 onward in `docs/verification/comms-v0.3-rulings.md`.

## Review focus

1. **A write replayed under the same `request_id` makes no second provider effect**, at every `crash_at` point. Tests: IG-5 `test_container_create_replay_makes_one_container`, IG-5 `test_publish_resolves_by_status_after_crash`.
2. **The wrong account cannot write.** `account` is required; a `req_` under account B is `REQUEST_ID_REUSE`; an `igk_` child of another account is refused by `carousel_create`; `writes: false` refuses before any provider call. Tests: IG-4 `test_wrong_account_refused_before_provider`, IG-5 `test_foreign_child_refused`.
3. **No token in a URL, log, repr or error.** Tests: IG-1 `test_token_only_in_authorization_header`, the secrets sweep in `tests/security/test_v03_egress.py`.
4. **Hostile text produces no write.** Test: IG-4 `test_injected_comment_causes_no_write`.
5. **Every Instagram mutation appends to the chain** with actor `instagram` accepted by the typed payload. Test: IG-1 `test_audit_payload_accepts_instagram_actor`.
6. **`_meta` reaches the host.** Test: IG-6 `test_meta_reaches_the_wire_through_http_tools` and the proxy-path check in `scripts/smoke_sweep.py`.

---

### Task IG-0: Pre-flight, pins and the gauntlet record

**Files:**
- `docs/verification/comms-v0.3-rulings.md`: pin the SHA-256 of `docs/instagram-spec-v0.6.md` (rev 2) and this plan; ruling R-IG1 (pre-flight, "no production code changed").
- `docs/verification/instagram-gauntlet-v0.6.md` (new): a copy of `GAUNTLET-v0.6.md` from `Raoof128/Instagram-MCP` at `85cf0b1`, so the verification record lives beside the spec.

- [ ] **Step 1:** `uv sync --locked`; run the full gate once on a clean tree and record the baseline (`5632 passed, 4 skipped` or the current number) in the ledger.
- [ ] **Step 2:** add the two pins and R-IG1; copy the gauntlet record.
- [ ] **Step 3:** `uv run pytest tests/security/test_runbooks.py tests/security/test_v03_preflight.py -q` green; AGENT.md and CHANGELOG.md entries; commit.

### Task IG-1: The actor exists (enums, settings, purposes, migration, the Graph client, accounts)

Spec: sections 3, 4, 14 items 2, 3 (accounts part), 7, 8, 11.

**Files:**
- `src/comms/core/providers/protocols.py`: `ADAPTER_CONTRACTS["instagram"] = frozenset({"capability", "admin", "context"})`.
- `src/comms/core/providers/capability.py`: the 14 members from spec 5.3, names `UPPER_SNAKE` of the value.
- `src/comms/core/providers/semantics.py`: `INSTAGRAM = "instagram"`; an `_INSTAGRAM_SUPPORT` override table; `SUPPORT` merged from it; `SEMANTICS` entries per spec 5.3; `READS` gains the seven read capabilities.
- `src/comms/mcp/schemas.py`: `ACTOR` enum gains `"instagram"`.
- `src/comms/core/audit/specs.py`: `_ACTORS` gains `"instagram"`.
- `src/comms/runtime/comms_runtime.py`, `src/comms/runtime/selftest.py`: unchanged; their `_ACTORS` are group-target actors (R-IG3).
- `src/comms/core/refs.py`: `"instagram_account": "iga_"`, `"instagram_container": "igk_"`, `"instagram_media": "igm_"`, `"instagram_comment": "igc_"`, `"instagram_person": "igp_"` (R-IG2).
- `src/comms/core/storage/migrations.py`: `Migration(10, SCHEMA_V10)`: `instagram_accounts(id, ref, alias, user_id, obtained_at, expires_at, last_identity_check_at, created_at, removed_at)` with one live row per alias and per `user_id`; `instagram_containers(id, ref, account_id, kind CHECK IN (image, reel, carousel, child), creation_id, created_at, status, media_ref)`; `instagram_objects(id, ref, account_id, kind CHECK IN (media, comment, person), provider_identity, created_at, last_seen_at)`. No existing table changes (R-IG2).
- `src/comms/core/keys/purposes.py`: `PurposePattern("meta-ig-access-token.", "opaque", "staged", False, "at_rotation")` and `purpose_of(name) -> KeyPurpose | None` that resolves a static name or a pattern match (alias grammar from settings).
- `src/comms/core/keys/secrets.py`: `SECRET_ITEMS` check uses `purpose_of`.
- `src/comms/core/credentials.py` `_credential`, `src/comms/runtime/operator/credentials.py` `_purpose`: use `purpose_of`.
- `src/comms/runtime/proofs.py`: `build_proofs(..., instagram_aliases=...)` adds one `/me` proof per alias.
- `src/comms/runtime/settings.py`: `_TOP` gains `"instagram"`; `_instagram()` validator; `DaemonSettings.instagram`.
- `src/comms/runtime/adapters.py`: `AdapterSettings` fields; `_instagram(...)`; `build_adapters` calls it.
- `src/comms/transports/instagram/{__init__,http,config,store,accounts,capability,doctor}.py` (new); `src/comms/runtime/operator/instagram.py` (new: the handlers and `InstagramOperator`, R-IG3).
- `src/comms/cli_commands/operator.py`: `transport instagram account add|list|remove`, `transport instagram token refresh`, `transport instagram doctor` (under `transport`, R-IG3).
- `tests/security/test_egress.py`: `NETWORK_MODULES` gains `src/comms/transports/instagram/http.py`.
- `tests/core/keys/test_purposes.py`: DESIGN gains the pattern.
- `tests/core/providers/test_protocols.py`: `_amendment_ids(49)` reads `docs/instagram-spec-v0.6.md` section 5.3 phrases; `test_adapter_contracts_match_a18` gains the fifth entry.
- `tests/mcp/catalog_pin.json`: regenerated (the `ACTOR` ripple); ledger line records both digests.
- New tests: `tests/transports/instagram/test_http.py`, `test_accounts.py`, `test_capability.py`, `test_settings_instagram.py`, `tests/core/keys/test_purpose_patterns.py`, `tests/core/storage/test_migration_v10.py`, `tests/core/audit/test_instagram_actor_payload.py`.

**Interfaces produced:**
- `GraphIgApi(secrets, *, purpose: str, version: int, api_version: str, timeout=15.0, transport=None)` with `me(fields)`, `get(path, params)`, `post(path, body)`, `delete(path)`, each returning `GraphResponse`; raises `GraphRefused`, `GraphTransportError`.
- `accounts.register(conn, alias, label, user_id, obtained_at, expires_at) -> str` (the `iga_`), `accounts.resolve(conn, settings, alias | None, *, for_write: bool) -> AccountRow`, `accounts.prove_identity(api, row) -> None` (raises `IdentityMismatch`).
- `InstagramCapability(api_by_alias | None, settings, clock).snapshot(actor, destination)`.

- [ ] **Step 1: Failing tests.** `test_token_only_in_authorization_header` (a recording transport asserts no `access_token` in any URL, and the header on every call); `test_graph_ig_pins_origin` (a request to `graph.facebook.com` is `EgressRefused`); `test_alias_grammar_refuses_secret_substrings` (`keystone` refused); `test_purpose_pattern_resolves_alias_and_refuses_unknown`; `test_migration_v10_adds_tables_and_checks`; `test_audit_payload_accepts_instagram_actor`; `test_account_add_proves_me_and_registers`; `test_identity_mismatch_blocks_alias`; `test_no_network_at_boot`.
- [ ] **Step 2:** implement in the order listed; regenerate `catalog_pin.json` once; run `uv run pytest tests/mcp tests/core tests/security tests/transports/instagram -q`.
- [ ] **Step 3:** full gate `GATE ok=1`; AGENT.md and CHANGELOG.md; ruling R-IG2 if any deviation; commit.

### Task IG-2: Reads and context

Spec: sections 5.1 (minus `publish_quota`, `publish_preview`), 7, 9, 14 items 4, 9, 12.

**Files:**
- `src/comms/transports/instagram/{media,comments,insights,messages,context}.py` (reads only).
- `src/comms/runtime/instagram.py` (reads; R-IG4); `src/comms/core/providers/instagram_insights.py` (the insights tables, data only).
- `src/comms/mcp/tools/instagram.py`: the 12 read `ToolSpec`s; `src/comms/mcp/tools/__init__.py` `FAMILIES` gains it.
- Paging: Meta's `after` cursor becomes a `cur_` through `ContextHandles` (target `iga_`, actor `instagram`); `src/comms/services/context.py` is not changed (R-IG2).
- `src/comms/mcp/tools/account.py`, `src/comms/core/identities.py`: identity inspect for `iga_`, `igk_`, `igm_`, `igc_`, `igp_`.
- `docs/verification/comms-v0.3-actor-matrix.md`: an Instagram table with its own header (R-IG4); `comms_instagram_account_list` among the local tools.
- `tests/core/providers/test_actor_matrix.py`: each table's actors from its header row (R-IG4); `tests/integration/test_actor_matrix_behaviour.py` skips a table without its actor.
- `tests/mcp/catalog_pin.json`: regenerated.
- Tests: `tests/transports/instagram/test_media.py`, `test_insights_tables.py` (every (metric, product type) pair in spec 7 is allowed and nothing else; `crossposted_views` never by default), `test_messages_throttle.py` (2 per second, sequential), `tests/runtime/test_instagram_reads.py`, `tests/mcp/test_instagram_catalog.py`.

- [ ] **Step 1: Failing tests** (above), plus `test_caption_absent_degrades_default_fields`, `test_media_url_optional`, `test_bodies_only_in_untrusted_text`.
- [ ] **Step 2:** implement; regenerate the pin; `uv run pytest tests -q -k "instagram or actor_matrix or catalog"`.
- [ ] **Step 3:** full gate; audit entries; commit.

### Task IG-3: The classifier, policy and the write path

Spec: sections 4.3, 4.5, 5.2 (comments and DM only), 5.3, 8, 14 items 5, 6 (writes), 10.

**Files:**
- `src/comms/transports/instagram/classify.py`: `IG_CODES: Mapping[tuple[int, int | str | None], tuple[ResultKind, str | None]]`, `classify(outcome) -> ProviderResult`, `not_sent -> FAILED_TRANSIENT`.
- `src/comms/transports/instagram/admin.py`: `validate()` and `invoke()` for `comment.reply`, `comment.hide`, `media.comments_toggle`, `comment.delete`, `message.reply` (window check from the live conversation).
- `src/comms/runtime/instagram.py` (writes): policy ceiling before any provider call; `MutationExecutor.provider` with an `iga_`-keyed target.
- `src/comms/mcp/tools/instagram.py`: the five write `ToolSpec`s with `provider_result(account=..., untrusted=...)`.
- `src/comms/mcp/egress.py`: `_NAMES` gains them.
- `.claude/settings.json`: `permissions.ask` gains `mcp__comms__comms_instagram_{comment_reply,comment_hide,comments_enabled_set,comment_delete,message_send}`.
- `tests/mcp/catalog_pin.json`: regenerated.
- Tests: `tests/transports/instagram/test_classify.py` (every row of spec 8; an unknown pair is `OUTCOME_UNKNOWN`; `not_sent`), `tests/services/test_instagram_writes.py` (`test_wrong_account_refused_before_provider`, `test_policy_disabled_refuses_before_provider`, `test_req_under_other_account_is_reuse`, `test_injected_comment_causes_no_write`, `test_window_closed_refuses`), `tests/security/test_host_permissions.py` passes unchanged.

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2:** implement; regenerate the pin; targeted tests.
- [ ] **Step 3:** full gate; audit entries; commit.

### Task IG-4: Publishing on a durable container ref

Spec: sections 5.1 (`publish_quota`, `publish_preview`), 5.2 (`container_create`, `carousel_create`, `publish`), 6.

**Files:**
- `src/comms/transports/instagram/{urls,publish}.py`: URL validation; the `igk_` ledger (`containers.create_row`, `count_last_24h`, `mark_status`, `mark_published`); quota read; preview; `admin.invoke` for `media.container_create`, `media.carousel_create`, `media.publish` (status read, then publish; resolution by status).
- `src/comms/mcp/tools/instagram.py`: the five remaining `ToolSpec`s.
- `src/comms/mcp/egress.py` `_NAMES`; `.claude/settings.json` ask list gains the three publish writes.
- `tests/mcp/catalog_pin.json`: regenerated.
- Tests: `tests/transports/instagram/test_urls.py` (userinfo, IP literal, `localhost`, `http`, length), `test_publish_ledger.py` (400 budget, 24 h window, foreign child refused), `tests/services/test_instagram_publish.py` (`test_container_create_replay_makes_one_container` at every `crash_at`, `test_publish_resolves_by_status_after_crash`, `test_publish_not_ready_is_failed_not_retried`, `test_published_container_answers_succeeded_with_media`, `test_carousel_needs_2_to_10_same_account_children`, `test_quota_cap_2207042_is_publish_cap`), `tests/security/test_media_fits_the_wire.py` unchanged.

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2:** implement; regenerate the pin; targeted tests.
- [ ] **Step 3:** full gate; audit entries; commit.

### Task IG-5: `requires_user_interaction` through the daemon

Spec: section 11, 14 item 1.

**Files:**
- `src/comms/mcp/spec.py`: `requires_user_interaction: bool = False`.
- `src/comms/mcp/catalog.py`: `_entry` adds `"_meta": {"anthropic/requiresUserInteraction": True}` when set; `_canonical` includes it.
- `src/comms/mcp/http.py` `_tools()`: `meta=entry.get("_meta")`.
- `src/comms/mcp/tools/instagram.py`: set on `publish`, `comment_reply`, `comment_delete`, `message_send`.
- `tests/mcp/catalog_pin.json`: regenerated.
- Tests: `tests/mcp/test_catalog_meta.py` (`_meta` only on the four; absent elsewhere), `tests/mcp/test_http_tools_meta.py` (`test_meta_reaches_the_wire_through_http_tools`: `/mcp` `tools/list` carries it), `tests/mcp/test_stdio_proxy.py` (a proxied `tools/list` keeps `_meta`).

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2:** implement; regenerate the pin.
- [ ] **Step 3:** full gate; audit entries; commit.

### Task IG-6: Doctor, smoke, runbooks, exit test

Spec: sections 4.4, 11, 13, 14 items 13, 14, 15.

**Files:**
- `src/comms/transports/instagram/doctor.py`: the five finding codes; wired into `comms doctor`.
- `scripts/smoke_sweep.py`: the 22 tools against a fake `GraphIgApi`; a proxy-path `tools/list` check asserting the four `_meta` keys. `docs/verification/comms-v0.3-smoke-map.json` and `tests/security/test_smoke_map.py` updated.
- `docs/runbooks/clients-claude-code.md`: the Instagram ask rules, `instagram.default` per project. `docs/runbooks/live-acceptance-instagram.md` (new): GI-1 to GI-8, evidence to `docs/verification/live-acceptance/<date>.json`. `docs/runbooks/install.md`: `comms transport instagram account add`.
- `tests/security/test_runbooks.py` `EXPECTED`.
- `tests/conformance/test_live_acceptance.py`: Instagram cases (`NOT_CONFIGURED` until the accounts file names an account).
- `tests/security/test_instagram_exit.py` (new): pins the 22 names and order, `catalog_digest`, the ask list, `_NAMES`, `ADAPTER_CONTRACTS["instagram"]`, the four prefixes, the three actor enums, `_meta` on exactly four tools, `NETWORK_MODULES`, `SCHEMA_VERSION == 10`.
- `CLAUDE.md`: a paragraph under the history ("A49, branch `comms-instagram-spec`"), the test count, the Map table row for `src/comms/transports/instagram/`.

- [ ] **Step 1: Failing tests** (`test_instagram_exit.py`, the smoke-map test).
- [ ] **Step 2:** implement; run `uv run python scripts/smoke_sweep.py` against the self-test daemon.
- [ ] **Step 3:** full gate; AGENT.md and CHANGELOG.md; commit.

### Task IG-8: Stories publishing (R-IG10, the owner's request)

Spec: revision 3, section 6 (Story), D-I10, section 14 item 3.

**Files:**
- `src/comms/core/storage/migrations.py`: `Migration(11, SCHEMA_V11, rebuild=True)`: `instagram_containers` rebuilt with `kind` admitting `story`; rows, index and trigger kept.
- `src/comms/transports/instagram/{publish,store}.py`: kinds `story_image` and `story_video` (`media_type=STORIES`, `image_url` or `video_url`, nothing else); ledger kind `story`.
- `src/comms/mcp/tools/instagram.py`: the two kinds in `container_create` and `publish_preview`; the catalog pin regenerated.
- Tests: the Story arguments Meta refuses are refused first; a Story container publishes; migration v11 keeps every v10 row and refuses an unknown kind; the end-to-end sweep and the daemon smoke publish a Story.

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2:** implement; regenerate the pin; targeted tests.
- [ ] **Step 3:** full gate; audit entries; commit.

### Task IG-9: Reading Stories (R-IG11, the owner's request)

Spec: revision 4, section 5.1 (`story_list`, `story_insights`), section 7 (Story insights).

**Files:**
- `src/comms/core/providers/instagram_insights.py`: `STORY_METRICS`, `STORY_BREAKDOWNS`.
- `src/comms/transports/instagram/{insights,http}.py`: `story_params`; the `stories` edge.
- `src/comms/runtime/instagram.py`: `story_list` (client-bound cursors, as `media_list`) and `story_insights`.
- `src/comms/mcp/tools/instagram.py`, the facades, `_BODY` and `_NAMES`, the actor matrix; the catalog pin regenerated.
- Tests: `tests/runtime/test_instagram_stories.py`; the sweep and the daemon smoke read a Story; the exit test pins 24 tools.

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2:** implement; regenerate the pin; targeted tests.
- [ ] **Step 3:** full gate; audit entries; commit.

### Task IG-7: Owner steps (not for the agent)

- [ ] Add each Instagram professional account to the Meta app (public account, Business or Creator), accept the invite, generate the dashboard token with the minimum scopes.
- [ ] `comms transport instagram account add <alias>` per account (token on a pipe), then `comms transport instagram doctor`.
- [ ] Run GI-1 first. If `/refresh_access_token` refuses the `Authorization` header, stop and record the ruling (spec open question 4).
- [ ] Run GI-2 to GI-8 per `docs/runbooks/live-acceptance-instagram.md`; the run writes the evidence file.
- [ ] Decide open questions 1 to 3.
- [ ] Ruling R-IG0: append A49 to `docs/comms-spec-v0.3.md`, re-pin, merge.

## Not in this plan

- Webhooks, the window mirror, mention replies, campaign delivery to Instagram (spec section 10, MI-7).
- Any change to the mutation executor, recovery, the relay Worker or the stdio proxy.
- Stories, collaborators, product tags, hashtag search, delete-media (spec D-I10).

## Agent brief (read once, then execute IG-0 to IG-6 in order)

1. **Start:** `cd` to the repository root on branch `comms-instagram-spec`; `uv sync --locked`; read `CLAUDE.md` (Non-negotiables, Verify, Map), then `docs/instagram-spec-v0.6.md` sections 3, 5, 14, then this plan's task.
2. **Per task:** write the failing tests named in the task first and watch them fail; implement only what the task lists; run the task's targeted tests; run the full gate from `CLAUDE.md` Verify; regenerate `tests/mcp/catalog_pin.json` only where the task says so and record both digests; append the `**Raouf:**` entries (Scope, Summary, Files changed, Verification, Follow-ups) to `AGENT.md` and `CHANGELOG.md`; commit with a one-line subject and a body naming the task.
3. **Stop conditions:** a contradiction between the spec and this plan (record a ruling, stop); a test in `tests/security/` that would need weakening (stop, it is a design signal); anything that needs a real token or network (owner steps, IG-7).
4. **Done:** six commits, the exit test green, the full gate green, `CLAUDE.md` updated, nothing pushed without the owner.
