# Pinterest for comms: specification v0.1 (proposed amendment A50)

**Status:** Proposed, revision 1, 2 November 2026 (Australia/Sydney). Not yet adopted: `docs/comms-spec-v0.3.md` is unchanged and stays pinned until ruling R-PN0 appends A50 and re-pins it, as A45 to A49 were added. The Instagram actor (A49, `docs/instagram-spec-v0.6.md`) is the blueprint: one more actor on the existing surface, no new server, no new dependency.
**Owner:** Raouf.
**Plan:** `docs/superpowers/plans/2026-11-02-comms-pinterest.md`.
**Stack:** Python 3.12, `uv`, the comms daemon, `mcp` 2.2.0, `httpx` through `pinned_client` and `suffix_pinned_client`.
**Scope:** read boards, Pins and analytics; publish image, carousel and video Pins to a board; edit and delete the account's own Pins; create boards; one or more Pinterest business accounts the owner owns.

Legend: ✅ verified against Pinterest's official pages and the official OpenAPI description (`pinterest/api-description`, v5 `5.28.0`) on 2 November 2026; 🧪 needs a live test (section 13); ℹ️ inference, not doc text. A sentence about comms' own code cites the file it was checked against.

---

## 0. Why Pinterest joins comms, and not a third-party server

comms D4: `comms mcp` is the single AI surface. Pinterest announced its own MCP on 17 June 2026 for selected advertising partners; it is not a generally available organic-publishing integration. Community servers exist (`clugtu/pinterest-mcp`, `aymandakirgh/pinterest-mcp`); each is a second trust boundary with its own credential handling and no audit. comms already has what they lack: typed tools (A29), request-id idempotency (A28), one mutation executor (A28, A41), the anchored audit chain (A7, A8), the secret store (A13, A38), typed egress (A44), host-side permission prompts (R-A20) and the Instagram pattern for a per-account publishing actor (A49). So Pinterest is a native adapter over Pinterest REST API v5.

## 1. Decisions

| # | Decision |
|---|---|
| D-P1 | **Pinterest is a comms actor**, `pinterest`, with transport `pinterest`. `ADAPTER_CONTRACTS` gains `"pinterest": {capability, admin}` (an amendment to A18's list). No context source: Pinterest reads are served by their own tools, as Instagram's are (R-IG2). |
| D-P2 | **API v5 only**, `https://api.pinterest.com/v5/…` ✅, pinned in code. An account marked `sandbox` in `comms.json` is pinned to `https://api-sandbox.pinterest.com` ✅ instead; Sandbox cannot make video Pins ✅. The deprecated v3 and the `client_credentials` grant are never used. |
| D-P3 | **No ceremony (D5).** `comms_pinterest_pin_preview` is read-only and returns exactly what a `pin_create` would do. `pin_create`, `pin_delete` and `board_create` carry `requires_user_interaction` (public or irreversible), so Claude Code prompts on every call. Comms authority stays `owner_full_admin`. |
| D-P4 | **OAuth 2.0 authorization code, continuous refresh.** The owner opens the authorization URL (`comms transport pinterest auth-url <alias>` prints it), signs in, and types the returned `code` at the hidden prompt of `comms transport pinterest account add <alias>`. The daemon exchanges it at `POST /v5/oauth/token` with `Authorization: Basic base64(app_id:app_secret)` ✅ and keeps **two staged secrets per account**: `pinterest-access-token.<alias>` (30 days ✅) and `pinterest-refresh-token.<alias>` (60 days, refreshable indefinitely ✅). The app secret is the static purpose `pinterest-app-secret`; the app id and redirect URI are non-secret settings in `comms.json`. |
| D-P5 | **Accounts are refs.** An account is `pna_`. Its Pinterest user id is an identity inside SQLCipher `comms.db`, read only through `comms_admin_identity_inspect` (A44, A45). Reads resolve `account` by alias, else `pinterest.default`. **Writes require `account`**, and every result echoes the live `username` under `untrusted`. |
| D-P6 | **Egress.** `PinterestApi` pins one origin per account through `pinned_client`; the token travels only in `Authorization: Bearer`. A video's bytes go once to the `upload_url` Pinterest returns (`pinterest-media-upload.s3-accelerate.amazonaws.com` ✅ in the reference), through `suffix_pinned_client(("amazonaws.com",))`, with **no** Authorization header ✅ (🧪 GP-4 pins the real host). A Pin's image URL and link the model supplies are validated syntactically (`transports/instagram/urls.py`'s `public_url`, one copy) and passed to Pinterest, which fetches the image; comms never fetches them (A26). |
| D-P7 | **Publishing is one CREATE per Pin on the `pnp_` ledger**, with a comms-side ceiling. Pinterest creates a Pin in one call (`POST /v5/pins` ✅, no container). comms records every Pin it created (`pinterest_publications`) and refuses a create once the account made `daily_pin_budget` Pins in the rolling 24 hours (default 50; ℹ️ comms' own ceiling against a runaway agent, below Pinterest's Trial `org_write` 300 a day ✅). A video Pin names a `pnv_` whose upload comms made and whose status it reads once (`GET /v5/media/{id}` ✅) before creating the Pin: not `succeeded` is `FAILED MEDIA_NOT_READY` (or `MEDIA_FAILED`), nothing sent. |
| D-P8 | **Video upload is one CREATE** (`comms_pinterest_video_upload`): register (`POST /v5/media {media_type: video}` ✅), then one multipart POST of the staged file to `upload_url` with every `upload_parameters` field ✅ (204 ✅). The bytes come from the existing memory-only staged upload (`upl_`, 16 MiB cap, G8/D3): a video over 16 MiB is out of v1. The `pnv_` ledger row is written as soon as Pinterest answers a `media_id` and the upload returns. The `upload_url` and its parameters are AWS-signed and short-lived: they are never stored or returned. |
| D-P9 | **Analytics are reads with a closed metric set** from the OpenAPI description (`StandardPinMetricTypes`, `VideoPinMetricTypes`, the account's `QuerymetrictypesItems` ✅); dates are `YYYY-MM-DD`, at most 90 days back and 90 days wide ✅. Numbers only leave; `data_status` is passed as a closed enum. |
| D-P10 | **Non-goals:** ads, catalogs, shopping and billing (other scopes, other tools); board sections, board edit and delete; saving another user's Pin; secret boards and Pins (`*_secret` scopes are never requested); follower and following lists; search; comments (Pinterest's API has no comment endpoint ✅); webhooks (Pinterest has none for organic content ✅); automatic token refresh in the daemon (v2; the doctor warns ten days ahead and `token refresh` is one command). |
| D-P11 | **Trial access** (Pinterest's first tier) makes Pins and boards visible only to their creator ✅; Standard access needs Pinterest's review with an OAuth video demo ✅. comms cannot tell the tiers apart from the API, so `comms_pinterest_whoami` says nothing about visibility; the runbook does. |
| D-P12 | **`comms-spec-v0.3.md` is not edited by this proposal.** Adoption follows the A49 precedent: ruling R-PN0 in `docs/verification/comms-v0.3-rulings.md`, A50 appended, the spec re-pinned. |
| D-P13 | **Every call fits 30 seconds.** No tool polls. An API call has one 15 s timeout; the one upload has one 25 s timeout and a 16 MiB body; a write makes at most three network calls (`video_upload`: register and upload; `pin_create` for a video: status, then create). |

## 2. Pinterest facts (checked)

**API:** Pinterest REST API v5, base `https://api.pinterest.com/v5` ✅; a sandbox host `https://api-sandbox.pinterest.com` ✅ serving the same paths for Pins, boards, media and user accounts, not video Pins ✅. Bearer tokens ✅. Pagination by `bookmark` (`page_size` 1 to 250, default 25; the last page's `bookmark` is `null`) ✅.

**OAuth (✅):** authorization at `https://www.pinterest.com/oauth/?client_id=&redirect_uri=&response_type=code&scope=&state=`; token at `POST https://api.pinterest.com/v5/oauth/token`, `Authorization: Basic base64(client_id:client_secret)`, form `grant_type=authorization_code&code=&redirect_uri=` or `grant_type=refresh_token&refresh_token=`. Response: `access_token` (`pina…`, `expires_in` 2,592,000 s = 30 days), `refresh_token` (`pinr…`, `refresh_token_expires_in` 5,184,000 s = 60 days), `token_type` `bearer`, `scope`. Apps created on or after 25 September 2025 get the continuous refresh token automatically; older apps pass `continuous_refresh=true` ✅ (comms always sends it: harmless either way ℹ️). A refresh answers a new access token, and may answer a new refresh token 🧪 GP-2; comms keeps whichever it is given.

**Scopes (✅):** `boards:read`, `boards:write`, `pins:read`, `pins:write`, `user_accounts:read`. Never `*_secret`, never `ads:*`.

**Identity (✅):** `GET /v5/user_account` answers `id` (numeric), `username`, `account_type` (`PINNER`, `BUSINESS`), `business_name`, counts, `monthly_views`. comms compares `id`.

**Rate limits (✅):** Trial, 1,000 calls a day per app, `org_write` 300 a day; Standard, per minute per user per app (`org_read` 1,000, `org_write` 100, `org_analytics` 60). Headers `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset` on every answer. A refusal is HTTP 429.

**Errors (✅ shape):** `{"code": <int>, "message": "…"}` with the HTTP status; apps registered on or after 14 September 2026 may answer 403 `PINNER_DATA_ACCESS_DENIED` for a non-business user's board or Pin ✅. comms classifies by HTTP status (section 8); the message is untrusted and never leaves.

**Pins (✅):** `POST /v5/pins` body: `board_id` (numeric), `title` ≤ 100, `description` ≤ 800, `link` ≤ 2048, `alt_text` ≤ 500, `board_section_id`, `dominant_color`, `ai_disclosures.values[]` of `AI_MODIFIED` or `SYNTHETIC_PERFORMER`, `media_source` one of `image_url {url}`, `multiple_image_urls {items[2..5] of {url, title, description, link}, index}`, `video_id {media_id, cover_image_url | cover_image_data+cover_image_content_type | cover_image_key_frame_time}`, and (never used here) `image_base64`, `multiple_image_base64`, `pin_url`. Answer: the Pin (`id`, `created_at`, `creative_type`, `media.media_type`, `board_id`, `is_owner`). `PATCH /v5/pins/{id}` edits title, description, link, alt text and board; `DELETE /v5/pins/{id}` answers the Pin. Video processing takes seconds; `creative_type` reads `REGULAR` until it is `VIDEO` ✅. A video Pin needs a cover image or the request is 400 ✅.

**Media (✅):** `POST /v5/media {media_type: "video"}` answers `media_id`, `upload_url`, `upload_parameters` (S3 presigned POST fields: `key`, `policy`, `x-amz-*`, `Content-Type`); the file is POSTed as `multipart/form-data` with every parameter as a field plus `file` (`.mp4`, `.mov`, `.m4v`); 204 on success; `GET /v5/media/{media_id}` answers `status` in `registered`, `processing`, `succeeded`, `failed`.

**Boards (✅):** `GET /v5/boards` (`privacy` filter), `GET /v5/boards/{id}`, `GET /v5/boards/{id}/pins`, `POST /v5/boards {name, description, privacy}`. Up to 2,000 boards per account; 200,000 Pins ✅.

**Analytics (✅):** `GET /v5/pins/{id}/analytics?start_date&end_date&metric_types&app_types&split_field` (category `org_analytics`, no sandbox); `GET /v5/user_account/analytics?start_date&end_date&metric_types&from_claimed_content&pin_format&app_types&content_type&source&split_field`. Answers keyed `ALL` (or a split) to `{summary_metrics, daily_metrics[{date, metrics, data_status}], lifetime_metrics}`.

**Sizes (ℹ️ third-party guides; Pinterest's Pin-specs page is behind the site's JavaScript):** images 2:3 recommended (1000 × 1500), JPEG or PNG; video `.mp4`, `.mov`, `.m4v`, 4 s to 15 min, up to 2 GB on Pinterest (16 MiB through comms, D-P8).

## 3. The actor

```
src/comms/transports/pinterest/
  __init__.py
  http.py        # PinterestApi: pinned origin, Bearer, one call per request; token exchange with Basic
  upload.py      # the one multipart POST of a staged video to Pinterest's upload_url
  config.py      # the comms.json section (app_id, redirect_uri, default, daily_pin_budget, accounts)
  store.py       # the four v12 tables: accounts, objects (boards, pins), media uploads, publications
  accounts.py    # the configured accounts at runtime, the lazy /user_account identity check
  capability.py  # PinterestCapability: snapshot per account (ceiling, identity)
  classify.py    # HTTP-status classification for writes; read refusals
  items.py       # board, pin, profile, analytics items; untrusted text
  publish.py     # pin_create, pin_update, pin_delete, board_create, video_upload; quota; preview checks
  admin.py       # PinterestAdmin: validate() and invoke() for every write capability
  doctor.py      # per-account findings
src/comms/core/providers/pinterest_analytics.py  # the metric tables, data only
src/comms/mcp/tools/pinterest.py   # the 18 ToolSpec entries, in catalog order
src/comms/runtime/pinterest.py     # PinterestService, every tool's one service (A37; R-IG4)
src/comms/runtime/operator/pinterest.py  # the operator commands and PinterestOperator
```

`http.py` and `upload.py` are the only importers of `httpx` in the package and join `NETWORK_MODULES` (`tests/security/test_egress.py`). The access token is read from the secret store once, shape-checked (`[A-Za-z0-9_.\-]{20,2048}`, comms' rule ℹ️), sent only in `Authorization`, and never appears in a URL, a log, a `repr` or an error. Every id joins a path only after `\A[0-9]{1,24}\Z`; every resource is one of a closed set (`user_account`, `boards`, `pins`, `media`, `oauth/token`, and the `pins`, `analytics` sub-resources). The app secret is read for one `oauth/token` call and dropped. Transport errors are `GraphTransportError("not_sent" | "ambiguous")` (one copy, `transports/whatsapp/cloud/http.py`).

**Wiring:** `runtime/adapters.py` gains `pinterest_adapters(adapters, conn, secrets, settings, clock, *, transport=None)`: for each alias configured, registered and holding an active access token it builds one `PinterestApi`; `adapters.capability["pinterest"]`, `adapters.admin["pinterest"]`, `adapters.pinterest` (the accounts), `adapters.pinterest_publisher`. No network at boot. The same `transport` seam feeds the upload client, so `comms selftest-daemon` scripts both hosts.

## 4. Accounts

### 4.1 Refs and identities
- New prefixes in `CORE_PREFIXES`: `pna_` (account), `pnb_` (board), `pnp_` (Pin), `pnv_` (a video upload). Disjoint from every other registry (`test_v03_prefixes_disjoint_from_telegram_whatsvault_and_5b4`).
- Aliases follow the Instagram grammar (`[a-z0-9_-]{1,32}`, none of the secret-like words), one copy in `core/keys/purposes.py`.
- A `pna_` row holds alias, `user_id`, `access_expires_at`, `refresh_expires_at`, `last_identity_check_at`, `removed_at`. A `pnb_` or `pnp_` row holds account, kind and the provider identity. A `pnv_` row holds account, `media_id`, `created_at`, `status` as last seen. A `pinterest_publications` row holds the account and the `pnp_` object a `pin_create` made, with its time: the budget ledger. Schema migration **v12**; no existing table changes.

### 4.2 Secret purposes (A9, A13, A38)
- `pinterest-app-secret`: static, `opaque`, `staged`, destroyed `at_rotation`. Its proof is local: printable ASCII, 16 to 256 characters (Pinterest gives no whoami for an app secret alone).
- `pinterest-access-token.<alias>` and `pinterest-refresh-token.<alias>`: `opaque`, `staged`, `at_rotation`, parameterised by alias like `meta-ig-access-token.<alias>`.
- Proof on `account add`: the exchanged access token must answer `GET /v5/user_account` with a numeric `id` not held by another live account. On `token refresh`: the new access token must answer the registered `id`.

### 4.3 Settings (`comms.json`, non-secret, no identities)
```json
"pinterest": {
  "app_id": "1234567",
  "redirect_uri": "https://raoof128.github.io/comms-mcp/pinterest/",
  "default": "sarabi",
  "daily_pin_budget": 50,
  "accounts": {
    "sarabi": {"label": "Sarabi's Fine Rugs", "writes": true, "sandbox": false}
  }
}
```
`app_id` is 1 to 32 digits; `redirect_uri` an `https` URL registered in the Pinterest app; `daily_pin_budget` 1 to 300; `writes` is the per-account ceiling (a refused write never reaches Pinterest); `sandbox` pins the account to the sandbox host.

### 4.4 Operator commands (A37, never tools)
- `comms transport pinterest auth-url <alias>`: prints the authorization URL with the five scopes and a fresh `state`; no network.
- `comms transport pinterest account add <alias>`: reads the authorization `code` at the hidden prompt (`_VALUE_FROM_STDIN`, as the Instagram token), exchanges it, proves the access token, stages both tokens (A13 rotation), records the `pna_` in one audited transaction (`admin.pinterest_account` `added`), reloads the adapters.
- `comms transport pinterest account list|remove <alias>`; `comms transport pinterest token refresh --alias <alias> | --all` (the refreshed tokens are proved and rotated; the row's expiries move); `comms transport pinterest doctor` (live identity probe).
- `comms credential set pinterest-app-secret` (the static credential path).

### 4.5 Per-call safety
As Instagram's: the first use of an account in a daemon's lifetime calls `GET /v5/user_account` and compares `id`; a mismatch blocks the alias (`IDENTITY_MISMATCH`) until the operator re-adds it. The live `username` is echoed under `untrusted`, never stored.

## 5. Tool catalog (18 tools, `comms_pinterest_*`)

Every tool but `account_list` takes `account`. A page's `next_cursor` is a client-bound `cur_` wrapping Pinterest's `bookmark` through `ContextHandles` (target `pna_`, actor `pinterest`).

### 5.1 Reads (13, no `request_id`)

| Tool | Pinterest call | Result |
|---|---|---|
| `account_list` | none | configured accounts: alias, `pna_`, registered, `writes`, `sandbox`, days left on both tokens, label |
| `whoami` | `GET /user_account` | identity checked, both expiries |
| `profile_get` | `GET /user_account` | `account_type`, board, Pin, follower, following counts, `monthly_views`; `username`, `business_name`, `website_url` untrusted |
| `board_list` | `GET /boards?privacy=` | boards (`pnb_`, privacy, pin and follower counts; name and description untrusted), paged |
| `board_get` | `GET /boards/{id}` | one board |
| `board_pins` | `GET /boards/{id}/pins` | Pins on a board (`pnp_`), paged |
| `pin_list` | `GET /pins` | the account's Pins, newest first, paged |
| `pin_get` | `GET /pins/{id}?pin_metrics=` | one Pin: `pnb_`, `created_at`, `creative_type`, `media_type`, `is_owner`; title, description, link, alt text untrusted; optional 90-day and lifetime metrics |
| `pin_analytics` | `GET /pins/{id}/analytics` | summary, daily and lifetime metrics for a date range |
| `account_analytics` | `GET /user_account/analytics` | the account's metrics for a date range |
| `media_status` | `GET /media/{id}` | a `pnv_`'s status |
| `publish_quota` | none | Pins created in the last 24 h against `daily_pin_budget`; the rate-limit remaining and reset last seen |
| `pin_preview` | `GET /media/{id}` for a video | exactly what `pin_create` would make, policy and budget verdict, `preview_digest`; makes nothing |

### 5.2 Writes (5, `account` and `request_id`)

| Tool | Capability | Pinterest call | Prompt |
|---|---|---|---|
| `board_create` | `board.create` | `POST /boards` | yes (public) |
| `video_upload` | `media.upload` | `POST /media`, then the upload | no |
| `pin_create` | `pin.create` | (`GET /media/{id}` for a video,) `POST /pins` | yes (public) |
| `pin_update` | `pin.update` | `PATCH /pins/{id}` | no |
| `pin_delete` | `pin.delete` | `DELETE /pins/{id}` | yes (irreversible) |

Arguments: `pin_create` takes `board` (`pnb_`), `kind` (`image` with `url`; `carousel` with `images` 2 to 5 of `{url, title?, description?, link?}`; `video` with `media` (`pnv_`) and `cover_url`), `title`, `description`, `link`, `alt_text`, `ai_disclosures`, and an optional `preview_digest`. `pin_update` takes `pin` and any of `title`, `description`, `link`, `alt_text`, `board`. `board_create` takes `name` (1 to 180), `description`, `privacy` (`PUBLIC` or `PROTECTED`; never `SECRET`). `video_upload` takes `upload` (`upl_`, mime `video/mp4`, `video/quicktime` or `video/x-m4v`).

### 5.3 Capabilities and semantics

New capabilities, all offered by `pinterest` only: capability `board.list`, capability `board.get`, capability `board.create`, capability `pin.list`, capability `pin.get`, capability `pin.create`, capability `pin.update`, capability `pin.delete`, capability `media.status_read`. Reused: capability `profile.read` and capability `insights.read` and capability `publishing.quota_read` (shared with `instagram`), capability `media.upload` (shared with `telegram_user` and `whatsapp_cloud`).

Semantics: `board.create`, `pin.create` and `media.upload` are `CREATE` (`none`, `resolve_only`); `pin.update` is `SET_STATE`; `pin.delete` is `DESTRUCTIVE_NONIDEMPOTENT`; the rest are reads. comms never retries a CREATE: an ambiguous outcome is `OUTCOME_UNKNOWN`, resolved by the owner through `pin_list` or `media_status`.

## 6. Publishing behaviour

- **Budget before Pinterest.** `pin_create` counts `pinterest_publications` in the last 24 h; at or over `daily_pin_budget` it answers `FAILED PIN_BUDGET` with nothing recorded at Pinterest. Pinterest's own answer is final (A25).
- **Preview digest.** `pin_preview` returns `sha256("comms-pinterest-preview/v1\0" || JCS({tool, account, args}))`; a `pin_create` that echoes a `preview_digest` is refused (`INVALID_ARGUMENT`) when its arguments differ from the preview's.
- **Video.** `pin_create` with `kind: video` reads the `pnv_`'s status once: `succeeded` proceeds; `registered` or `processing` is `FAILED MEDIA_NOT_READY` (call again later with a new `request_id`); `failed` is `FAILED MEDIA_FAILED`. The ledger row records the status seen.
- **Ledger.** A created Pin is a `pnp_` object and a publication row at once (the executor's `on_created`), so a crash after Pinterest's answer never loses a Pin the budget must count.
- **Trial visibility.** Under Trial access a created Pin is visible only to the creator ✅; comms reports `SUCCEEDED` either way (D-P11).

## 7. Analytics

`pin_analytics`: `metric_types` from the union of `StandardPinMetricTypes` and `VideoPinMetricTypes` (`IMPRESSION`, `OUTBOUND_CLICK`, `PIN_CLICK`, `SAVE`, `SAVE_RATE`, `TOTAL_COMMENTS`, `TOTAL_REACTIONS`, `USER_FOLLOW`, `PROFILE_VISIT`, `VIDEO_MRC_VIEW`, `VIDEO_10S_VIEW`, `QUARTILE_95_PERCENT_VIEW`, `VIDEO_V50_WATCH_TIME`, `VIDEO_START`, `VIDEO_AVG_WATCH_TIME`), `app_types` in `ALL|MOBILE|TABLET|WEB`, `split_field` `NO_SPLIT` only. `account_analytics`: `metric_types` from `ENGAGEMENT`, `ENGAGEMENT_RATE`, `IMPRESSION`, `OUTBOUND_CLICK`, `OUTBOUND_CLICK_RATE`, `PIN_CLICK`, `PIN_CLICK_RATE`, `SAVE`, `SAVE_RATE`, plus `from_claimed_content`, `pin_format`, `content_type`, `source`, `app_types`. Both take `start_date` and `end_date` (`YYYY-MM-DD`; checked for order, the 90-day look-back and the 90-day span before any call). Results: `summary` (name to number), `daily` (date, `data_status`, name to number), `lifetime` (name to number) under the `ALL` key.

## 8. Error classification (`classify.py`)

Writes, by HTTP status: 2xx with a JSON object is `SUCCEEDED` (the Pin or board `id`, or the `media_id`, as the provider ref); 400 and 409 are `FAILED_PERMANENT INVALID_ARGUMENT`; 401 is `FAILED_TRANSIENT CREDENTIAL`; 403 is `FAILED_PERMANENT NOT_AUTHORIZED`; 404 is `FAILED_PERMANENT NOT_FOUND`; 429 is `FAILED_TRANSIENT RATE_LIMITED`; 5xx, a non-JSON body and any transport failure after connecting are `OUTCOME_UNKNOWN`; a connection never made is `FAILED PROVIDER_UNAVAILABLE`. The upload: 2xx is success; 4xx is `FAILED UPLOAD_FAILED`; else `OUTCOME_UNKNOWN`. Reads: 401 and 403 `NOT_AUTHORIZED`, 404 `NOT_FOUND`, 400 `INVALID_ARGUMENT`, 429 `RATE_LIMITED` (with `retry_after` from `x-ratelimit-reset` when numeric), else `PROVIDER_UNAVAILABLE`.

## 9. Hosts

`pin_create`, `pin_delete` and `board_create` carry `requires_user_interaction` (`_meta` `anthropic/requiresUserInteraction`, as A49's four). The five writes join `.claude/settings.json`'s `permissions.ask` (R-A20).

## 10. Security (A44 mapping)

- **Identities** (`user_id`, board, Pin and media ids) never leave except through `comms_admin_identity_inspect`.
- **Bodies** (titles, descriptions, board names, usernames, links Pinterest returns) only under `untrusted` or `untrusted_text`, control characters stripped, bounded.
- **Secrets:** the app secret, both tokens and the upload parameters never appear in a tool result, an audit row, a log line, a `repr` or an error.
- **Hostile text produces no write:** a Pin's title or description is never an argument source; the model names refs.
- **Egress:** two pinned API origins (production, sandbox) and the upload suffix; the model's URLs go to Pinterest and nowhere else.

## 11. Testing and gates

Unit and runtime tests over a recording fake of `api.pinterest.com` and the upload host (`tests/transports/pinterest/fakes.py`, `world.py`); conformance cases (`tests/conformance/pinterest.py`); the daemon smoke (`scripts/smoke_daemon.py` `drive_pinterest`) through the installed binary against `comms selftest-daemon`'s scripted Pinterest; the exit test `tests/security/test_pinterest_exit.py`. Live gates (owner-run, `docs/runbooks/live-acceptance-pinterest.md`): GP-1 OAuth exchange and `GET /user_account` with the header only; GP-2 refresh: which tokens come back; GP-3 one image Pin to a test board, read back, edited, deleted; GP-4 one short video: the real upload host, status to `succeeded`, a video Pin with a cover; GP-5 analytics on a real Pin and the account; GP-6 Trial visibility and the rate-limit headers; GP-7 the prompts in Claude Code and Desktop.

## 12. Code changes this proposal requires

1. `core/providers/capability.py`: the nine new members. `semantics.py`: `PINTEREST`, `_PINTEREST_CAPS`, `READS`, `_CREATES`, `_DESTROYS`, shared capabilities. `protocols.py`: `ADAPTER_CONTRACTS["pinterest"]`.
2. `core/refs.py`: the four prefixes. `core/identities.py`: the Pinterest tables. `core/domains.py`: `PINTEREST_PREVIEW`. `core/errors.py`: `MEDIA_NOT_READY`, `MEDIA_FAILED`, `UPLOAD_FAILED`, `PIN_BUDGET` are result codes, not `CommsError` codes; no new `CommsError` code.
3. `core/storage/migrations.py`: v12. `core/keys/purposes.py`: `pinterest-app-secret`; the two alias-parameterised prefixes; `purpose_of`. `core/audit/specs.py`: actor `pinterest`; `admin.pinterest_account`.
4. `mcp/schemas.py` `ACTORS`; `mcp/catalog.py` `_TRANSPORT`; `mcp/tools/pinterest.py`; `mcp/tools/__init__.py`; `mcp/egress.py`; `mcp/tools/account.py` (identity inspect kinds).
5. `runtime/{adapters,settings,assemble,comms_runtime,facades,selftest,doctor,proofs}.py`; `runtime/pinterest.py`; `runtime/operator/{pinterest,__init__}.py`; `cli_commands/operator.py`.
6. `transports/pinterest/*`; `core/providers/pinterest_analytics.py`.
7. Tests, pins (`tests/mcp/catalog_pin.json` regenerated once per task), `.claude/settings.json`, the actor matrix, the smoke map, the runbooks, `README.md`, `CLAUDE.md`, `AGENT.md`, `CHANGELOG.md`.

## 13. Open questions (none block the build)

1. Whether a refresh answers a new refresh token (GP-2). comms rotates whatever comes back.
2. The real upload host suffix (GP-4). `amazonaws.com` is pinned as the suffix; the live host is recorded.
3. Whether Standard access review needs the OAuth demo from comms' CLI (Pinterest accepts terminal recordings ✅). Owner's step.
4. The redirect URI: a static page under `site/pinterest/` that shows the `code` for copying is the simplest; it is not part of this proposal.

## References

- Pinterest API v5 reference and the OpenAPI description, `pinterest/api-description` v5 (`5.28.0`), read 2 November 2026.
- Authentication and scopes; access tiers; rate limits; pagination; sandbox; create boards and Pins: `developers.pinterest.com/docs/…`, read 2 November 2026.
- `docs/instagram-spec-v0.6.md` (A49), the blueprint.
