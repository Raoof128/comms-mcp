# Live acceptance: Instagram (proposed A49)

Owner-run, on a **throwaway** public professional account (Business or Creator) that you own,
with writes only on a test post you are happy to delete in the Instagram app. The results are
evidence, never a gate: the conformance run writes `docs/verification/live-acceptance/<date>.json`,
and the gate table below is pasted, filled, into
`docs/verification/live-acceptance/<date>-instagram.md`. Spec: `docs/instagram-spec-v0.6.md`,
sections 2, 11 and 13.

## Prepare, once

1. In the Meta app (Instagram API with Instagram Login), add the throwaway account as a tester,
   accept the invite in the Instagram app, and generate its dashboard token with only the scopes
   its policy needs (`instagram_business_basic`, plus `content_publish`, `manage_comments`,
   `manage_insights`, `manage_messages` as the gates below require).
2. Describe the account in `comms.json` (no token, no ids), for example
   `"instagram": {"default": "test", "accounts": {"test": {"label": "Throwaway", "writes": true, "dms": true}}}`.
3. Add it. The token is typed at the hidden prompt, never piped, passed or put in a file (R-IG2):

   ```bash
   comms transport instagram account add test
   comms transport instagram account list
   comms transport instagram doctor
   ```

   `account add` proves the token with `GET /me` before it is active and records the `iga_`.
4. Describe the account for the conformance run, identifiers only, in a JSON file outside the
   repository: `{"instagram": {"account": "test"}}`.

## Run the conformance cases

```bash
COMMS_LIVE_ACCOUNTS=/path/outside/repo/accounts.json \
  uv run pytest tests/conformance/test_live_acceptance.py --run-live-acceptance -q -s
```

Until the accounts description names an adapter, its cases report `NOT_CONFIGURED`.

## The live gates

Run GI-1 first. If it fails, stop: Instagram work waits for a ruling (spec open question 4).

| Gate | How | Expected | Fallback |
|---|---|---|---|
| GI-1 | `comms transport instagram doctor` (a read with the header), one `comms_instagram_comment_hide` round trip on the test post, and `comms transport instagram token refresh --alias test` once the token is 24 hours old | every call answers with the token only in `Authorization: Bearer`, including `/refresh_access_token` | none inside A26: record the refusal and stop |
| GI-2 | refresh again after 24 hours; switch the account to private and call `comms_instagram_whoami` | refresh succeeds and `doctor` shows the new expiry; a private account is refused | document "the account must be public"; refresh on schedule |
| GI-3 | `comms_instagram_publish_quota` | `quota_total` is 50 or 100 | use the returned value; 50 as the conservative cap |
| GI-4 | `comms_instagram_media_list` with `instagram.caption` false, then true | captions arrive only when enabled; no `media_url` is ever asked for | keep `caption` off by default |
| GI-5 | `comms_instagram_media_insights` and `comms_instagram_account_insights` on real posts, including `follower_type`; note any code 4, 17, 32, 613 or 190 | the metric tables match; each code maps as section 8 says | trim the tables; extend `IG_CODES` by ruling |
| GI-6 | in Claude Code, call `comms_instagram_publish`, `comment_reply`, `comment_delete` and `message_send` in default and bypass modes; repeat in Claude Desktop | Claude Code prompts on every call; record Desktop's behaviour | the ask rules in `clients-claude-code.md` |
| GI-7 | connect `comms mcp --stdio` under Claude Code with `MCP_PROTOCOL_NEGOTIATION` unset, `auto` and `legacy`, and under Desktop | `/mcp` shows `comms` connected with every tool | pin the working `mcp` version; raise it with the SDK |
| GI-8 | `comms_instagram_conversation_list` and `conversation_messages` after a friend's account DMs the test account; then `comms_instagram_message_send` inside 24 hours | one `igp_` per counterpart, the 20 newest messages, one reply sent; outside 24 hours `WINDOW_CLOSED` | fetch details per message with throttling |

The publishing path (`container_create`, `publish_preview`, `publish`) is exercised on GI-3's
run: one image container from a public `https` URL you control, published once, then deleted in
the Instagram app. Then one Story (`kind` `story_image`, a 9:16 JPEG): it must publish, and
`comms_instagram_media_get` on its `igm_` reads `media_type` `IMAGE` (Meta's documented answer for
a Story). It disappears by itself after 24 hours.

## Afterwards

Delete the test post, its comments and DMs in the Instagram app, then remove the account and
revoke the token in Instagram's settings:

```bash
comms transport instagram account remove test
```

Keep both evidence files.
