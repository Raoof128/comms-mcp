# Live acceptance: Pinterest (proposed A50)

Owner-run, on a Pinterest **business** account you own, with writes only to a test board you are
happy to delete in the Pinterest app. Under Trial access every Pin and board the API creates is
visible only to you, so a test under Trial disturbs nothing public. The results are evidence,
never a gate: the conformance run writes `docs/verification/live-acceptance/<date>.json`, and the
gate table below is pasted, filled, into `docs/verification/live-acceptance/<date>-pinterest.md`.
Spec: `docs/pinterest-spec-v0.1.md`, sections 2, 4, 11.

## Prepare, once

1. At [Pinterest Developers](https://developers.pinterest.com/) create an app on the business
   account, request Trial access, and register the redirect URI you will put in `comms.json`
   (a page you control; the code arrives in its query string). Note the app id and secret.
2. Describe the account in `comms.json` (no secret, no ids), for example
   `"pinterest": {"app_id": "<app id>", "redirect_uri": "https://…/pinterest/", "default": "test", "accounts": {"test": {"label": "Test", "writes": true, "sandbox": false}}}`.
3. Store the app secret, then add the account. The secret and the authorization code are typed
   at the hidden prompt, never piped, passed or put in a file:

   ```bash
   comms credential set pinterest-app-secret
   comms transport pinterest auth-url test
   comms transport pinterest account add test
   comms transport pinterest account list
   comms transport pinterest doctor
   ```

   `auth-url` prints the URL to open; after you approve the five scopes, copy the `code` from the
   redirect and give it to `account add`, which exchanges it, proves the access token with
   `GET /v5/user_account`, stages both tokens and records the `pna_`.
4. Describe the account for the conformance run, identifiers only, in a JSON file outside the
   repository: `{"pinterest": {"account": "test"}}`.

## Run the conformance cases

```bash
COMMS_LIVE_ACCOUNTS=/path/outside/repo/accounts.json \
  uv run pytest tests/conformance/test_live_acceptance.py --run-live-acceptance -q -s
```

Until the accounts description names an adapter, its cases report `NOT_CONFIGURED`.

## The live gates

Run GP-1 first. If it fails, stop: Pinterest work waits for a ruling.

| Gate | How | Expected | Fallback |
|---|---|---|---|
| GP-1 | `account add` with a real code, then `comms transport pinterest doctor` and `comms_pinterest_whoami` | the exchange answers both tokens; every call carries the token only in `Authorization: Bearer`; the doctor is `OK` | record the refusal and stop |
| GP-2 | `comms transport pinterest token refresh --alias test` | a new access token; note whether a new refresh token came back (`refresh_token_rotated`) and the new expiries in `account list` | open question 1: rotate whatever comes back |
| GP-3 | `comms_pinterest_board_create` (a test board), `comms_pinterest_pin_preview` then `comms_pinterest_pin_create` with one public `https` image you control, `comms_pinterest_pin_get`, `comms_pinterest_pin_update` (a new title), `comms_pinterest_pin_delete` | one Pin on the test board, read back by its `pnp_`, edited, then gone; `publish_quota` counts 1 | none inside D-P7: record |
| GP-4 | stage a short `.mp4` under 16 MiB with `comms_media_stage_begin` and `comms_media_stage_chunk`, then `comms_pinterest_video_upload`, `comms_pinterest_media_status` until `succeeded`, then `pin_create` with `kind` `video` and a cover image URL | the upload host is under `amazonaws.com` (record the exact host); the Pin's `creative_type` reads `VIDEO` once processed | widen or narrow `UPLOAD_SUFFIXES` by ruling |
| GP-5 | `comms_pinterest_pin_analytics` on a real Pin and `comms_pinterest_account_analytics` over the last 30 days | numbers under `summary` and `daily`; `data_status` values match the closed set | trim the metric tables by ruling |
| GP-6 | under Trial access, open the created Pin from another account; call any read twice and read `comms_pinterest_publish_quota` | the Pin is invisible to others (Trial); `rate_limit_remaining` moves | document the tier in the README |
| GP-7 | in Claude Code, call `comms_pinterest_pin_create`, `board_create` and `pin_delete` in default and bypass modes; repeat in Claude Desktop | Claude Code prompts on every call; record Desktop's behaviour | the ask rules in `clients-claude-code.md` |

## Afterwards

Delete the test Pins and the test board in the Pinterest app, then remove the account and revoke
the app's access in Pinterest's settings:

```bash
comms transport pinterest account remove test
```

Keep both evidence files.
