# Live acceptance: Instagram (proposed A49), 2026-10-05

Evidence, never a gate. Runbook: `docs/runbooks/live-acceptance-instagram.md`. Times are
Australia/Sydney.

## Setup

| Field | Value |
|---|---|
| Account | @punpun.r12, `MEDIA_CREATOR`, public, 116 followers, 0 posts at start |
| Alias and policy | `main`, `writes: true`, `dms: true` (`instagram.default` is `main`) |
| Account ref | `iga_akejch7j6q3tbjh6snuj6n2ftw` |
| Meta app | W-Vault (Instagram app W-Vault-IG); punpun.r12 is an Instagram Tester, invite accepted 2026-10-05 |
| Scopes added on the app | `instagram_business_basic`, `instagram_business_manage_comments`, `instagram_business_manage_messages` |
| Token | dashboard token, typed at the hidden prompt in Terminal.app; proved by `GET /me`; expires 2026-12-04T05:04:20Z |
| comms | `main` at `1f66f3e` plus the audit-trail commit `da2ea47`; daemon run as the owner's user (`--state-dir`/`--runtime-dir` under `~/Library/Application Support/comms`, `local_port` 8866) |
| Client | a scripted MCP stdio client (`mcp` SDK) over `comms mcp --stdio --client-seed … --daemon http://127.0.0.1:8866 --runtime-dir …`; 154 tools listed, 24 Instagram |

**Deviation from the runbook.** The owner chose their real account rather than a throwaway. Every
write was approved in chat beforehand (image, exact caption and target), and the test post was
deleted afterwards. Because the client was scripted, Claude Code's `requiresUserInteraction` prompt
was not exercised; that is GI-6, still pending.

**Setup notes.**
- `comms transport instagram account add` refuses without a TTY ("credential values are entered
  interactively, at a terminal"); Claude Code's `!` prefix is not one. Run it in a real terminal.
- Meta's "add Instagram tester" box refused punpun.r12 ("Unable to add a user with a role on the
  app's owning business"). The API-setup page's "Add account" flow, signed in to Instagram as the
  account, sent the invite; accepting it under Apps and websites → Tester invites worked.

## The live gates

| Gate | Run | Result |
|---|---|---|
| GI-1 | `comms transport instagram doctor`; `comment_hide` true then false on the test post's comment, re-reading `comment_list` after each | **Partial pass.** Doctor `OK` with the token only in `Authorization: Bearer`; hide round trip read back `hidden: true` then `false`. Refresh (`token refresh --alias main`) waits for the token to be 24 hours old (after 2026-10-06 16:04) |
| GI-2 | refresh after 24 more hours; private-account refusal | **Pending.** The private switch may be skipped on this account |
| GI-3 | `publish_quota`; feed image and Story published | **Pass.** `quota_total` 100, `quota_duration` 86400. Image container → `publish` → `igm_apyvyxhsd6kkiaxtdpnpnkqfku`; live caption confirmed by the permalink's `og:description`. Story (`story_image`, 1080x1920 JPEG) published as `igm_akzarrhbibb45i3ij4xd4vfg5t`; `story_list` lists it (the `stories` edge answers on `graph.instagram.com`) and `media_get` reads `media_type` `IMAGE`. After both, `quota_usage` 1 and `containers_last_24h` 2 |
| GI-4 | `media_list`, `media_get`, `tag_list`, `story_list` with `instagram.caption` false | **Pass for caption off.** Items carry no caption and no `media_url`. The caption-on half was not run |
| GI-5 | `account_insights` (`reach`, `views`, `accounts_engaged`; `follower_demographics` by country, `this_month`); `media_insights` on the test post | **Pass.** Account totals 0; demographics empty (too few followers to report); post `reach` 0, `likes` 0, `comments` 1, `views` 16. No code 4, 17, 32, 613 or 190 seen |
| GI-6 | the four prompted writes in Claude Code and Claude Desktop | **Pending (owner).** Not exercised: the run used a scripted client |
| GI-7 | `/mcp` under Claude Code and Desktop | **Pending (owner).** The stdio proxy itself negotiated and listed 154 tools |
| GI-8 | `conversation_list`; `conversation_messages`; `message_send` inside 24 hours | **Partial, with a finding.** Lists of up to 20 succeed, and paging by 5 reaches conversation 24. Conversation 25 answers `PROVIDER_UNAVAILABLE` alone, so any page containing it fails and nothing after it can be listed. `conversation_messages` and `message_send` not run |

Other writes, all `SUCCEEDED`: `comment_reply` ("test reply") replayed with the same `request_id`
returned the same comment with `replayed: true` and made no second reply; `comment_replies` listed
it; `comment_delete` removed it and `comment_replies` then read empty.

## Findings

1. **One unsupported thread blocks the conversation list (GI-8).** `_counterpart` in
   `src/comms/transports/instagram/messages.py` raises `PROVIDER_UNAVAILABLE` for a thread without
   exactly one counterpart (likely a group thread). It fails the whole page instead of skipping or
   marking that thread, so the default `limit` (25) fails on this account and no cursor can pass
   it. Needs a ruling: skip the thread, or return it as unsupported.
2. **A deleted post reads `INVALID_ARGUMENT`.** `media_get` on the deleted test post answers
   `INVALID_ARGUMENT` (Meta code 100). `NOT_FOUND` would describe it; the read error table maps
   code 100 to `INVALID_ARGUMENT` by design (section 8). Minor; a ruling may refine it.

## Cleanup

- The test post was deleted in Instagram on 2026-10-05; `media_list` reads empty afterwards.
- The Story expires by itself about 2026-10-06 16:19. Story insights need five viewers.
- The two test images were served from GitHub Pages for the run only: added in `d79f2c1`, removed
  in `d41e8ef`.
- The account stays registered for GI-1's refresh, GI-2, GI-6, GI-7 and GI-8. Afterwards:
  `comms transport instagram account remove main` and revoke W-Vault-IG under Apps and websites.

## Still to run

- GI-1 and GI-2 token refreshes (2026-10-06 after 16:04, then a day later).
- GI-4 with `instagram.caption` true.
- GI-6 and GI-7 in Claude Code and Claude Desktop.
- GI-8 `conversation_messages` and one `message_send` to a person who wrote within 24 hours.
- `story_insights` once the Story has five viewers.
- Ruling R-IG0 (adopt A49), plus rulings on the two findings.
