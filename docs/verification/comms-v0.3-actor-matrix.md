# Comms v0.3 actor matrix: full admin on both APIs (spec A45; catalog amendment G6a)

**What this is.** One row for every catalog tool that reaches a provider, and one cell per
actor. The owner decided (A45, D2) that an operation an actor's API implements is implemented;
only a genuine API gap is `B`, reported by that actor's capability as `PROVIDER_UNSUPPORTED`.

**Cell grammar** (parsed by `tests/core/providers/test_actor_matrix.py`):

- `A done [capability]: <method>` means implemented, and `SUPPORT[capability]` includes the actor;
- `A todo:G<n> [capability]: <method>` means the API implements it and task G<n> will build it
  (G9's exit gate requires none left);
- `B [capability]: <reason>` means the API has no such operation, `SUPPORT[capability]` excludes
  the actor, and its capability reports `PROVIDER_UNSUPPORTED`;
- `B [capability] (groups): <reason>` means the capability exists for this actor in 1:1 chats, but
  not for the group-addressed tool; the tool refuses for this actor;
- `A done (local)` and `A todo:G<n> (local)` mean served from comms' own retained data (the bot's
  updates, the webhook archive), with no provider capability to hold;
- `— : <reason>` means the tool is not addressed to this actor at all (a WhatsApp account tool, a
  conversation-addressed tool); it answers by its own transport's configuration.

**How it is proved.** `tests/core/providers/test_actor_matrix.py` checks the claims three ways:
- **against `SUPPORT`;**
- **against the libraries:** every cited Telethon request exists, every implemented bot method is one the bot adapters use, and every implemented user request is pinned;
- **by behaviour:** each tool goes through the real dispatcher for each Telegram actor alone. `A done` succeeds; `B` and `A todo` are refused with no provider call. A `B` refusal is `PROVIDER_UNSUPPORTED`, or `NOT_CONFIGURED` when the only capable actor is not configured.

**Sources.**
- **Bot API:** Bot API 10.3 (24 August 2026), `core.telegram.org/bots/api` and its changelog; re-checked 2026-09-26.
- **MTProto:** Telethon 1.45.0's TL layer 229 (`functions.*`); every cited method re-checked against `core.telegram.org/methods` and its method page on 2026-09-26 (forum topics are `messages.*`, taking an `InputPeer`).
- **WhatsApp Cloud API:** the code pins Graph API v21.0 (`developers.facebook.com/documentation/business-messaging/whatsapp`), which **expires 21 January 2027**; Meta's current examples use v26.0 (29 July 2026). The Groups API reference (read 2026-09-25, re-checked 2026-09-26) supports:
  - create and delete a group; get and list groups;
  - update the subject, description and photo;
  - get and reset the invite link;
  - remove participants;
  - list, approve and reject join requests;
  - send to a group (text, media, templates); pin and unpin.

  It explicitly does **not** support admin promotion or demotion, or direct participant addition; its quick facts list "Non-supported actions: Admin hide group participant list, Edit message, Delete message". Group messaging documents no reply-with-context, mark-read or forward. A group holds at most 8 participants, and a removal takes at most 8. The Message History Events API (`GET /{message_history_id}/events`) returns delivery statuses only, never message content, so it is not a history method.

MTProto rows cover both a basic group (`messages.*`) and a supergroup or channel (`channels.*`); the adapter picks by peer type.

## Messages

| Tool | telegram_bot | telegram_user | whatsapp_cloud |
|---|---|---|---|
| `comms_message_send` | A done [message.send]: `sendMessage` | A done [message.send]: `messages.sendMessage` | A todo:G8 [group.message.send]: `POST /{phone}/messages` (`recipient_type: group`) |
| `comms_message_reply` | A done [message.send]: `sendMessage` + `reply_parameters` | A done [message.send]: `messages.sendMessage` + `reply_to` | B [message.reply] (groups): the Groups API documents no reply with context in groups |
| `comms_message_edit` | A done [message.edit]: `editMessageText` | A done [message.edit]: `messages.editMessage` | B [message.edit]: the Groups API lists edit as unsupported |
| `comms_message_delete` | A done [message.delete]: `deleteMessage` | A done [message.delete]: `messages.deleteMessages` / `channels.deleteMessages` | B [message.delete]: the Groups API lists delete as unsupported |
| `comms_message_forward` | A done [message.forward]: `forwardMessage` (G7) | A done [message.forward]: `messages.forwardMessages` (`random_id` from the operation key, as a send; G7) | B [message.forward]: the Groups API documents no forward |
| `comms_message_pin` / `comms_message_unpin` | A done [message.pin]: `pinChatMessage` / `unpinChatMessage` | A done [message.pin]: `messages.updatePinnedMessage` | A todo:G8 [message.pin]: `POST /{phone}/messages` (`recipient_type: group`, `type: pin`, `pin.type` pin/unpin; `expiration_days` 1–30 is required to pin; admin-only, at most 3 pinned) |
| `comms_message_mark_read` | — : addressed to a person's conversation; bots have no read state (`readBusinessMessage` is for business connections only) | B [message.mark_read]: policy, not an API gap. MTProto has `messages.readHistory`, but the frozen spec keeps every read-acknowledge request absent in every phase (`telegram-rpc-review.md`, "Absent in every phase"); only the owner can lift that (R-G6) | A done [message.mark_read]: `POST /{phone}/messages` `status: read` (1:1 chats; the Groups API documents no group mark-read) |

## Context (reads through `ContextEngine`)

| Tool | telegram_bot | telegram_user | whatsapp_cloud |
|---|---|---|---|
| `comms_context_recent` / `comms_context_page` / `comms_message_recent` | A done (local): the bot's retained updates (`telegram_local`; the Bot API has no history method) | A done [history.read]: `messages.getHistory` | A done (local): the comms webhook archive (`whatsapp_webhook_archive`; the Cloud API has no history method) |
| `comms_context_get` | A done (local): the bot's retained updates | A done [history.read]: `messages.getHistory` | A done (local): the archive |
| `comms_message_get` | A done (local): one retained update by id (the bot's `around` with no context; G6) | A done [history.read]: `messages.getMessages` / `channels.getMessages` | A done (local): one archived message by `wamid` (the archive's `around` with no context) |
| `comms_group_context` | A done (local): retained updates + `getChatAdministrators(return_bots=True)`; the member list, which the Bot API cannot produce, is left out (G6) | A done [history.read]: `messages.getHistory`, `channels.getParticipants` | A done (local): the archive's messages; members and admins, which the archive cannot serve, are left out (G6's rule). Participants arrive with G8's `comms_group_members_list` |
| `comms_context_around_message` / `comms_message_context` | A done (local): retained updates around one update, newest first (G6; the Bot API has no history method) | A done [history.read]: `messages.getHistory` (offset) | A done (local): the archive around one `wamid`, newest first (the Cloud API has no history method) |
| `comms_context_thread` | B [history.read]: the Bot API has no history or thread method, and retained updates carry no thread index | A done [history.read]: `messages.getReplies` | B [history.read]: the Cloud API has no history method; the archive has no thread index |
| `comms_context_person` | A done (local): the bot's retained private-chat updates (`telegram_local`), when the user account cannot read the chat | A done [history.read]: `messages.getHistory` on the user peer (`telegram_live`) | A done (local): the archive's direct messages (`whatsapp_webhook_archive`), plus `campaign_store` on every transport |
| `comms_context_person` (variant: include_group_activity) | A done (local): retained group updates from that sender | A done [history.search]: `messages.search(from_id)` per group, when the account can search it (G6) | A done (local): the archive's group messages from that sender |
| `comms_context_search` / `comms_message_search` | B [history.search]: the Bot API has no search | A done [history.search]: `messages.search` | B [history.search]: the Cloud API has no search |
| `comms_context_summarize_source` | A done: local (what each source can serve) | A done: local | A done: local |

## Groups: members and admins

| Tool | telegram_bot | telegram_user | whatsapp_cloud |
|---|---|---|---|
| `comms_group_members_list` | B [member.list]: the Bot API has no member list (only `getChatMember` per user, `getChatAdministrators`) | A done [member.list]: `channels.getParticipants` / `messages.getFullChat` | A todo:G8 [group.members]: `GET /{group_id}?fields=participants` |
| `comms_group_members_get` | A done [member.get]: `getChatMember` (G6) | A done [member.get]: `channels.getParticipant` / `messages.getFullChat` (G6) | A todo:G8 [group.members]: `GET /{group_id}?fields=participants` (filtered) |
| `comms_group_admins_list` | A done [admin.list]: `getChatAdministrators(return_bots=True)`; other bots are omitted by default since Bot API 10.0 (G6) | A done [admin.list]: `channels.getParticipants(filter=admins)` / `messages.getFullChat` (G6: read as admins, not derived from a member page) | B [admin.list]: the Groups API exposes no admin roles |
| `comms_group_member_add` | B [member.add]: bots cannot add users (invite links only) | A done [member.add]: `channels.inviteToChannel` / `messages.addChatUser` | B [member.add]: the Groups API has no direct participant addition (invite link only); by design (P §25) the tool answers `result: INVITE_REQUIRED` with no call |
| `comms_group_member_invite` | A done [invite.create]: `createChatInviteLink` | A done [invite.create]: `messages.exportChatInvite` | A todo:G8 [group.invite.get]: `GET /{group_id}/invite_link` (G1 found this cell claimed done: the service routes Telegram only, and the Graph client has no invite GET) |
| `comms_group_member_remove` | A done [member.remove]: `banChatMember` then `unbanChatMember` (saga) | A done [member.remove]: `channels.editBanned` / `messages.deleteChatUser` | A done [group.member.remove]: `DELETE /{group_id}/participants` |
| `comms_group_member_ban` / `comms_group_member_unban` | A done [member.ban]/[member.unban]: `banChatMember` / `unbanChatMember` | A done [member.ban]/[member.unban]: `channels.editBanned` | B [member.ban]: the Groups API has no ban (removal only) |
| `comms_group_member_restrict` / `comms_group_member_unrestrict` | A done [member.restrict]: `restrictChatMember` | A done [member.restrict]: `channels.editBanned` (rights) | B [member.restrict]: the Groups API has no per-member rights |
| `comms_group_member_tag_set` | A done [member.tag]: `setChatMemberTag` (`can_manage_tags`; A46) | A done [member.tag]: `messages.editChatParticipantRank` (`manage_ranks`; A46) | B [member.tag]: WhatsApp groups have no member tags |
| `comms_message_reaction_remove` | A done [reaction.remove]: `deleteMessageReaction` (`can_delete_messages`; A46) | A done [reaction.remove]: `messages.deleteParticipantReaction` (A46) | B [reaction.remove]: group messaging supports no reaction moderation |
| `comms_group_member_reactions_clear` | A done [reaction.clear]: `deleteAllMessageReactions` (A46) | A done [reaction.clear]: `messages.deleteParticipantReactions` (A46) | B [reaction.clear]: group messaging supports no reaction moderation |
| `comms_group_admin_promote` / `comms_group_admin_update_rights` / `comms_group_admin_demote` | A done [admin.promote]/[admin.demote]: `promoteChatMember` | A done [admin.promote]/[admin.demote]: `channels.editAdmin` / `messages.editChatAdmin` | B [admin.promote]: the Groups API explicitly has no admin promotion or demotion |
| `comms_group_admin_log` | B [admin.log.read]: the Bot API has no admin log | A done [admin.log.read]: `channels.getAdminLog` (event kinds and actors by ref, no content; G6) | B [admin.log.read]: the Groups API has no admin log |

## Groups: chat settings, invites, join requests, topics, lifecycle

| Tool | telegram_bot | telegram_user | whatsapp_cloud |
|---|---|---|---|
| `comms_group_permissions_get` | A done [member.get]: `getChat` → `permissions` (G6; membership suffices to read them) | A done [member.get]: `channels.getParticipant(self)` / `messages.getFullChat` → the chat's `default_banned_rights` (G6; channels.getChannels stays absent, as the frozen spec requires) | B [chat.set_permissions]: the Groups API has no member permission set |
| `comms_group_permissions_set` | A done [chat.set_permissions]: `setChatPermissions` | A done [chat.set_permissions]: `messages.editChatDefaultBannedRights` | B [chat.set_permissions]: as above |
| `comms_group_info_set_title` | A done [chat.set_title]: `setChatTitle` | A done [chat.set_title]: `channels.editTitle` / `messages.editChatTitle` | A done [group.settings.update]: `POST /{group_id}` (`subject`) |
| `comms_group_info_set_description` | A done [chat.set_description]: `setChatDescription` | A done [chat.set_description]: `messages.editChatAbout` | A done [group.settings.update]: `POST /{group_id}` (`description`) |
| `comms_group_info_set_photo` | A todo:G8 [chat.set_photo]: `setChatPhoto` (multipart) | A todo:G8 [chat.set_photo]: `upload.saveFilePart` → `channels.editPhoto` / `messages.editChatPhoto` | A todo:G8 [group.settings.update]: `POST /{group_id}` (profile photo) |
| `comms_group_invite_create` / `comms_group_invite_edit` | A done [invite.create]/[invite.edit]: `createChatInviteLink` / `editChatInviteLink` | A done [invite.create]/[invite.edit]: `messages.exportChatInvite` / `messages.editExportedChatInvite` | B [invite.create]/[invite.edit]: one invite link per group, which the Groups API can only reset |
| `comms_group_invite_revoke` | A done [invite.revoke]: `revokeChatInviteLink` | A done [invite.revoke]: `messages.editExportedChatInvite(revoked=True)` | A done [group.invite.reset]: `POST /{group_id}/invite_link` |
| `comms_group_invite_revoke` (variant: no invite given, reset the primary link) | A done [group.invite.reset]: `exportChatInviteLink` (a new primary link revokes the old; its `inv_` returned; G6) | A done [group.invite.reset]: `messages.exportChatInvite(legacy_revoke_permanent=True)` (G6) | A done [group.invite.reset]: `POST /{group_id}/invite_link` |
| `comms_group_invite_list` | B [invite.list]: the Bot API has no invite-link listing | A done [invite.list]: `messages.getExportedChatInvites` (the account's active links, by `inv_`; G6) | A todo:G8 [group.invite.get]: `GET /{group_id}/invite_link` (the one link) |
| `comms_group_join_requests_list` | A done (local): retained `chat_join_request` updates (`telegram_local`; the Bot API has no list method; G6) | A done [join_request.list]: `messages.getChatInviteImporters(requested=True)` (G6) | A todo:G8 [join_request.list]: `GET /{group_id}/join_requests` |
| `comms_group_join_requests_approve` / `comms_group_join_requests_reject` | A done [join_request.approve]/[join_request.reject]: `approveChatJoinRequest` / `declineChatJoinRequest` | A done: `messages.hideChatJoinRequest(approved=…)` | A todo:G8 [join_request.approve]/[join_request.reject]: `POST` / `DELETE /{group_id}/join_requests` |
| `comms_group_topic_list` / `comms_group_topic_get` | B [topic.list]: the Bot API has no forum-topic listing | A done [topic.list]: `messages.getForumTopics` / `messages.getForumTopicsByID` (by `top_`; G6) | B [topic.list]: WhatsApp groups have no topics |
| `comms_group_topic_create` / `comms_group_topic_edit` / `comms_group_topic_close` / `comms_group_topic_reopen` | A done [topic.create]/[topic.edit]/[topic.close]/[topic.reopen]: `createForumTopic` / `editForumTopic` / `closeForumTopic` / `reopenForumTopic` | A done [topic.create]/[topic.edit]/[topic.close]/[topic.reopen]: `messages.createForumTopic` / `messages.editForumTopic` | B [topic.create]: WhatsApp groups have no topics |
| `comms_group_create` | B [group.create]: bots cannot create chats | A done [group.create]: `channels.createChannel` (+ `forum`), filed at once with its `grp_` (G7) | A todo:G8 [group.create]: `POST /{phone}/groups` |
| `comms_group_delete` | B [group.delete]: bots cannot delete chats | A done [group.delete]: `channels.deleteChannel` / `messages.deleteChat` | A todo:G8 [group.delete]: `DELETE /{group_id}` |
| `comms_group_migrate` | B [group.migrate]: bots cannot migrate a group | A done [group.migrate]: `messages.migrateChat` | B [group.migrate]: WhatsApp groups have no supergroup form |

## Account, media, templates, webhooks, capability

| Tool | telegram_bot | telegram_user | whatsapp_cloud |
|---|---|---|---|
| `comms_account_profile` | A todo:G8 [account.inspect]: `getMe` | A todo:G8 [account.inspect]: `users.getFullUser(self)` | A todo:G8 [account.inspect]: `GET /{phone}/whatsapp_business_profile` |
| `comms_account_status` / `comms_account_capabilities` / `comms_telegram_*_status` / `comms_whatsapp_account_status` | A done: capability snapshot (`getMe`, rights) | A done: session readiness, `users.getUsers(self)` | A done [account.inspect]: `GET /{waba}` |
| `comms_whatsapp_phone_status` | — : a WhatsApp account tool | — : a WhatsApp account tool | A todo:G8 [phone_number.inspect]: `GET /{phone}?fields=` (`quality_rating`, `status`, `name_status`, `code_verification_status`) |
| `comms_media_upload` | B [media.upload]: the Bot API has no standalone upload (files upload only inside a send) | A todo:G8 [media.upload]: `upload.saveFilePart` → `messages.uploadMedia` | A todo:G8 [media.upload]: `POST /{phone}/media` (multipart; Meta allows up to 100 MB documents, but the `upl_` stage caps at 16 MiB) |
| `comms_media_download` | A todo:G8 [media.retrieve]: `getFile` + file download | A todo:G8 [media.retrieve]: `upload.getFile` | A todo:G8 [media.retrieve]: `GET /{media_id}` → bounded Meta-URL download |
| `comms_media_inspect` / `comms_media_delete` | — : WhatsApp media by `med_` id (Telegram files are message attachments, G8) | — : WhatsApp media by `med_` id (Telegram files are message attachments, G8) | A done [media.delete]: `GET` / `DELETE /{media_id}` |
| `comms_whatsapp_template_*` | — : a WhatsApp account tool | — : a WhatsApp account tool | A done [template.list]/[template.get]/[template.create]/[template.edit]/[template.delete]: `/{waba}/message_templates` |
| `comms_whatsapp_webhook_status` | — : a local report on the WhatsApp webhook inbox | — : a local report on the WhatsApp webhook inbox | A done: the local inbox counts |
| `comms_capability_get` / `comms_capability_for_group` / `comms_capability_for_actor` / `comms_capability_refresh` / `comms_group_capabilities` | A done: capability service | A done: capability service | A done: capability service |

## Added by A46, not yet in the catalog

These tools become rows when their task adds them to the catalog. The row test requires every cited tool to exist, and G9 requires this section to be empty.

- `comms_whatsapp_health_status`:
  - both Telegram actors: `—`, because it is a WhatsApp account tool;
  - WhatsApp: A todo:G8 [phone_number.health] `GET /{phone}?fields=health_status`.

## Local tools (no provider actor)

`comms_capability_list`, `comms_group_list`, `comms_group_get`, every `comms_campaign_*`, `comms_location_*` and `comms_audience_*` tool, `comms_admin_identity_inspect`, the `comms_directory_*` tools G2–G4 add, and `comms_location_member_*`. These read or write `comms.db` only. A campaign's delivery goes through the transports' delivery adapters, not these tools.

## Checked against the 2026 developer docs (2026-09-26)

Every cell was re-checked against the live docs. None flipped between A and B. What changed or was learned:

- **Confirmed B cells.** The Bot API still has no member list, admin log, invite-link or topic listing, history or search. Cloud API edit and delete in groups are listed as non-supported.
- **Confirmed methods.** All 30 cited bot methods and all 47 cited MTProto methods exist. `exportChatInviteLink` revokes the previous primary link, as the invite-revoke variant row assumes.
- **Details for the builders.**
  - G6: `getChatAdministrators` needs `return_bots=True` to list other bot admins.
  - G8: WhatsApp pin needs `expiration_days`; groups cap at 8 participants.
  - G9: the Graph API pin (v21.0) expires on 21 January 2027 and must move to a current version before release.
- **New admin surface beyond A45's catalog.** The owner added it to the catalog as A46 on 2026-09-26; see "Added by A46" above.
  - member tags: Bot API `setChatMemberTag` with the `can_manage_tags` right (9.5); MTProto `messages.editChatParticipantRank`;
  - reaction moderation: Bot API `deleteMessageReaction` / `deleteAllMessageReactions` (10.0); MTProto `messages.deleteParticipantReaction(s)`;
  - WhatsApp `health_status`: a messaging-health summary for the phone number, WABA and business.
