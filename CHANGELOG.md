# Changelog

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Telegram MCP planning.
- **Summary:** Read the V0.1.10 spec and prepared a release roadmap plus a detailed synthetic-foundation plan, as selected by the user.
- **Files changed:** `AGENT.md`, this file, and the two dated planning documents under `docs/superpowers/plans/`.
- **Verification:** Reviewed the full spec across architecture/contract/disclosure/release workstreams; checked JSON syntax and demonstrated the SQLite NULL and nested-schema reference defects. Planning documents received link, code-fence and coverage checks.
- **Follow-ups:** Review the plans and select an execution method. No implementation, dependencies, Git initialization, host provisioning or Telegram access performed.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Telegram MCP Phase-1 Task 1 foundation.
- **Summary:** Initialized local Git, established locked package (`mcp==2.2.0`, `Telethon==1.45.0`, `hatchling==1.32.4`) with audit-corrected floors and Appendix B `.gitignore`.
- **Files changed:** `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `src/telegram_mcp/__init__.py`, `tests/unit/test_package.py`, `docs/verification/dependencies.md`, `AGENT.md`, this file.
- **Verification:** `uv sync --locked` (67 packages); mcp 2.2.0 / telethon 1.45.0 confirmed; `pytest tests/unit/test_package.py -q` 1 passed (RED→GREEN); `git check-ignore` blocks session/env probes.
- **Follow-ups:** Continue Phase-1 Tasks 2–7 natively; no Telegram access, no service users, no remote.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Telegram MCP Phase-1 foundation complete (Tasks 1–7).
- **Summary:** Synthetic-only MCP foundation: locked deps, validated ten-tool contracts, closed dispatch, public-SDK transport, 158-test acceptance with modern + legacy wire parity.
- **Files changed:** `src/telegram_mcp`, `scripts/extract_contracts.py`, test suites, `README.md`, `docs/verification/`, `AGENT.md`, this file.
- **Verification:** 158 passed; lint/type/format clean; wheel fresh-install smoke OK; gates A/B/I/K/L partial only.
- **Follow-ups:** Phase-2 privileged runtime plan next; no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-2 track integration (2a Tasks 1-5, 2b Task 1) and handoff repair.
- **Summary:** Merged the `phase-2a-authority` and `phase-2b-agent` tracks into `main` and repaired what the tracks left broken: `binascii.Error` is now imported rather than reached through `base64`, `ConsentBroker._pinned_key_id` is narrowed to `str` at construction, `tests/unit/test_policy.py` kwargs are `dict[str, Any]`, and `tests/agent/conftest.py` builds the Swift agent with the plan's exact `swiftc` command so the shell tests no longer depend on an untracked `build/` artifact.
- **Files changed:** `src/telegram_mcp/consent/broker.py`, `src/telegram_mcp/consent/challenge.py`, `tests/unit/test_policy.py`, `tests/agent/conftest.py`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** `uv run pytest -q` 271 passed, 1 skipped from a clean `build/` (Swift binary rebuilt by the fixture); `ruff check` and `ruff format --check` clean on `src tests`; `mypy src tests` clean (was 8 errors across 3 files at merge).
- **Follow-ups:** Phase-2a Tasks 6-9 inline on `main` (refs/cursors/epochs, SQLite migrations with C2/C4, admin IPC/leases/rendezvous/tunnel identity/install/doctor, CLI wiring and evidence). Phase-2b Tasks 2-5 still open. No Telegram access, no service users, no remote, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Telegram MCP Phase-2a authority foundation, Tasks 6-9 (Tasks 1-5 arrived on the `phase-2a-authority` track).
- **Summary:** Completed the Phase-2a plan inline: ten-prefix ref validation, keyed cursor binding with the seven invalidation triggers mapped onto the four spec codes, epoch operations; all 19 spec tables with the C2 excerpt-width fix and the C4 retained-membership rules plus §12.3 integrity triggers, the guarded `open_db` path and the closed settings registry; `tgml1` leases per §9.7.1, one frame codec, the admin socket with the whole §33 surface routed and a presence gate, RV-1 rendezvous, tunnel pins with history, `doctor` with an honest `--production` gate, the two idempotent installers and the consent LaunchAgent definition; CLI verbs `start/stop/status/doctor/admin/keys/pair/rotate` with `demo` untouched, the three-layer vertical slice, and the Phase-2J join-gate harness.
- **Files changed:** `src/telegram_mcp/authority/{refs,cursors,epochs}.py`, `src/telegram_mcp/storage/`, `src/telegram_mcp/ipc/`, `src/telegram_mcp/doctor.py`, `src/telegram_mcp/cli.py`, `src/telegram_mcp/keys/store.py`, `scripts/install_service_users.sh`, `scripts/install_paths.sh`, `scripts/consent-agent.plist`, the new unit/contract/integration/security suites, `tests/conftest.py`, `pyproject.toml`, `README.md`, `docs/verification/phase-2a.md`, this file, `CHANGELOG.md`.
- **Verification:** Gate suite 440 passed, 17 skipped (all named); `extract --check` 23 files OK; `ruff check`/`format --check` clean over `src tests scripts`; `mypy src/telegram_mcp` clean (42 files); `uv build` produced wheel `449b6991b8da6133710d19822ba342573124f5d3ce85f3723fe211852f47a534`. Gates E/H/M/N/P and the privilege/key parts of R are recorded PARTIAL; `doctor --production` fails deliberately.
- **Follow-ups:** Phase-2b Tasks 2-5 (display gate and Touch ID, rendezvous client, pairing/LaunchAgent/signing, evidence), then the Phase-2J join gate, then the SMAppService API question. No Telegram access, no service users installed, no remote, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Telegram MCP Phase-2b Swift consent agent, Tasks 2-5.
- **Summary:** Completed the consent agent inline: the display gate (verify the daemon signature, recompute the display digest and compare it in constant time against the digest inside the signed challenge, and only then prompt), the Touch ID approval flow on a fresh LAContext with the key obtained through a KeyProvider seam, the RV-1 rendezvous client with prompt frames frozen here, and pairing with a Secure Enclave approval key, a software transport key and a keychain-pinned daemon challenge key. Six rendezvous scenarios run against the real Python broker rather than a stub. Pairing requires a stable certificate-backed identity and refuses ad-hoc builds; the plan's Developer-ID rule was relaxed deliberately after confirming against Apple's current documentation that Developer ID and notarization govern distribution and that a free Apple Development certificate creates Enclave keys with no entitlement or provisioning profile.
- **Files changed:** `agent/consent-agent.swift`, `agent/ConsentAgent-Info.plist`, `scripts/package_agent.sh`, `scripts/consent-agent.plist`, `src/telegram_mcp/ipc/rendezvous.py`, `tests/agent/` (conftest, stub_broker, shell tests), `tests/conftest.py`, `tests/__init__.py`, `docs/verification/phase-2b.md`, this file, `CHANGELOG.md`.
- **Verification:** `tests/agent` 26 passed, 2 skipped (the interactive pairing and Touch ID legs); full suite 466 passed, 19 skipped; ruff/format/mypy clean; 9 JCS vectors byte-equal; `plutil -lint` OK; ad-hoc bundle refuses pairing (`flags=0x10002(adhoc,runtime)`) and the certificate-signed bundle reports `pairable`.
- **Follow-ups:** Both interactive legs have now run on this host: a Secure Enclave approval key (`p256:sha256:fbd39bb3...`) and a software transport key are paired, and a real Touch ID approval produced a signature the broker's verifier accepts. Next: re-point Plan 2a's Phase-2J join-gate harness at this driver and drive the remaining seven scenarios. No daemon pin (no runtime exists yet), no loaded LaunchAgent, no Telegram access, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-1 + Phase-2 end-to-end smoke, and two startup-ordering fixes it found.
- **Summary:** Added `scripts/e2e_smoke.py`, which drives the shipped artifacts in one run — the demo server as a subprocess over a real TCP socket, the real 19-table schema on disk, real Unix sockets for the admin and rendezvous paths, the installed CLI, both installer dry-run plans, and the real Swift agent against the real consent broker — and prints one pass/fail ledger. Writing it exposed two ordering defects in `STARTUP_STEPS`: the single-runtime lock was acquired at step 8, after secrets were read and the database was opened, migrated and garbage-collected; and the tunnel client started before READY was advertised, contradicting both the design and the module's own comment. Both are fixed and pinned. `python -m telegram_mcp.cli` now works alongside the console script.
- **Files changed:** `scripts/e2e_smoke.py`, `src/telegram_mcp/runtime/lifecycle.py`, `src/telegram_mcp/cli.py`, `tests/unit/test_runtime.py`, `README.md`, `docs/verification/phase-2a.md`, this file, `CHANGELOG.md`.
- **Verification:** Smoke 41 passed, 0 failed, 0 skipped (~9 s, stable across three runs); full suite 467 passed, 20 skipped; ruff/format/mypy clean.
- **Follow-ups:** Re-point Plan 2a's Phase-2J join-gate harness at the Plan-2b driver and drive its remaining seven scenarios; decide how to scope the agent's transport key in the keychain. No Telegram access, no service users installed, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Close the two open items — keychain scoping for the agent's transport key, and the Phase-2J join gate.
- **Summary:** The agent's keychain records now carry a `SecAccess` naming the binary as the only trusted application, and reads disable interaction so a foreign code identity fails closed rather than raising an authorization dialog; writes replace rather than update so no record inherits a permissive ACL. Verified live: the signed bundle reads its own records and survives rebuilds, the ad-hoc bundle sees none, and `/usr/bin/security` gets a prompt instead of bytes. The daemon now also serves one agent session at a time. The join gate was rebuilt on the real driver and passes all thirteen scenarios against the real broker and the real packaged agent, plus one interactive Touch ID approval through the production `run` path that imports a daemon pin and removes it afterwards. Writing it exposed two further defects, both fixed: `doctor`'s OFF probe matched any process whose arguments merely mentioned a job label, so a `dscl` or `sudo -u` probe tripped it, and a stale test asserting the old keychain exposure survived its own replacement and was passing only by skipping.
- **Files changed:** `agent/consent-agent.swift`, `src/telegram_mcp/ipc/rendezvous.py`, `src/telegram_mcp/doctor.py`, `tests/conftest.py`, `tests/agent/conftest.py`, `tests/agent/stub_broker.py`, `tests/agent/test_consent_agent.py`, `tests/integration/test_join_gate.py`, `tests/unit/test_ipc.py`, `tests/unit/test_doctor.py`, `tests/security/test_install.py`, `scripts/e2e_smoke.py`, `docs/verification/phase-2a.md`, `docs/verification/phase-2b.md`, this file, `CHANGELOG.md`.
- **Verification:** 484 passed, 7 skipped by default; 487 passed, 4 skipped with `--run-platform-gated` (the four remaining skips are the rotation ceremony behind its flag, two install-dependent probes, and the vector generator); smoke 41/41; ruff, format and `mypy src/telegram_mcp` clean.
- **Follow-ups:** Phase 3 (disclosure, budgets, proofs, audit chain). Service accounts and paths are still not installed on this host, and no runtime has ever issued a challenge to the paired agent outside the join gate. No Telegram access, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Project memory and cross-project knowledge capture.
- **Summary:** Added `CLAUDE.md` as the repository's working agreement — non-negotiables, the verification commands, the module map, the frozen wire contracts and the current host state — so a fresh session starts from the same rules rather than rediscovering them. Recorded the session's durable knowledge in Zurvan: four accepted decisions (pairing on a stable code identity rather than Developer ID, SecAccess scoping for the keychain records, the corrected startup ordering, and driving the real broker instead of a stub), four findings (the free-certificate Secure Enclave path, the keychain ACL behaviour matrix, SQLite admitting a row whose CHECK evaluates to NULL, and macOS LibreSSL rejecting `-noenc`), and one open question about what `doctor --production` will still refuse once the installers have run. Zurvan's search index was rebuilt.
- **Files changed:** `CLAUDE.md`, this file, `CHANGELOG.md`; Zurvan wiki entries outside this repository.
- **Verification:** Full suite 484 passed, 7 skipped; `zurvan index search` rebuilt 185,480 chunks; decisions and question accepted by the Zurvan write tools.
- **Follow-ups:** No Git remote is configured, so nothing has been pushed. Phase 3 next.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Third gauntlet pass over the Phase-3 design, and the fixes it forced.
- **Summary:** Ran the `simurgh-arise` doctrine over `docs/superpowers/specs/2026-09-22-telegram-mcp-phase-3-design.md`, checking every normative citation against the frozen specification and every architectural claim against the shipped code rather than against the document's own reasoning. Thirteen claims verified clean — the spec hash, all ten error codes and their retryability, the 15-second deadline, all seven §33 commands, the anchor fallback wording, the §12.2 degraded flow clause by clause, the five table DDLs, the two-dimension ledger, the three key-registry rows and the retention values — and the controlling statement survived a direct attempt to falsify it, because Phase 1 had already transcribed `disclosure_proof_key_id`, `disclosure_proof_public_key`, `meta.disclosure` and the whole `meta.coverage` object into the frozen contracts. Eighteen defects did not survive. Six were blocking: the design promised to keep `DisclosureGate` as the seam, but it returns a boolean and cannot release a payload, contradicting the document's own controlling statement (it also has no production caller, so the fix is free); Appendix L is normative and the design had substituted its own eight invariants for the required fourteen and named neither `formal/README.md` nor `SECURITY-MANIFEST.json`; the §23D coverage proof had no design text and no plan owner although its object is already contract-frozen and its digest signed into every search receipt; per-project byte attribution was missing, so an implementer would have charged envelope overhead to every project bucket; the reservation tuple had silently dropped `security_epoch` and `consent_challenge_digest`; and the pre-consent hard-budget refusal §23C.3 mandates was absent, so the design would have prompted a human for a call it was about to refuse. Twelve more followed, including the audit-chain genesis value and epoch-bump rule being undefined, the absence of a single measurement authority against a Gate P MUST, the settings work being understated as three rows when it is eleven, and no content-leak sweep against Gate O's first privacy MUST. Two defects were in shipped code, not the document. The checkpoint-cadence registry rows carried maxima of 100,000 events and seven days — wide enough for an operator to configure a violation of §26.5's "at least every 500 events or 60 minutes" — under a comment asserting the specification states no number, which §26.5 and the reference configuration both contradict; fixed test-first, maxima now 500 and 3600. And `tools/status.py` advertises a key derived from 32 zero bytes while Appendix K.2 tells verifiers to resolve `proof_key_id` against exactly that key: harmless while nothing signs anything, a forgery oracle the moment Phase 3 lands a signer, so it now carries a tripwire test that fails when the real key arrives and a warning at the point of the hazard. One finding was refined rather than adopted: the arithmetic showing two 45-second consent windows exceed the 75-second recommended client timeout is real, but §23C.3 says the request MUST be re-prompted, so the bound stays and the timing is documented as safe-but-wasteful instead. The design was rewritten as revision 2 with all eighteen folded in, plus the claim boundary that no participant in those conversations ever consented, and the honest bound that rolling windows limit burst rate and not lifetime exposure.
- **Files changed:** `docs/superpowers/specs/2026-09-22-telegram-mcp-phase-3-design.md` (446 → 928 lines), `src/telegram_mcp/storage/settings.py`, `src/telegram_mcp/tools/status.py`, `src/telegram_mcp/consent/gate.py`, `tests/unit/test_storage.py`, `tests/security/test_demo_isolation.py`, this file, `CHANGELOG.md`.
- **Verification:** 486 passed, 7 skipped (two new tests, both written before their fix or as a deliberate tripwire); smoke 41 passed, 0 failed; `extract_contracts --check` 23 files OK; ruff, format and `mypy src/telegram_mcp` clean over 42 source files; the fourteen Appendix-L assertions diffed programmatically against the frozen text with no omission and no addition; spec self-review clean (0 placeholders, 18 of 18 defect rows, 11 of 11 settings rows, every cross-reference resolving).
- **Follow-ups:** Write the three implementation plans (3a measurement/egress/provenance/coverage/receipts/keys, 3b accounting/reservations, 3c chain/anchor/coordinator/formal model) against revision 2. Honest scorecard before the pass was 5.2 of 10 across fidelity, consistency, implementability, falsifiability and honesty; it should be re-scored after the plans exist, not now. No Telegram access, no service users installed, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** External implementation-readiness review of the Phase-3 design; revision 3.
- **Summary:** A fourth review read revision 2 against the frozen contract hunting implementation ambiguity rather than architectural error, and raised ten points. Its document lives in a sandbox this machine cannot reach (`sandbox:/mnt/data/...`, absent from every local path), so nothing was read or merged; each point was verified against the frozen specification and revision 2 directly and applied here. Eight were real and adopted: budget decisions must compare the projected figure — committed rows plus live reservations plus this call's worst case — because the reservation is that worst case and a ceiling compared against current totals would bound where a call starts rather than where it ends; the append barrier needed an actual process-wide `audit_append_guard` acquired before Step 11 and held across Step 12, since a barrier entered by committing leaves a window where a second caller commits and the chain goes two ahead; the fallback anchor had no format or durability procedure, now a frozen JSON shape with a domain-separated `anchor_mac` that cannot be confused with an event MAC, a write/fsync/rename/fsync sequence and fail-closed symlink, owner and mode checks; the formal model asserted over anchor and payload state it never declared, so five variables were added including `audit_integrity_state` over the five integrity states, because an assertion that cannot be expressed produces a checker that passes for the wrong reason; "ordered set" was replaced by an ordered vector in emitted-record order with four frozen fields, since a set has no order and two implementers would canonicalise differently; `meta.coverage` sits outside `data` and therefore outside `bytes_disclosed`, verified against the frozen search contract whose `data` members are `project`, `results` and `search_scope`, so revision 2's "envelope and coverage overhead are charged globally" was wrong in both directions; a successful anchor repair is now itself a chained and anchored `admin.repair_anchor` event whose six-step ordering clears the latch only after the repair event is anchored; and the extraction benchmark is reframed as benchmark-observed under a named synthetic configuration and an explicit lower bound, because calling a fake-adapter number "how much private content a compliant assistant can see" was the adjective inflation this project refuses elsewhere. One point was refined: revision 2 already carried all four FAIL CLOSED rows, so the claim that fatal states were newly made explicit was stale — what was genuinely missing is that `repair-anchor` must actively refuse in those states rather than merely being unable to help, since moving a pointer over lost history is laundering evidence, and that is now stated with its reason. One claim was withdrawn rather than implemented: revision 2 promised `disclosure show` would report `payload_unreconstructable` after a ref-regenerating restore, which Phase 3 cannot deliver without durable restore-lineage metadata it does not persist, so the distinction is handed to Phase 5 and the false comfort removed. Two further defects surfaced while applying the rest and were fixed here: `event_id` enters the event MAC, so its format is frozen as `evt_` plus a 26-character Crockford base32 ULID per Appendix C, or the chain is not reproducible; and `audit_events.tool_name` is `NOT NULL` while §6.5 requires administrative events to append through the same barrier, so a closed dotted vocabulary was fixed that no MCP tool name can collide with.
- **Files changed:** `docs/superpowers/specs/2026-09-22-telegram-mcp-phase-3-design.md` (928 → 1127 lines), this file, `CHANGELOG.md`.
- **Verification:** 486 passed, 7 skipped; smoke 41 passed, 0 failed; ruff and `mypy src/telegram_mcp` clean over 42 source files. Document self-review clean: 0 placeholders, all three superseded revision-2 phrasings gone except where the withdrawal quotes them, and every new anchor present. No source file changed this round.
- **Follow-ups:** The design is ready to freeze; the next review belongs at the 3a/3b/3c plan level, where the subject changes from architectural ambiguity to exact APIs, SQL transactions, failure injection and test ordering. No Telegram access, no service users installed, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** The three Phase-3 implementation plans, and the gauntlet over them.
- **Summary:** Wrote `3a` (measurement authority, egress, provenance, §23D coverage, Appendix-K receipts, offline verifier, verification-key registry, key provisioning, synthetic-key retirement), `3b` (subject digests, rolling windows, the two dimensions, tiers, reservations, ledger commit, concurrency and bypass suites) and `3c` (settings rows, MAC-linked chain, external anchor, checkpoints, coordinator, crash model, content-leak sweep, recovery ceremony, formal model, extraction benchmark) — 5,157 lines across three files. Then gauntleted them by **executing** their own code rather than reading it: the plans' modules and tests were extracted verbatim into a throwaway spike and run. That found eleven defects the design review could not have caught, because each lives in the seam between two tasks. Two were blocking. `append_event` opened and committed its own `BEGIN IMMEDIATE`, which SQLite proves incompatible with the coordinator wrapping it — the error is `cannot start a transaction within a transaction` — so running the plan as written would either raise at step 11 or push an implementer into deleting the coordinator's transaction, silently turning §23A.3's one atomic commit into three and destroying the crash model the whole design rests on; appends now require a caller-owned transaction and refuse without one. And plan 3a proposed reporting `null` for the two disclosure-key fields of `telegram_status`, which the frozen contract types as a non-null string and a 43-character base64url pattern, so the null design would have broken the contract and widening it would have contradicted the controlling statement; the key is now required, with the demo minting an ephemeral per-process Ed25519 key whose private half signs nothing. Three test defects were proven by running them: a measurement assertion comparing per-project bytes against the global figure was arithmetically false because the global figure carries container overhead (381 vs 409 on the plan's own fixture); a provenance assertion compared insertion-ordered dict keys against an alphabetical list; and an `event_id` assertion was vacuous, passing for any string containing a digit. Six more were structural: the coordinator's twelve steps were left as a "steps 1-10 omitted for brevity" comment in the single most important module of Phase 3, now written in full with the append guard wrapping steps 11 and 12; four suites depended on five fixtures that appeared nowhere; `disclose_sync` was called in tests against an `async def disclose` interface, resolved as async tests since `asyncio_mode = "auto"`; `disclosure/verify.py` was referenced by two tasks and created by none; `AdminRouter.knows()` was invented where the real closed list is the module-level `ADMIN_COMMANDS` tuple, whose 51 entries do contain all seven commands Phase 3 needs; and `SettingSpec`'s new `pattern` field was described rather than shown. Writing the plans also caught a defect in the design committed an hour earlier: §5.2's record-element list named `peers[]`, `projects[]` and `unread[]` for tools whose frozen contracts actually emit `matches[]`, `matches[]` and `chats[]`, and `telegram_cross_project_search` carries a `projects` array that is scope metadata rather than records — so a measurement keyed on it would have counted the wrong thing on exactly the tool where cross-project accounting matters most.
- **Files changed:** `docs/superpowers/plans/2026-09-22-telegram-mcp-phase-3a-disclosure-machinery.md`, `...-3b-exposure-accounting.md`, `...-3c-audit-and-coordinator.md` (new), `docs/superpowers/specs/2026-09-22-telegram-mcp-phase-3-design.md`, this file, `CHANGELOG.md`.
- **Verification:** The spike ran the plans' own code: measurement 5 of 6 passing before the fix, egress 8 of 8, provenance 13 of 14, coverage 10 of 10, receipts 9 of 9, budget 7 of 7; the nested-transaction failure reproduced directly against the project's own connection factory; all seven §33 commands confirmed present in `ADMIN_COMMANDS`; the status contract's non-nullability read off the frozen schema. Spike removed afterwards — the tree carries plans only. Suite 486 passed, 7 skipped; ruff, format and mypy clean. Final placeholder scan across all three plans: zero.
- **Follow-ups:** Execute 3a, then 3b, then 3c. The dependency direction is one-way, so 3a can start immediately. No Telegram access, no service users installed, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Execute Phase-3 Plan 3a inline — the deterministic disclosure machinery.
- **Summary:** All nine tasks done test-first: the three Phase-3 key rows are provisioned and carry distinct recomputed ids; `disclosure/measure.py` is the single measurement authority Gate P demands, with per-tool record elements read off the frozen contracts and a per-project/global byte split that reconciles exactly; `egress.py` transforms and intersects profiles without ever sanitising a message body; `provenance.py` commits to an ordered emitted-record vector whose digest is order-sensitive and text-blind; `coverage.py` carries the §23D object, its closed six `partial_reasons` and the invariant chain JSON Schema cannot express, validated against the frozen `meta.json`; `receipts.py` builds the twenty-one Appendix-K fields, signs over JCS bytes and rejects tampering; `keys.py` holds the public verification-key registry with retirement that never deletes; and the zero-seed disclosure key is retired. Execution found four defects the plan had not: `keys provision` created four rows while `keys list` reported seven, so the two CLI verbs disagreed and `list` failed on a freshly provisioned store; two existing tests were pinning the gap rather than the requirement (`test_provision_phases_3_creates_nothing` asserted the defect literally) and were replaced; the smoke provisioned Phase-2 rows only and failed three checks once `FILE_BACKED_KEYS` grew; and ruff's `PLE2502` trojan-source rule correctly rejected the bidi control the egress test needs, which now builds it with `chr(0x202E)` so the character reaches the transformer without sitting in the source. The tripwire planted two commits earlier fired exactly on cue when `make_status` gained its required key argument, and was replaced by tests that describe the requirement instead of the hazard. One process failure worth recording: an early commit went in against a red suite because `&&` chained off `tail` rather than pytest; caught on the next command and fixed in the following commit, but the guard belongs in the habit, not the pipeline.
- **Files changed:** `src/telegram_mcp/disclosure/{__init__,measure,egress,provenance,coverage,receipts,keys}.py` (new), `src/telegram_mcp/tools/status.py`, `src/telegram_mcp/dispatch.py`, `src/telegram_mcp/keys/store.py`, `src/telegram_mcp/cli.py`, `tests/unit/test_disclosure_{measure,egress,provenance,coverage,receipts,keys}.py` (new), `tests/security/test_offline_verifier.py` (new), `tests/security/test_demo_isolation.py`, `tests/unit/test_keys.py`, `tests/unit/test_doctor.py`, `tests/integration/test_cli.py`, `tests/conftest.py`, `scripts/e2e_smoke.py`, `docs/verification/phase-3.md` (new), `CLAUDE.md`, this file, `CHANGELOG.md`.
- **Verification:** 536 passed, 7 skipped (up from 486); smoke 41 passed, 0 failed; `extract_contracts --check` 23 files OK; ruff, format and `mypy src/telegram_mcp` clean over 49 source files. The offline verifier is proven by forbidding `sqlite3.connect` and `socket.socket` inside the test, so "needs no database" is enforced rather than asserted. Coverage objects validate against the frozen `meta.json`. Gates O, P and Q are recorded PARTIAL in `docs/verification/phase-3.md`, each naming exactly what is missing.
- **Follow-ups:** Plan 3b (exposure accounting), then Plan 3c (chain, anchor, coordinator). Nothing from 3a is wired into a tool: the nine sensitive tools still return `POLICY_UNCONFIGURED` and no disclosure has ever been committed. No Telegram access, no service users installed, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Execute Phase-3 Plan 3b inline — exposure accounting.
- **Summary:** All seven tasks done test-first. `disclosure/budget.py` now carries keyed subject digests so no opaque ref lands in `exposure_ledger` while `exposure status` can still recompute one deterministically; rolling windows; the two budget dimensions, where three projects touch four physical buckets and a record with several origins is charged whole in each contributing bucket; thresholds read from the closed settings registry with "at or above" escalating rather than passing; the reservation lifecycle bound to the six components §23C.3 freezes, including the `security_epoch` and `consent_challenge_digest` revision 1 had dropped; and `commit` converting a reservation into ledger rows inside a caller-owned transaction, refusing when actual exceeds reserved. Execution corrected two defects the plan had carried. The concurrency suite used threads, but `sqlite3` connections are thread-bound and this daemon is single-process asyncio, so the thread version died inside `get_setting` with "SQLite objects created in a thread can only be used in that same thread" before it reached any budget logic; it now races coroutines, which is the real concurrency model, and `BudgetLedger` documents that a future thread pool needs a ledger and a connection per thread rather than a shared one. And the project-cycling fixture reserved 700 records per project against a 500-record per-project ceiling, so it tripped on the first call instead of demonstrating what it claimed: three calls of 400 now pass under their own ceilings while the fourth reaches 1600 against the 1500 client-global ceiling, which is the bypass the test exists to catch. The shared `seed_authority_rows` and `insert_committed_receipt` helpers moved to `tests/authority_fixtures.py`, because `conftest` is not importable from a subdirectory, and they are proven against the §12.3 tuple-consistency trigger that rejects a receipt whose client belongs to another principal or whose principal/account pair has no `policy_state` row.
- **Files changed:** `src/telegram_mcp/disclosure/budget.py`, `tests/unit/test_disclosure_budget.py` (new), `tests/integration/test_budget_concurrency.py` (new), `tests/security/test_budget_bypass.py` (new), `tests/authority_fixtures.py` (new), `tests/conftest.py`, `docs/verification/phase-3.md`, `docs/superpowers/plans/2026-09-22-telegram-mcp-phase-3b-exposure-accounting.md`, this file, `CHANGELOG.md`.
- **Verification:** 561 passed, 7 skipped (up from 536); smoke 41 passed, 0 failed; ruff, format and `mypy src/telegram_mcp` clean over 50 source files. Gate P now records soft and hard tiers behaving exactly as §23C.1 specifies against the projected figure, concurrent reservations unable to both take the last capacity, retries and project cycling both caught, and `actual ≤ reserved` failing closed — with what remains stated plainly: no tool consults the ledger, so nothing is enforced end to end, and measurement identity across prompt, reservation, ledger and receipt cannot be asserted until a coordinator exists.
- **Follow-ups:** Plan 3c (audit chain, external anchor, degraded state and recovery, the coordinator, the operator commands, the formal model, the crash and content-leak gauntlets). No Telegram access, no service users installed, no production claim.

### 2026-09-22 (Australia/Sydney)
**Raouf:**
- **Scope:** Execute Phase-3 Plan 3c inline — audit chain, external anchor, coordinator, formal model.
- **Summary:** All ten tasks done test-first. The eleven Phase-3 settings rows landed, and with them the content guarantee moved from a key-name heuristic to the type: an `int` row cannot hold prose whatever it is called, and every `str` row must now be closed by `choices` or a `pattern`, which closed the last free-form key (`audit.external_anchor_ref`, now a bare filename with no separators and no traversal). `audit/chain.py` carries MAC-linked events with an epoch-bound genesis and refuses to append outside a caller-owned transaction — the guard that makes §23A.3's single commit possible, and the one that caught the same defect again later in the repair path. `audit/anchor.py` has the frozen JSON shape, a domain-separated `anchor_mac` that cannot be replayed from an event MAC, write/fsync/rename/fsync durability and a rejection matrix verified live (0644 refused, wrong key refused, no temp file surviving). `coordinator.py` runs the twelve steps with the append guard held across 11 and 12 and returns a payload with its receipt or a refusal, never a third shape. The crash suite proves the model: ten crash points before step 11 leave nothing durable, a crash between 11 and 12 leaves the disclosure accounted and the payload withheld with the latch set, and the next call is refused while appending nothing. Writing that found a real defect — the step-12 crash seam sat outside the anchor handler, so an injected failure escaped instead of latching degraded. The content-leak sweep scans every table plus the logs and carries a control test proving it can fail. `verify.py` rebuilds a persisted receipt byte-identically and verifies it, including after a client credential rotation, which is the hole revision 2 of the design had promised to paper over and revision 3 withdrew. The bounded formal model explores all 624 reachable states against Appendix L's fourteen assertions plus this architecture's four, with a second test asserting no assertion is unreachable; it earned its keep three times, showing that revalidation alone does not stop a locked disclosure, that the window between step 8 and step 12 is closed by the reservation's `security_epoch` binding rather than by revalidation — exactly the component an earlier draft had dropped — and that the append guard must exclude environment interleaving or a lock lands between the commit and the anchor. No third-party checker was available, so the model is a self-contained exhaustive breadth-first search, recorded as such in `SECURITY-MANIFEST.json`.
- **Files changed:** `src/telegram_mcp/disclosure/{coordinator,verify}.py` and `disclosure/audit/{__init__,chain,anchor}.py` (new), `src/telegram_mcp/storage/settings.py`, `formal/{model.py,README.md}` and `SECURITY-MANIFEST.json` (new), `tests/unit/test_audit_{chain,anchor}.py`, `tests/integration/test_{disclosure_coordinator,audit_recovery}.py`, `tests/security/test_{no_uncommitted_escape,no_content_in_stores}.py`, `tests/formal/test_state_machine.py`, `tests/adversarial/test_maximal_extraction.py`, `tests/coordinator_fixtures.py` (all new), `tests/unit/test_storage.py`, `docs/verification/phase-3.md`, `CLAUDE.md`, `README.md`, this file, `CHANGELOG.md`.
- **Verification:** 626 passed, 7 skipped (up from 561); smoke 41 passed, 0 failed; formal model 624 reachable states with all 18 assertions holding and none unreachable; ruff, format and `mypy src/telegram_mcp` clean over 55 source files. The adversarial extraction benchmark ran once and its first result is sealed in the evidence: 1152 releases, 48 refusals, 23,040 records across 24 simulated hours, 1152 receipts — every release accounted. The bound that actually bit was the per-project ceiling of 500 rather than the client-global 1500, because a single-project client never reaches the global limit, and the client was refused in every window and simply continued in the next, which is the honest demonstration that budgets limit burst rate and not lifetime exposure.
- **Follow-ups:** Phase 4 — the real Telegram adapter and the nine tool slices behind the disclosure seam. Gates O, P and Q remain PARTIAL: no tool slice calls the coordinator, so the nine sensitive tools still return `POLICY_UNCONFIGURED`, and every result above was produced against a fake adapter. No Telegram access, no service users installed, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4 design (allowlisted Telegram adapter and vertical tool slices). Design only; no code.
- **Summary:** Four sections presented and reviewed one at a time, each amended before the next; the result is written to `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md`. Decomposition: 4a real coordinator seams and the authenticated runtime ingress with `list_projects`/`resolve_project` as the first real sensitive success, no network; 4b Telethon adapter, daemon-side login and discovery, Test DC, `list_chats`/`resolve_peer`/`get_messages`/`get_unread` with a counterpart-observed `read_outbox_max_id` witness; 4c `get_context` (forum topics), both searches with a bounded 64-peer continuation window and truthful coverage, and a dedicated-account qualification run. Reading the code during design found four things the spec now carries: the runtime has no authenticated MCP ingress (only the synthetic demo server), the coordinator's authority and consent collaborators exist only as test fakes, no admin handler writes projects, grants or peers, and the coordinator reserves with a request-derived nonce where §9.8/§23C.3 bind the challenge's nonce. Reading the pinned Telethon 1.45.0 source fixed the exact login RPC set and showed entity resolution can silently send `contacts.ResolveUsernameRequest`, so the design requires cache-only `InputPeer` construction plus a runtime outbound-RPC recorder alongside the source AST guard. Phase-2 cursor limits (`_PER_PEER_MAX=64`, 8,192-byte state) set the continuation window size.
- **Files changed:** `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md` (new), this file, `AGENT.md`/`CHANGELOG.md`.
- **Verification:** Baseline re-run for the design: 626 passed, 7 skipped. Every Telethon request class named in the allowlist confirmed present in the installed 1.45.0 package; frozen error codes checked against §27.1.
- **Follow-ups:** External line-by-line gauntlet of the written spec, then the 4a plan via writing-plans. Open to verify at plan time: Telegram's strictness on `limit > -add_offset`, and the current Test DC address and number/code conventions. No Telegram access, no service users installed, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Gauntlet of the Phase-4 design, revision 1 → revision 2. Design only; no code.
- **Summary:** Every claim in revision 1 was checked against the shipped code, the pinned Telethon 1.45.0 source and Telegram's own method and constructor pages; sixteen defects were found and fixed in place, each listed with its evidence in §0A. The largest: the daemon has no prompt-delivery path at all — `PROMPT`/`APPROVAL`/`DENIAL` frames live only in `tests/agent/stub_broker.py` and only `doctor.py` self-tests ever call `broker.consume` — so 4a gains `consent/prompter.py`. Also: `ConsentBroker.issue` is async while the coordinator calls it without `await`; `ConsumedChallenge` carries neither the nonce nor the exposure digest the design relied on; consent timeout is `CONSENT_DENIED` per §27.1 (revision 1 said `CONSENT_UNAVAILABLE`, the shipped broker says `DEADLINE_EXCEEDED` — both wrong); the admin router gates only `lock`/`unlock`, so §33's "mutations remain presence-gated" must be implemented, with a test tying the gated set to the mutating set; the cursor validator rejects booleans and any non-integer key except `offset_peer_ref`, so exhaustion is now encoded by absence from `per_peer`; Hypothesis is not a dependency; Telegram's `forum_topic` flag is absent in the General topic and a direct topic post has no `reply_to_top_id`, so the topic rule became a five-row table with a General-topic path; Telethon's `_on_login` sends `GetDifference` unconditionally, so the runtime recorder's allowlist is scoped by operation; bad bearers and rate limits are HTTP 401/429 before parsing because §27.1 has no rate-limit code; and continuation past `max_cross_project_peers` was withdrawn because CT-139 forbids a complete result under peer-cap exhaustion. The dev Keychain placement is recorded as a deviation from §9.1, not as compliance.
- **Files changed:** `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** Checked by execution: Telethon constructor arguments and all named request classes present in 1.45.0; `_on_login` source read; `messages.search` bounds strict and `inexact` present; `messages.getReplies` parameters; Telegram's pagination page states no strict `limit > -add_offset` rule, so that stays an empirical Test DC check. Suite unchanged at 626 passed, 7 skipped (no code touched).
- **Follow-ups:** Owner review of revision 2, then the 4a plan via writing-plans. No Telegram access, no service users installed, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4a implementation plan. Plan only; no product code.
- **Summary:** Wrote `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4a-seams-and-ingress.md` from design revision 2: twelve test-first tasks taking `telegram_list_projects` and `telegram_resolve_project` to a real, receipted, anchored success through an authenticated loopback ingress, a real consent prompt and the Phase-3 coordinator. Reading the code for the plan found more the design had not named, now owned by tasks: nothing loads SQLite rows into an `AuthorityView`; the coordinator emits `next_cursor: null` unconditionally and leaves adapter side keys (`_coverage`) inside `data`, where they would be measured and fail the output schema; its `meta.source` is hard-coded to `telegram`; `disclose` takes no principal and retrieval receives raw rather than frozen arguments; the policy engine's `discover` operation is what the catalogue tools need; `provision_lease_seed` mints on a miss, so the ingress gets a read-only `read_lease_seed`; and `policy.evaluate` treats an empty allowlist as allow-all (recorded as a 4b blocker, unreachable in 4a). One empirical question was settled by probe instead of assumption: a `ContextVar` set in the ASGI wrapper is visible in the SDK's `on_call_tool` per request under stateless Streamable HTTP. Scope boundaries are stated up front: identity rows are seeded (the account row comes from 4b login), admin presence proofs stay injected until 4b, and there is no daemon entry point until 4b.
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4a-seams-and-ingress.md` (new), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** Every signature the plan consumes was read from the shipped source; the ContextVar route was executed against the installed `mcp==2.2.0`. Suite unchanged at 626 passed, 7 skipped.
- **Follow-ups:** Owner review of the plan and choice of execution method. No Telegram access, no service users installed, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Gauntlet of the Phase-4a plan, revision 1 → revision 2. Plan only; no product code on `main`.
- **Summary:** Revision 1 was executed verbatim, task by task, in a throwaway worktree: 699 passed with minimal fixes, and no task's tests failed for a logic reason. The run and a static pass found fifteen defects, all fixed in place and listed in the plan's "What revision 2 changed". The one that mattered most came from executing, not reading. Three concurrent calls from one client produced four prompts, every one approved, and still one refusal: budget buckets are per client and §9.8/§23C.3 require the approved exposure digest to match exactly, so a sibling call from the same client moves the snapshot by construction. The fix serialises sensitive disclosures per client, lowering the §28 per-client ceiling to 1 as §28 permits. Also: `meta.partial` would have contradicted the signed receipt; the commit gate failed on formatting in every task; the `CoordinatorConsent` harness raced its own session; a relative source path let seven architecture guards pass vacuously; a `git checkout -- src` instruction would have wiped uncommitted tasks; and design §2.8's cancellation and oversize cases had no tests.
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4a-seams-and-ingress.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** Revision-2 code applied in the worktree: 704 passed, 7 skipped; ruff clean after formatting; mypy clean over 71 files; formal model 624/624. The new same-client concurrency test was seen to fail with the per-client lock removed (one call refused) and to pass with it restored. `main` suite unchanged at 626 passed, 7 skipped.
- **Follow-ups:** Owner review of revision 2 and choice of execution method. The throwaway worktree `.claude/worktrees/agent-a00bb75a052c3c0e1` holds uncommitted revision-2 code and can be removed. No Telegram access, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Execute the Phase-4a plan (revision 2) inline on branch `phase-4a` — real seams, authenticated ingress, first real sensitive success.
- **Summary:** All twelve tasks done test-first, each watched red before green, each committed on a green gate. `telegram_list_projects` and `telegram_resolve_project` now succeed through the whole chain: bearer checked before the body is parsed (401, byte-identical across causes; 429 with `Retry-After` for rate limits), identity-only `PrincipalContext`, live SQLite authority read fresh at steps 2 and 8, a consent prompt delivered by the new daemon-side prompter and answered by the packaged agent over RV-1, the coordinator's receipt, ledger rows, one audit event and anchor. The broker now carries the signed nonce and exposure digest, a consent timeout is `CONSENT_DENIED` per §27.1, the coordinator awaits issue, reserves with the approved nonce after the digest re-check, splits adapter side keys out of `data`, and labels catalogue results as gateway metadata. Every mutating admin command is presence-gated. Sensitive disclosures run one at a time per client, because exact-digest consent over per-client buckets otherwise re-prompts and refuses concurrent same-client calls. Tests written after their code (the ingress) were proven by mutation; the concurrency and revoke-during-prompt tests were shown to fail with their fix removed; three planted guard violations each failed their guard.
- **Files changed:** `src/telegram_mcp/{http_guards,sensitive_dispatch}.py`, `runtime/{identity,ingress,composition}.py`, `consent/{prompter,display}.py`, `disclosure/{exposure,seams}.py`, `storage/authority_view.py`, `telegram/{__init__,service,metadata}.py`, `ipc/handlers/{__init__,projects,leases}.py` (all new); `consent/broker.py`, `disclosure/coordinator.py`, `ipc/admin.py`, `keys/store.py`, `server.py`; eleven new test files plus `tests/coordinator_fixtures.py`, `tests/agent/stub_broker.py`, `tests/unit/{test_consent,test_gate,test_ipc}.py`; `scripts/e2e_smoke.py`; `docs/verification/phase-4.md` (new); `CLAUDE.md`, this file, `CHANGELOG.md`/`AGENT.md`.
- **Verification:** `uv sync --locked`, contract check, `pytest` 704 passed / 8 skipped, smoke 45 passed / 0 failed, formal model 624 states / 18 assertions, ruff check and format clean, mypy clean over 71 files, `uv build` sdist + wheel — every command exit 0, run fresh.
- **Follow-ups:** 4b: fix `policy.evaluate` treating an empty allowlist as allow-all (before any peer-scoped success), the live admin presence path, the daemon entry point, the account row from login. Owner-run: `pytest tests/integration/test_phase4a_touch_id.py --run-platform-gated`. No Telegram access, no service users installed, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4a final whole-branch review and its fix pass, on branch `phase-4a`.
- **Summary:** A separate reviewer (started before the owner's no-subagent rule, finished at the owner's choice) found no Critical issue and no path that releases data or a receipt without verified consent; all six Review Focus scenarios held under execution. Two Important findings were fixed in this session, each with a test seen failing first. First, a client that disconnected mid-prompt left its consent challenge live, so a late approval committed a receipt, ledger row and audit event for an abandoned call, against spec §9.8's "MUST be invalidated"; the HTTP preflight now runs the app as a task and cancels it on `http.disconnect`, which reuses the existing cancellation path. Second, an agent that died between prompts went unnoticed and held the rendezvous slot; the prompter now owns one reader loop per session that detects EOF at once, routes answers by handle, and never cancels a read mid-frame (which also removes a minor desync). Remaining minors are deferred and the reviewer's "declined to judge" items ruled on in the ledger; display-name bidi safety is recorded as a hard 4b prerequisite.
- **Files changed:** `src/telegram_mcp/http_guards.py`, `src/telegram_mcp/consent/prompter.py`, `tests/integration/test_phase4a_end_to_end.py`, `tests/unit/test_prompter.py`, `docs/verification/phase-4.md`, `CLAUDE.md`, this file, `CHANGELOG.md`/`AGENT.md`.
- **Verification:** pytest 706 passed / 8 skipped; smoke 45/45; join gate against the packaged agent 16 passed / 1 skipped; reviewer's probes now show pending 0 and counts (0,0,0) after a disconnect, and immediate detach after idle agent death; ruff, format and mypy clean.
- **Follow-ups:** merge decision for `phase-4a` (owner); owner-run Touch ID test; 4b prerequisites listed in `docs/verification/phase-4.md` §7.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4b implementation plan and design revision 3. Plan and design only; no product code.
- **Summary:** Wrote `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4b-adapter-and-tools.md`: eighteen test-first tasks.
  - **Tasks 1–6:** owner mode (an empty allowlist denies), prompt-safe names, live Touch ID admin approvals on the unchanged consent wire with sentinel refs, identity bootstrap and `client rotate`, deadlines/work budgets/fair admission, and the Keychain `api_hash` reader.
  - **Tasks 7–11:** the ref store, the single Telethon module, dialog discovery, three-step login, and scope/allowlist handlers.
  - **Tasks 12–16:** worst-case bounds with a page cap, the project-scoped authority snapshot, a coordinator re-check of authority before retrieval with typed retrieval refusals, history views, and the four tools.
  - **Tasks 17–18:** an alias-resolving RPC guard with composition and the daemon, and the Test DC harness with a runtime recorder and read-state witness.

  Design §3.8 records the owner's two decisions: reuse the wire with sentinel refs, and one 4b plan. It adds three refinements the planning forced:
  - `list_chats`, `get_unread` and `resolve_peer` read only the project's members via `GetPeerDialogs`.
  - Pages fit a 48 KiB data cap, because the 64 KiB response refusal happens after commit.
  - Telegram tools refuse before consent when no session exists.

  Before handover, the plan's code was dry-run in a scratch copy of `main`, which found eight defects, now fixed in the text:
  - Telethon 1.45 constructor changes (2);
  - a keyed digest at import;
  - an open implicit transaction;
  - an order-dependent demo-isolation test;
  - the daemon importing a concrete backend;
  - an unimported name;
  - a missing runtime handler.

  It also found that the existing RPC guard reads only import statements, so it would never have seen an RPC built as `functions.messages.X`; Task 17 fixes it.
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4b-adapter-and-tools.md` (new), `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md` (revision 3), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** Scratch dry run: the new tests for Tasks 4–17 passed; the full suite showed 770 passed, and its failures were only those expected from unapplied Tasks 1–2 and the unrebuilt Swift agent. Telethon 1.45.0 signatures were read from the installed package. `main` suite unchanged.
- **Follow-ups:** An owner-requested simurgh gauntlet of this plan next, then execution inline (no subagents). The owner must create the Keychain item, and supply the `api_id` and Test DC IP for the opt-in Test DC run. No Telegram access, no production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Simurgh gauntlet of the Phase-4b plan, revision 1 → revision 2. Plan only; no product code on `main`.
- **Summary:** Applied the whole plan to a scratch copy of `main`, including the Swift renderer, the recorder and the smoke rows, and attacked it by execution. Eight defects were fixed in the plan text:
  - The plan's code failed its own commit gate: 7 ruff and 6 mypy errors.
  - Literal bidi and invisible characters were embedded in the plan's code (a Trojan-Source hazard).
  - A deleted message in a full history page silently ended pagination.
  - An unreachable Telegram at start crashed the daemon and took the admin socket with it.
  - An unauthorised session still reached a Touch ID prompt.
  - `auth logout-local` left the auth key in the client's memory. Proven against real Telethon: the next connect would sign back in.
  - The smoke pinned the admin-router order that the plan changes.
  - The Swift instruction invited deleting the `isInvisible` line.

  Five residuals are recorded as owner rulings in the plan's gauntlet record.
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4b-adapter-and-tools.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification (scratch copy, fully applied):**
  - `pytest tests`: 825 passed, 8 skipped.
  - join gate: 16 passed, 1 skipped.
  - smoke: 49/49.
  - ruff check and format: clean.
  - mypy: clean over 85 files.
  - Each defect was shown failing by a probe before its fix.
  - `main` suite unchanged (706 passed, 8 skipped).
- **Follow-ups:** Owner review of revision 2 and the five residual rulings. Then inline execution. The Test DC run stays owner-only (needs the Keychain item, `api_id` and the Test DC IP).

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4b plan revision 4, fixing an external gauntlet's eight findings. Plan and design only; no product code on `main`.
- **Summary:** Each finding was verified before any change: all eight held against the pinned Telethon source, the plan and the spec. The verification found more. `send_code_request` sends the prohibited `auth.ResendCodeRequest` when a code hash is cached, and Telethon's `_call` sleeps and sends hidden RPCs.
  - **Wire (G-1, G-2):** the adapter now owns the wire. `_GatewayClient._call` sends one request per call, with no retry or sleep, under a per-operation allowlist and work budget. Login is raw reviewed requests, and the executor is private.
  - **Admin approvals (G-3):** they now bind keyed secret digests, and tokens are bound to their exact request.
  - **Pagination (G-4):** keyset with constant state; the 1,024-chat silent stop is gone.
  - **Retryability (G-5):** `results.RETRYABILITY` is §27.1 verbatim and the only registry.
  - **Witness (G-6):** widened to DM and group markers, channel views and unread counts.
  - **Daemon (G-7):** a production-shape admin-socket mode.
  - **Estimator (G-8):** a seeded adversarial invariant proves the reservation dominates Phase 3's exact measurement; a control run shows it bites.
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4b-adapter-and-tools.md`, `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification (whole plan applied to a scratch copy of `main`):**
  - pytest: 847 passed, 10 skipped
  - smoke: 49/49
  - join gate: 16 passed, 1 skipped
  - ruff, format and mypy: clean
  - session-file ignores: checked in the real repository
  - `main` suite unchanged.
- **Follow-ups:** Execute revision 4 inline, per the owner. The Test DC run and the installed-host boundary check remain owner-run.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Execute the Phase-4b plan (revision 4) inline on branch `phase-4b`, Tasks 1–18.
- **Summary:** All eighteen tasks were done test first, each watched red before green and each committed on a green full gate.
  - **Authority:** an empty owner allowlist now denies. Prompt-unsafe names are refused at creation and stripped by the agent's renderer.
  - **Admin approvals:** gated admin commands are approved with Touch ID on the consent wire, with secrets bound by keyed digest and tokens bound to their exact request.
  - **Identity:** principal, account and clients are bootstrapped for real.
  - **Telegram boundary:** deadlines, work budgets and fair admission; the Keychain `api_hash`; the ref store. A Telethon adapter owns the wire: one send per request, per-operation allowlist and budget, raw reviewed login, no Telethon helpers.
  - **Operator commands:** dialog discovery; three-step login; scope and allowlist.
  - **Exposure:** worst-case bounds with a 48 KiB page cap.
  - **Authority and coordinator:** the project-scoped authority snapshot; an authority re-check before retrieval with typed refusals and the §27.1 retryability registry.
  - **Reads:** history views, and the four reads with keyset pagination.
  - **Runtime:** the alias-resolving RPC guard, composition, `telegram-mcp daemon` with a production-shape admin-socket mode, the Test DC harness, the runtime recorder, the widened read-state witness, smoke rows and evidence.

  Control runs: a planted `ReadHistoryRequest` made both RPC guards fail, and a weakened estimator made all four exposure-invariant cases fail.
- **Files changed:**
  - **src — authority, consent, IPC:** `authority/policy.py`, `storage/{authority_view,identity,refstore}.py`, `ipc/admin.py`, `ipc/handlers/{projects,clients,auth,scope}.py`, `consent/admin_approval.py`.
  - **src — Telegram and disclosure:** `telegram/{deadline,errors,telethon_adapter,discovery,reads}.py`, `keys/keychain.py`, `disclosure/{bounds,seams,coordinator}.py`, `results.py`, `sensitive_dispatch.py`.
  - **src — runtime:** `runtime/{composition,daemon}.py`, `cli.py`.
  - **Agent:** `agent/consent-agent.swift`.
  - **Tests:** the new tests under `tests/`, plus `tests/telegram/`.
  - **Other:** `scripts/e2e_smoke.py`, `pyproject.toml`, `docs/verification/{phase-4,telegram-rpc-review}.md`, `CLAUDE.md`, this file, `CHANGELOG.md`/`AGENT.md`.
- **Verification:**
  - pytest: 860 passed, 10 skipped (the Test DC and host-gated tests skip honestly).
  - smoke: 49/49.
  - join gate: 16 passed, 1 skipped.
  - formal model: 624/624.
  - ruff and format: clean.
  - mypy: clean over 85 files.
  - `uv build`: OK.
- **Follow-ups:**
  - The final whole-branch review (self-review; no subagents, per the owner).
  - Owner-run: the Test DC run, the Touch ID test, and the installed-host boundary check.
  - Re-package the signed agent bundle with the renderer fix.
  - The merge decision (owner).
  - No production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4b final whole-branch review and its fix pass, on branch `phase-4b`.
- **Summary:** This was a self-review, because the owner's rule is no subagents: the code-reviewer checklist over the whole branch diff, plus executed probes. The shipped daemon CLI fails closed when unpaired, before it creates state or reads the Keychain.

  One Important finding was fixed test first. `_call_reviewed` carried an `isinstance(self._client, _GatewayClient)` branch that existed only for injected test clients, which breaks the "no test-only flags in production paths" rule. Charging is now uniform: the session always charges its own request and marks it pre-charged, and the client charges anything else.

  Five minors are deferred to the owner and listed in the ledger.
- **Files changed:** `src/telegram_mcp/telegram/telethon_adapter.py`, `tests/unit/test_gateway_client.py`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the new source guard went red, then green. Full gate: pytest 862 passed, 10 skipped; smoke 49/49; formal 624/624; ruff, format and mypy clean; build OK.
- **Follow-ups:**
  - The owner decides the merge and push; a self-review is weaker than a fresh reviewer.
  - Owner-run: the Test DC run, the Touch ID test, and the installed-host boundary check.
  - Re-package the signed agent bundle.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4c implementation plan and design revision 5 (§4.7), on branch `phase-4c`.
- **Summary:** The plan (`docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4c-context-and-search.md`) covers `get_context`, `search_messages`, `cross_project_search`, the continuation engine, §23D coverage and the Test DC qualification harness, in 8 tasks. It is a transcription of code that already ran. The code was written and tested in a scratch copy of `main` at `cd1434e` (1290 passed, 10 skipped; smoke 53/53). It was then replayed task by task onto a fresh export, with each task's tests, ruff, format, mypy, the full suite and the smoke run at every stage; all 8 stages were green. The plan text itself was then replayed mechanically onto a third export: 34 blocks applied with zero fuzz, and the 33 files are byte-identical to the tested tree. Design §4.7 records the 11 refinements that execution forced (nearest-neighbour context windows, byte-accounted search pages, response attribution checks and others).
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4c-context-and-search.md` (new), `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the staged proof table is in the plan. Full gate on this commit (docs only): pytest 862 passed, 10 skipped; smoke 49/49; formal 624/624; ruff, format and mypy clean; contracts check and build OK.
- **Follow-ups:**
  - The line-by-line gauntlet of the plan (owner request).
  - Inline execution.
  - Owner-run: the Test DC run, including the 4c forum and search cases; the dedicated-account qualification; the Touch ID test; the installed-host check; re-packaging the signed agent.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase-4c plan, revision 6: a line-by-line gauntlet, then an external review, on branch `phase-4c`.
- **Summary:** The gauntlet read the plan against the frozen spec, the pinned Telethon source and the tested tree, and ran probes against it. The owner then pasted an external review of the first transcription, and each claim was checked before anything changed. Every confirmed defect was fixed test first in the scratch tree: each new test failed before its fix, and four guard tests also had control runs. The confirmed defects:
  - **Paging ended too early.** A short page was taken as the end. Telethon 1.45.0 `client/messages.py:213-225` documents that it is not. This affected both search and 4b history.
  - **Offsets and coverage were unreliable.** A foreign entry could steer the next offset. Uncertainty was forgotten between pages. `peers_scanned` counted peers merely started. The coverage counters were guessed rather than measured.
  - **Two work bounds were enforced nowhere, including 4b.** One is the 10-search-page bound; the other is the 32,000-codepoint cap on combined text.
  - **Owner-excluded peers were counted as eligible.**
  - **Continuations were slow.** A continuation made one dialog request per resumed peer.
  - **The Test DC run would have failed at its first read,** because of a stale chat-kind equality.
  - **Smaller defects:** a lowercase `z` in RFC 3339 times and a fractional `until`; the epoch `since` edge; forum classification; an empty cursor entry; query-canary coverage of logs and files.

  The plan was re-proved: every task was replayed onto a fresh `main` export with its own tests, lint, types, the full suite and the smoke, and all 48 checks were green. The plan text was then replayed mechanically: 38 blocks applied with zero fuzz, and the 36 files are byte-identical to the tested tree. Design §4.7 records every rule change.
- **Files changed:** `docs/superpowers/plans/2026-09-23-telegram-mcp-phase-4c-context-and-search.md`, `docs/superpowers/specs/2026-09-23-telegram-mcp-phase-4-design.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** staged proof: 1333 passed, 10 skipped (plus the 4 git-only tests in the repo); smoke 53/53 at Task 8. Full gate on this commit (docs only): pytest 862 passed, 10 skipped; smoke 49/49; formal 624/624; ruff, format and mypy clean; contracts check and build OK.
- **Follow-ups:**
  - Inline execution.
  - Deferred minors: the exposure-invariant `_rehome` truncates a shared list in place; the universe digest binds the candidate universe.
  - Owner-run: the Test DC run (now including real paging), the dedicated-account qualification, the Touch ID test, the installed-host check, and re-packaging the signed agent.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 4c executed inline from the revision-6 plan, on branch `phase-4c` (8 tasks).
- **Summary:** `telegram_get_context`, `telegram_search_messages` and `telegram_cross_project_search` are served through ingress, consent and the coordinator on the fake transport; all nine sensitive tools are now served. Each task's red and green outputs, and its full-gate counts, matched the plan exactly, with no rulings needed. Control runs: the estimator weakening (3 invariant cases failed), and a planted query log line and query `INSERT` (the canary test failed in the log and in `meta.db-wal`). Evidence is in `docs/verification/phase-4.md` §4c; the two new RPC reviews are in `telegram-rpc-review.md`.
- **Files changed:**
  - **src:** `authority/{cursors,policy}.py`, `telegram/{telethon_adapter,search,reads}.py`, `disclosure/{bounds,search_authority,seams,coordinator}.py`, `storage/refstore.py`, `validation.py`, `consent/display.py`, `runtime/composition.py`.
  - **Tests:** new and updated tests under `tests/`, including `tests/telegram/`.
  - **Other:** `scripts/e2e_smoke.py`, `docs/verification/{phase-4,telegram-rpc-review}.md`, `CLAUDE.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** pytest 1337 passed, 10 skipped; smoke 53/53; formal 624/624; ruff, format and mypy clean (87 files); contracts check and build OK.
- **Follow-ups:**
  - The final whole-branch review (self-review; no subagents, per the owner).
  - Owner-run: the Test DC run (forum, edges, real paging and exhaustion), the dedicated-account qualification, the Touch ID test, and the installed-host check.
  - Re-package the signed agent.
  - A forum read-marker witness.
  - The merge decision (owner).
  - No production claim.

### 2026-09-23 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 4c landed on `main`.
- **Summary:** Branch `phase-4c` was pushed, merged into `main` with `--no-ff` as `0a11bb9` (11 commits since `cd1434e`), and `main` was pushed. The merged tree is identical to the gated branch head `1741ff9`. There are 9 sensitive tools and all are served on the fake transport. Real Telegram behaviour is owner-pending. `CLAUDE.md` and `docs/verification/phase-4.md` now say 4b and 4c are on `main`. The decisions and claims are recorded in Zurvan under the tag `telegram-mcp`.
- **Files changed:** `CLAUDE.md`, `docs/verification/phase-4.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the full gate on the merged tree (below): pytest 1337 passed, 10 skipped; smoke 53/53; formal 624/624; ruff, format and mypy clean (87 files); contracts check and build OK.
- **Follow-ups:**
  - Owner-run: the Test DC run (forum, edges, real paging and exhaustion), the dedicated-account qualification, the Touch ID test, and the installed-host check.
  - Re-package the signed agent.
  - A forum read-marker witness.
  - Deferred minors: the conservative ten-page check; the exposure test's in-place `_rehome`; the candidate-universe digest.
  - Next: Phase 5 per the roadmap.
  - No production claim until Gates A–R pass for the exact artifact.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 5 design written.
- **Summary:** Revision 1 of the Phase 5 design (5a inspect surface and policy engine, 5b lifecycle/rotation/retention/recovery, 5c backup/import/runbooks). It carries 9 decisions and 25 review findings. The findings include a shipped error-mapping defect (`UserDeactivated*` reported as `SESSION_REVOKED`) queued for 5b.
- **Files changed:** `docs/superpowers/specs/2026-09-24-telegram-mcp-phase-5-design.md`, `AGENT.md`, this file.
- **Verification:** The design's code citations were checked at `9eec78e`. No code changed.
- **Follow-ups:**
  - The owner's gauntlet of the design, then the 5a plan.
  - No production claim.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 5 design, revision 2 (gauntlet).
- **Summary:** 16 defects were found against the shipped code and fixed in the design. The two blockers are an FK-breaking purge order and an audit chain that cannot hold multiple epochs or a truncated prefix (the latter proven by a committed probe).
- **Files changed:** `docs/superpowers/specs/2026-09-24-telegram-mcp-phase-5-design.md`, `docs/verification/probes/phase5_chain_epochs_probe.py`, `AGENT.md`, this file.
- **Verification:** The probe rejects both cases, as recorded in §0B G2. Ruff is clean. No product code changed.
- **Follow-ups:**
  - The owner's review, then the 5a plan.
  - No production claim.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 5a plan (11 tasks), gauntleted.
- **Summary:** The operator surface and single policy engine plan. The gauntlet fixed 15 plan defects, including lock-contention handling and the degraded-recovery path.
- **Files changed:** `docs/superpowers/plans/2026-09-24-telegram-mcp-phase-5a-operator-surface.md`, `AGENT.md`, this file.
- **Verification:** The guards were run, the probes were executed, and every code block parses. No product code changed.
- **Follow-ups:**
  - The owner's review, then execution.
  - No production claim.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 5a plan revision 3.
- **Summary:** The owner's review folded in: 10 findings adopted, 2 rejected with evidence. Adds Task 4A (retrieval decides chat class through the evaluator).
- **Files changed:** the plan, `AGENT.md`, this file.
- **Verification:** Every code block parses; the guard predictions were checked.
- **Follow-ups:** inline execution.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Phase 5a implemented on `phase-5a`.
- **Summary:** The operator surface and one policy engine (plan rev 3, 12 tasks). Five shipped defects fixed; four gaps recorded for 5b.
- **Files changed:** see the matching `AGENT.md` entry.
- **Verification:** pytest 1493 passed, 10 skipped; smoke 60/60; formal 624/18; ruff, format, mypy and build clean.
- **Follow-ups:**
  - Branch review, then the merge decision.
  - The 5b plan.
  - No production claim.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms consolidation design (5b-0).
- **Summary:** Telegram and WhatsApp merge into `comms` through staged phases; only 5b-3 changes semantics, and only 5d adds live sends.
- **Files changed:** `docs/superpowers/specs/2026-09-24-comms-consolidation-design.md`, `AGENT.md`, this file.
- **Verification:** Both baselines were measured, and the identifiers were grep-confirmed.
- **Follow-ups:** the 5b-1 plan.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms 5b-1 (mechanical relocation).
- **Summary:** `telegram_mcp` becomes `comms.transports.telegram`, proven AST-equivalent. `comms.core` is empty and guarded; the legacy CLI is kept.
- **Files changed:** see the matching `AGENT.md` entry.
- **Verification:** 1514 passed, 11 skipped; smoke 60/60; formal 624/18; ruff, format, mypy and build clean.
- **Follow-ups:**
  - The merge decision.
  - The 5b-2 plan.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms 5b-2 — WhatsVault import.
- **Summary:** WhatsVault imported intact with full history under `transports/whatsapp/`; one Python 3.12 environment; both suites green.
- **Files changed:** see AGENT.md entry of the same date.
- **Verification:** Telegram 1519/10 skipped + smoke 60 + formal 624/18; WhatsVault 539 passed.
- **Follow-ups:** merge decision; §3.4 seams or 5b-3.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms 5b-3 — owner-direct authority (comms spec v0.2).
- **Summary:** No Touch ID and no consent ceremony anywhere: the consent subsystem is deleted; receipts are explicitly versioned (v2 `owner_direct` with the soft-threshold flag; v1 kept byte-identical and verifiable); admin authority is peer credentials; consent keys retired, not erased; six replacement formal invariants; retired identifiers tombstoned; the AI boundary stated exactly.
- **Files changed:** see AGENT.md entry of the same date.
- **Verification:** Telegram 1427/4 skipped + smoke 52 + formal 544/22; WhatsVault 539 passed; unexpectedly missing tests = 0.
- **Follow-ups:** merge decision; runbook key/bundle removal; 5b-4.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms 5b-4: the campaign core (fake transports only).
- **Summary:** A new encrypted `comms.db` and `comms.core` campaign core:
  - the directory, with shared delivery identities;
  - campaigns frozen into immutable generations of deduplicated, idempotent jobs;
  - one reducer and a derived summary;
  - an engine whose only exception boundary is `deliver`;
  - cancel, retry, resolution and provider updates, including updates that arrive before the result;
  - scheduling with a time gate;
  - recovery that never resends blindly.

  It is proved by a bounded model with mutation tests and by a differential walk against the library.
- **Files changed:** see the `AGENT.md` entry of the same date.
- **Verification:** Telegram 2215 passed, 4 skipped; smoke 52; formal 544/22 plus the campaign model at 96,528 states and 11 properties; WhatsVault 539 passed.
- **Follow-ups:** the owner's ruling on the snapshot-digest contradiction; the merge decision; 5c/5d/5e.

### 2026-09-24 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms v0.3 Part A — the constitutional cutover (branch `comms-v0.3`), plan rev 2 executed inline and test-first (tasks A1–A23; A18 merged into A11).
- **Summary:** One profile-parameterised audit chain engine and one anchor engine now live in `comms.core`; the legacy Telegram chain is a thin binding that reproduces its byte vectors. `comms.db` v2 adds the comms audit chain, the integrity latch, lineage and an exact-next-state cutover table. `AuditWriter` commits and then anchors exactly that head under one lock. The resumable cutover drains, verifies, seals (DB-enforced), anchors, writes lineage and the `system.audit_cutover` genesis, and retires `tgml1` (DB-enforced, epoch bumped once); 12 crash boundaries converge. `verify_all` walks legacy (from a signed root) → seal → lineage → genesis → comms chain → anchor and fails closed. The Telegram MCP surface, disclosure-on-read, project/grant/scope/policy authority, exposure budget and `tgml1` issuance leave production (the daemon serves admin only; 29 admin commands answer `RETIRED_IN_V0_3`; `demo`/`serve` exit 8); `legacy_composition` keeps them as a historical harness for retained tests. `legacy_verify` verifies v1/v2 receipts, the legacy chain and key coverage without the retired engine. WhatsVault's `apps/mcp` is removed (R-A16). A seed `TOOL_CATALOG` with closed `comms_*` dispatch and a v0.3 AI-boundary suite (owner_full_admin) are in. Rulings R-000–R-008, R-A16, R-A20 are registered.
- **Files changed:** `src/comms/core/{audit/*,keys/{ids,slots}.py,storage/migrations.py,strict_json.py,validators.py,refs.py,domains.py}`, `src/comms/mcp/*`, `src/comms/services/registry.py`; Telegram `cli.py`, `contract.py`, `authority/__init__.py`, `disclosure/{audit/*,keys.py}`, `ipc/{admin,leases}.py`, `ipc/handlers/{exposure,inspect,audit,leases}.py`, `legacy_verify/`, `runtime/{composition,legacy_composition,daemon,cutover_barrier,identity}.py`, `storage/{migrations,settings,owner_state,authority_view}.py`; `transports/whatsapp/**` (R-A16 only); tests under `tests/{core/audit,mcp,security,unit,integration}`; `scripts/e2e_smoke.py`, `scripts/capture_chain_vectors.py`; `docs/comms-v0.3-supersession.json`, `docs/verification/comms-v0.3*`; `AGENT.md`, `CHANGELOG.md`.
- **Verification:** full gate at the Part A head — contracts OK; Telegram 2385 passed, 4 skipped; smoke 57/57; formal 544 states/22 assertions and the campaign model at 96,528 states; ruff/format/mypy clean; build OK; WhatsVault 450 passed. Part A exit gate (`test_v03_part_a_exit.py`) re-runs every §A.9 owning test; test accounting unexpectedly missing = 0; smoke map complete. Evidence: `docs/verification/comms-v0.3.md`.
- **Follow-ups:** the owner confirms or applies the R-A20 `.claude/settings.json` change; local tag `comms-v0.3-part-a` (not pushed); Parts B–D next; merge and push need the owner's approval. No production claim.

### 2026-09-25 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms v0.3 Part B — durability, audit, keys, retention, recovery, backup (branch `comms-v0.3`), plan rev 2 tasks B1–B33, inline and test-first.
- **Summary:** Chain epochs and root-aware verification (the five probe attacks as regressions); the truncation root; the full key inventory with staged rotation, epoch-opening chain-key rotation, checkpoint/cursor consequences, backup-signer trust states and retired-HMAC dependency rules; the keyed campaign commitment; a daemon-owned 0600 secret store (no Keychain); the `comms.db` rekey with recovery at every boundary; staged credential rotation with re-check and rollback; Telegram session revoke, error mapping and login recovery; retention in foreign-key order (legacy truncation enables receipt purge; comms truncation; body and identity redaction; retired key material; a maintenance event), failing closed on a bad root; `audit repair` through an ancestor-proving verifier; age-v1 X25519 backups with signatures, binding, transfer frames, export, staged import and an epoch-opening commit; `comms doctor`; eight runbooks; two mutation-tested formal models and a 200-walk differential test.
- **Files changed:** `src/comms/core/{audit,keys,maintenance,backup}/*`, `src/comms/core/{credentials,doctor,installation,strict_json}.py`, `src/comms/core/storage/{migrations,rekey,db}.py`, `src/comms/core/{domains,refs,timeutil,validators}.py`, `src/comms/core/campaigns/{directory,events}.py`, `src/comms/core/delivery/{freeze,commitment}.py`, Telegram `telegram/{telethon_adapter,admin_rpc}.py`, `ipc/handlers/auth.py`, `storage/{identity,owner_state,settings,migrations}.py`, `runtime/legacy_retention.py`; `formal/{audit_model,keys_model}.py`, `formal/README.md`; `docs/runbooks/*`, `tests/fixtures/age/*`; tests throughout; `docs/verification/{comms-v0.3,comms-v0.3-rulings,telegram-rpc-review}.md`; `AGENT.md`, `CHANGELOG.md`.
- **Verification:** full gate at the Part B head (see the evidence for exact counts); Part B exit gate re-runs every owning test with no skip allowed; crash tables converge at every boundary; formal: 544 states / 22 assertions, the campaign model at 96,528 states, the audit model at 215,040 states, the keys model at 512 states; WhatsVault 450 passed. Evidence: `docs/verification/comms-v0.3.md`.
- **Follow-ups:** the R-A20 `.claude/settings.json` change awaits the owner; local tag `comms-v0.3-part-b` (not pushed); Part C (provider adapters) next; merge and push need the owner's approval. No production claim.

### 2026-09-25 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms v0.3 Part C — provider adapters (branch `comms-v0.3`), plan rev 2 tasks C1–C34, inline and test-first.
- **Summary:** Four adapters behind the core provider protocols, each passing every contract it advertises with zero skips: the Telegram Bot API (pinned client, named-case classification, delivery, capability from real rights, admin tables for membership, rights and P §74 profiles, chat info, pins, invites, join requests and topics, an atomic-offset update poller, a local-only context source); the Telegram user actor over the one Telethon session (capability-keyed RPC sets with retries and auto-reconnect off, `random_id` sends persisted on the attempt before the call and reconciled once, delivery, capability across group kinds, admin, a bounded live context source, the update consumer); the WhatsApp Cloud API (a per-code error table, delivery with the mirrored window and frozen template binding, template and media operations with a Meta-only bounded downloader, account status and discovery-gated groups); and the Meta webhooks (a raw-bytes HMAC ingress, a durable inbox and a resumable fan-out). Core gains `OperationSemantics`, normalized rate limits, campaign-content rendering, template bindings, the window mirror and an inbound-body retention phase. The Meta contract oracle lives in WhatsVault's `fake_meta.py` (R-C27). Live acceptance is opt-in and evidence-only, with two runbooks. The registry is built from secret-store credentials.
- **Files changed:** `src/comms/core/providers/*`, `src/comms/core/{campaigns/{render,templates},delivery/{transport,engine,freeze,operations,window}}.py`, `src/comms/core/{domains,storage/migrations,audit/specs,maintenance/retention}.py`; `src/comms/transports/{net.py,telegram/{bot,user}/*,telegram/{peers,message_text,args,admin_profiles,chat_specs,capabilities,page_bounds}.py,telegram/telegram/{telethon_adapter,rights,send_attempt,updates_view}.py,telegram/runtime/composition.py,whatsapp/**}`; `src/comms/runtime/adapters.py`; `transports/whatsapp/src/whatsvault/providers/fake_meta.py` (R-C27 only); `tests/{conformance,transports,fixtures/providers}/**`, `tests/core/*`, `tests/security/{test_egress,test_adapter_canaries,test_v03_part_c_exit}.py`, `tests/integration/test_adapter_registry.py`; `docs/runbooks/live-acceptance-{telegram,whatsapp}.md`; `docs/verification/{comms-v0.3,comms-v0.3-rulings,telegram-rpc-review}.md`; `AGENT.md`, `CHANGELOG.md`.
- **Verification:** full gate at the Part C head (exact counts in the evidence); the Part C exit gate re-runs every owning test with no skip allowed and runs the whole conformance registry; privacy canaries over all four adapters; WhatsVault 450 passed. Evidence: `docs/verification/comms-v0.3.md`.
- **Follow-ups:** the live update-stream switch, the daemon's `build_comms_adapters` call, the WhatsVault archive binding, per-recipient template language and `chat.set_photo` move to Part D; live acceptance needs the owner's disposable accounts; the R-A20 `.claude/settings.json` change awaits the owner; local tag `comms-v0.3-part-c` (not pushed); merge and push need the owner's approval. No production claim.

### 2026-09-25 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms v0.3 Part D — services, MCP, CLI, ingress, OAuth, smoke and client runbooks (branch `comms-v0.3`), plan rev 2 tasks D1–D38, inline and test-first.
- **Summary:** Built the typed service layer (`src/comms/services/`): the actor resolver, capability, the context engine, handles and cursors, groups, messages, campaigns, directory, templates, media, account and identity. It runs on one mutation executor with durable operation records, request-id idempotency, sagas and crash recovery. The 109-tool catalog is pinned by digest (`4380d085…`). `comms mcp` serves it in two ways: a privilege-free stdio proxy with `cml1` leases, and Streamable HTTP `/mcp`, with `cml1` locally and OAuth 2.1 remotely (EdDSA tokens, PKCE S256, owner code). The CLI is generated from the catalog and runs over the admin socket. There are three exact-path listeners. The operations model and the differential walk passed, as did the typed egress sweep. The smoke now drives the real comms composition, stdio, HTTP, OAuth and the CLI, and runs `verify --all` after every surface wrote. D38 added the `template` CLI group, the P §80 intent data, the P §81 deterministic ambiguity test, three client runbooks and the Part D exit gate. The ruling is R-D38.
- **Files changed:** `src/comms/{services,mcp,runtime,cli_commands}/*`, `src/comms/cli.py`, `src/comms/core/{auth,mutations,groups,objects,security,context_handles}*` and schema v4, the admin adapters (`transports/telegram/{bot,user}/admin_messages.py`, WhatsApp groups/templates/media/http), `formal/operations_model.py`, `scripts/e2e_smoke.py`, `docs/runbooks/{install,uninstall,clients-*}.md`, `docs/verification/comms-v0.3{,-rulings,-smoke-map}.*`, `tests/{services,mcp,cli,runtime,evaluation}/*` and the security, formal and integration tests named in the evidence, this file, `CHANGELOG.md`, `CLAUDE.md`.
- **Verification:** full gate at the Part D head: pytest 5023 passed, 4 skipped; smoke 74/74; formal 57 passed; ruff, format, mypy (275 files) and build clean; WhatsVault 450 passed. The Part D exit gate re-runs every owning test of design D.1–D.11 with no skip allowed. Evidence: `docs/verification/comms-v0.3.md`.
- **Follow-ups:**
  - The daemon must open `comms.db` and serve the composition. This blocks every P §88 row.
  - 13 tools are not offered.
  - Most operator commands are unwired.
  - `cml1` replay within 60 s is not tracked.
  - The proxy frames, backups and webhook responses were not egress-swept.
  - Carried from Part C: the update stream, the WhatsVault archive binding and per-recipient template language.
  - R-A20 awaits the owner.
  - The local tag `comms-v0.3-part-d` is not pushed; merge and push need the owner's approval.
  - No production claim.

### 2026-09-25 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms v0.3 D39-PRE / Runtime Completion, Task E0 (branch `comms-v0.3-d39pre`): the owner's rulings, the host permission rules, and a correction.
- **Summary:**
  - The owner decided R-A20: host permission UX is defence in depth. `.claude/settings.json` now asks before every consequential comms tool, 43 of them, generated from the catalog. There is no blanket allow, and the CLI campaign-send rules are kept.
  - Also approved: R-E1 (a `cml1` lease may be reused within its window; write safety comes from the request id), R-E2 (template language is explicit per campaign) and R-E3 (a registered operator command works, or it is not registered).
  - **Correction:** the Parts A–D entries above say their tags are "not pushed". All four `comms-v0.3-part-*` tags, `main` (merge `272dd8b`) and the `comms-v0.3` branch were pushed with the owner's approval on 2026-09-25.
  - The D39-PRE plan was owner-approved with four amendments.
  - **Found:** two test files on `main` (`tests/services/handle_fixtures.py`, `test_ctx_handles.py`) had misordered imports that the gate never reported. Ruff's cache keys on file content and settings, but its first-party import detection reads the filesystem, so it kept a stale clean result. Both files are fixed, and the gate now runs `ruff check` and `ruff format --check` with `--no-cache`.
- **Files changed:** `.claude/settings.json`, `tests/security/test_host_permissions.py`, `docs/runbooks/clients-claude-code.md`, `docs/verification/comms-v0.3{,-rulings}.md`, `docs/superpowers/plans/2026-09-25-comms-v0.3-d39-pre.md`, `tests/services/{handle_fixtures,test_ctx_handles}.py` (import order), this file, `CHANGELOG.md`.
- **Verification:** full gate (see the E0 ledger line); `test_host_permissions` 4 passed after watching the ask-rule test fail.
- **Follow-ups:** E1–E11 of the plan; the 13-tool disposition plan must be done before D39-B. No production claim.

### 2026-09-25 (Australia/Sydney)
**Raouf:**
- **Scope:** Comms v0.3 D39-PRE / Runtime Completion, tasks E1–E11 (branch `comms-v0.3-d39pre`), owner-approved plan with four amendments, inline and test-first.
- **Summary:** The daemon now holds `comms.db` and serves the whole v0.3 surface for real:
  - `comms keys provision`, and a fail-closed open with derived bootstrap states;
  - `comms.json` settings, and one composition root shared with the smoke;
  - startup recovery and supervised workers under two failure classes, with a write hold until the cutover;
  - the local, remote and webhook listeners and the admin socket;
  - every operator command working or absent: keys, audit, cutover, credentials (proved live and reloaded), the Telegram login flows, retention, backup, and a read-only doctor;
  - the Telegram user actor on its own Telethon thread with the update stream live, and Telethon's self-sent requests pinned;
  - a comms-native WhatsApp archive (the owner's choice), and egress sweeps over proxy frames, webhook responses and backups.

  D39-A drives a real selftest daemon through the installed binary only: 25 smoke checks.
- **Found by driving the real daemon (fixed):**
  - sends were never delivered;
  - a fresh install could never cut over;
  - a fresh daemon's effect loops never resumed after the cutover;
  - nothing ran retention;
  - the bot poller was never built;
  - no WhatsApp context source existed;
  - Telethon's `connect` sent unreviewed requests;
  - a restore dropped every person's name;
  - a restored group was invisible;
  - the reader rule had two copies;
  - the doctor counted client seeds as orphans;
  - the install runbook was out of order.

  Rulings R-E4 to R-E17 are in the register.
- **Files changed:** `src/comms/runtime/{paths,provision,state,settings,assemble,workers,serve,selftest,doctor,proofs}.py`, `src/comms/runtime/operator/*`, `src/comms/transports/telegram/runtime/{daemon,composition,telethon_thread,lock}.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/transports/whatsapp/webhooks/{archive,ingress}.py`, `src/comms/core/{groups,credentials,doctor}.py`, `src/comms/core/{keys/slots,keys/rotate,backup/*,campaigns/directory,maintenance/retention,storage/migrations,audit/writer}.py`, `src/comms/{cli,cli_commands/operator,mcp/dispatch,services/context,runtime/facades,runtime/adapters,runtime/comms_runtime}.py`, `scripts/{e2e_smoke,smoke_daemon}.py`, `docs/runbooks/{install,restore-from-backup,uninstall,key-compromise,clients-*}.md`, `docs/verification/{comms-v0.3,comms-v0.3-rulings,comms-v0.3-smoke-map.json,telegram-rpc-review}.md`, and the tests named in the D39-PRE exit gate, this file, `CHANGELOG.md`, `CLAUDE.md`.
- **Verification:** full gate at the D39-PRE head: pytest 5160 passed, 4 skipped; smoke 99/99 (25 against a real daemon); formal 57 passed; ruff (no cache), format, mypy (295 files) and build clean; WhatsVault 450 passed. The D39-PRE exit gate re-runs every owning test of E0–E11 with no skip allowed. Evidence: `docs/verification/comms-v0.3.md` (D39-PRE).
- **Follow-ups:**
  - The catalog-amendment plan comes before D39-B: the owner's `comms_directory_*` tools, a WhatsApp MCP route, and the 13 not-offered tools.
  - `grp_` refs are not in backups.
  - The local tag `comms-v0.3-d39-pre` is not pushed; merge and push need the owner's approval.
  - No production claim.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G6a. The last gauntlet re-checked the actor matrix against the live 2026 developer docs (branch `comms-v0.3-catalog`).
- **Summary:** No cell flips between A and B. All 30 cited Bot API methods (10.3, 2026-08-24) and all 47 cited MTProto methods exist; the forum-topic requests are `messages.*`, matching Telethon 1.45.0 (layer 229). Meta confirms the WhatsApp gaps (edit and delete are non-supported in groups; the Message History Events API is status-only). Recorded for the builders:
  - `getChatAdministrators(return_bots=True)`;
  - a WhatsApp pin requires `expiration_days`;
  - a group holds at most 8 participants.

  **Found:** the Graph API pin (v21.0) expires on 2027-01-21. G9 now moves it.
- **Files changed:** `docs/verification/comms-v0.3-actor-matrix.md`, `docs/verification/comms-v0.3-rulings.md` (R-G6a-docs), `docs/superpowers/plans/2026-09-25-comms-v0.3-catalog-amendment.md` (G9), `tests/core/providers/test_actor_matrix.py` (+1 test), the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** The raw doc pages were fetched and grepped; the full gate passed (GATE ok=1).
- **Follow-ups:** The owner rules whether member tags, reaction moderation and WhatsApp `health_status` join the catalog (they are outside A45). G9 bumps the Graph version.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Spec amendment A46. The owner added the 2026-docs admin surface to the catalog (branch `comms-v0.3-catalog`).
- **Summary:** Four tools:
  - `comms_group_member_tag_set`: Bot `setChatMemberTag`, MTProto `messages.editChatParticipantRank`;
  - `comms_message_reaction_remove`: `deleteMessageReaction` / `messages.deleteParticipantReaction`;
  - `comms_group_member_reactions_clear`: `deleteAllMessageReactions` / `messages.deleteParticipantReactions`;
  - `comms_whatsapp_health_status`: Graph `health_status`, with entity ids dropped.

  WhatsApp is B for the three Telegram tools. G7 builds the Telegram tools and G8 the health tool; G9 requires them all in the catalog.
- **Files changed:** `docs/comms-spec-v0.3.md` (A46), `docs/verification/comms-v0.3-rulings.md` (a pin and R-A46), the plan (G7, G8, G9), `docs/verification/comms-v0.3-actor-matrix.md`, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** The preflight pin and the actor-matrix tests pass; the full gate passed (GATE ok=1).
- **Follow-ups:** Build them in G7 and G8.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G1: WhatsApp groups as destinations with `grp_` refs (branch `comms-v0.3-catalog`).
- **Summary:** A WhatsApp group (`group:<id>`, one rule `wa_group_id`) is a directory destination with a `grp_`. Group tools target it through `whatsapp_cloud`, and its context is the comms webhook archive over MCP (`recent`, pages, `get`, `message_get`, `around`).
- **Found and fixed:**
  - Meta's group ids are opaque, but the Graph client accepted digits only;
  - the schema admitted Telegram destinations only (v6 rebuild);
  - the archive answered every read kind as `recent`;
  - two actor-matrix cells were false: `member_invite` on WhatsApp is not wired (now G8), and `member_add` answers INVITE_REQUIRED by design.
- **Files changed:** `src/comms/transports/whatsapp/numbers.py`, `cloud/http.py`, `cloud/groups.py`, `webhooks/archive.py`, `src/comms/core/storage/migrations.py` (v6), `src/comms/core/campaigns/directory.py`, `src/comms/core/groups.py`, `src/comms/runtime/facades.py`, `src/comms/services/context.py`; tests `tests/runtime/test_whatsapp_group_destinations.py`, `tests/core/test_schema_v6.py`, `tests/integration/test_actor_matrix_behaviour.py`, `tests/runtime/test_facades.py`; the matrix, the rulings (R-G1), the plan, the ledger, `AGENT.md` and `CHANGELOG.md`.
- **Verification:** 29 new tests; the behaviour test covers all three actors (mutation-checked); the full gate passed (GATE ok=1).
- **Follow-ups:**
  - G4 proves a backup round trip of a WhatsApp group's `grp_` (D5);
  - G8 adds the invite GET, participants and `group_context` for WhatsApp;
  - G6 adds the bot's `around` from retained updates.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G2a. The daemon wires the WhatsApp actor (branch `comms-v0.3-catalog`).
- **Summary:** `build_comms_runtime` never listed `whatsapp_cloud` as an actor, nor passed WhatsApp template or media services or an account target. In production, WhatsApp groups and the WhatsApp account tools therefore answered `NOT_CONFIGURED`, while tests that built their own services passed. They are now wired from `Adapters`, and the actor-matrix behaviour test goes through the real composition root.
- **Files changed:** `src/comms/runtime/adapters.py`, `src/comms/runtime/comms_runtime.py`, `tests/runtime/test_comms_runtime_whatsapp.py`, `tests/integration/test_actor_matrix_behaviour.py`, the rulings (R-G2a), the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 4 new composition tests; the behaviour test was mutation-checked on the actor list; the full gate passed (GATE ok=1).
- **Follow-ups:** None.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G2: the `comms_directory_recipient_*` tools (branch `comms-v0.3-catalog`).
- **Summary:** Six tools (list, get, create, update, enable, disable) over the core directory. Labels appear under `untrusted`; contact points appear by ref and transport, never by identity; every write is audited and replays by `req_`. The catalog pin is regenerated per task, on purpose (R-G2; 109 to 115 tools). The egress rule now counts an `untrusted` object as text.
- **Files changed:** `src/comms/mcp/tools/directory_people.py` (new), `src/comms/mcp/tools/__init__.py`, `src/comms/services/directory.py`, `src/comms/core/campaigns/directory.py`, `src/comms/core/campaigns/directory_views.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/egress.py`, `tests/mcp/test_catalog_directory_people.py` (new), `tests/security/test_v03_egress.py`, `tests/mcp/catalog_pin.json`, the rulings, the plan, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 48 new tests; the egress sweep runs the new tools; the full gate passed (GATE ok=1).
- **Follow-ups:** G3 adds contact points.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G3: `comms_directory_contact_*` (branch `comms-v0.3-catalog`).
- **Summary:** Add, disable and opt out a person's WhatsApp number or Telegram user id. The identity is input only: it is bound to the request by a keyed HMAC (an unkeyed digest of a phone number in the audit chain could be brute-forced) and never echoed. An opt-out now survives disabling and blocks re-adding. `contact_add` is host-confirmed.
- **Files changed:** `src/comms/core/domains.py`, `src/comms/core/campaigns/binding.py` (new), `src/comms/core/campaigns/directory.py`, `src/comms/services/directory.py`, `src/comms/runtime/comms_runtime.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/tools/directory_people.py`, `.claude/settings.json`; tests `tests/mcp/test_catalog_directory_contacts.py` (new), `tests/mcp/test_catalog_directory_people.py`, `tests/security/test_v03_egress.py`, `tests/security/test_comms_wire_frozen.py`, `tests/mcp/catalog_pin.json`; the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 26 new tests (the opt-out guard mutation-checked); the full gate passed (GATE ok=1).
- **Follow-ups:** G4 adds destinations and location membership.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G4: destinations, location membership and D5 (branch `comms-v0.3-catalog`).
- **Summary:** Create and disable chats by the provider's own id (Telegram marked chat ids, Meta group ids), input only; a group gets its `grp_` at once. Add and remove location members. Backups now keep every `grp_`: a compatible restore reuses them, a conflicting binding is a staged incompatibility, and a missing provider's groups are restored disabled with refs kept.
- **Files changed:** `src/comms/core/backup/payload.py`, `src/comms/core/backup/export_import.py`, `src/comms/services/directory.py`, `src/comms/runtime/comms_runtime.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/tools/directory_people.py`, `.claude/settings.json`; tests `tests/mcp/test_catalog_directory_places.py` and `tests/core/backup/test_backup_groups.py` (both new), `tests/mcp/catalog_pin.json`; the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 32 new tests; the full gate passed (GATE ok=1).
- **Follow-ups:** G5 adds per-person context.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G5: `comms_context_person` (branch `comms-v0.3-catalog`).
- **Summary:** One person's direct communication, by source: WhatsApp archive DMs, the Telegram private chat (live, else the bot's retained updates) and campaign history. Their messages in up to ten groups appear only when asked, read by a new sender-filtered `from` kind in the archive and the bot's context. Every section is a normal context page that pages through `comms_context_page`. No number or id appears.
- **Files changed:** `src/comms/runtime/facades.py`, `src/comms/services/context.py`, `src/comms/core/campaigns/directory.py`, `src/comms/core/groups.py`, `src/comms/transports/whatsapp/webhooks/archive.py`, `src/comms/transports/telegram/bot/context.py`, `src/comms/mcp/tools/context.py`, `src/comms/mcp/tools/__init__.py`, `src/comms/mcp/egress.py`; tests `tests/runtime/test_context_person.py` (new), `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 6 new tests; the actor matrix covers the tool on all three actors; the full gate passed (GATE ok=1).
- **Follow-ups:** G6 adds the user account's sender search.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G6, part 1: Telegram group reads (branch `comms-v0.3-catalog`).
- **Summary:** Admins are read as admins, which fixes the bot's admin list and group context. One member's standing, default permissions and join requests are served on both actors where the API allows, with every user id mapped to a `rcp_` ref or `null`. The bot serves `around`, `message_get` and join requests from its retained updates. A prohibited RPC (`channels.getChannels`) was caught by the independent guard and replaced with a reviewed one. User mark-read waits on the owner, because the frozen spec prohibits `messages.readHistory`.
- **Files changed:** `src/comms/services/group_reads.py` (new), `src/comms/services/context.py`, `src/comms/runtime/facades.py`, `src/comms/transports/telegram/bot/context.py`, `src/comms/transports/telegram/user/context.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/core/campaigns/directory.py`, `src/comms/mcp/tools/admin.py`, `src/comms/mcp/tools/groups.py`, `src/comms/mcp/egress.py`; tests (three new modules, plus updates), `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 22 new tests; the behaviour matrix passes on all three actors; the full gate passed (GATE ok=1).
- **Follow-ups:** G6 part 2: the user account's invite list, join requests, topics, admin log and sender search.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G6, part 2: the user account's lists and the primary-link reset (branch `comms-v0.3-catalog`).
- **Summary:** The user account lists invites, join requests, topics (and one topic) and the admin log. Its sender search serves a person's group activity. Invite revoke with no invite resets the primary link on both Telegram APIs and returns the new ref. Every provider id is mapped to a ref. The admin-log read now has one copy.
- **Files changed:** `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/transports/telegram/user/context.py`, `src/comms/transports/telegram/user/admin.py`, `src/comms/transports/telegram/user/admin_chat.py`, `src/comms/transports/telegram/user/capability.py`, `src/comms/transports/telegram/bot/*.py`, `src/comms/transports/telegram/chat_specs.py`, `src/comms/services/group_reads.py`, `src/comms/services/groups.py`, `src/comms/core/providers/semantics.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/tools/admin.py`, `src/comms/mcp/egress.py`, `docs/verification/telegram-rpc-review.md`; tests (three new modules, plus updates), `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 16 new tests; no G6 cell is left in the matrix; the full gate passed (GATE ok=1).
- **Follow-ups:** G7 (Telegram writes and A46's three tools).

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G7, part 1: forward and group create (branch `comms-v0.3-catalog`).
- **Summary:** Forward works on both Telegram APIs; the user account's forward is deduplicated by `random_id` like a send, through one shared reconcile path. The user account creates a group or channel, which is filed in the directory with its `grp_` in the same step. A WhatsApp forward crash was found and turned into a refusal.
- **Files changed:** `src/comms/transports/telegram/user/send.py`, `src/comms/transports/telegram/user/admin.py`, `src/comms/transports/telegram/user/admin_messages.py`, `src/comms/transports/telegram/user/capability.py`, `src/comms/transports/telegram/bot/admin.py`, `src/comms/transports/telegram/bot/admin_messages.py`, `src/comms/transports/telegram/chat_specs.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/services/mutations.py`, `src/comms/services/writes.py`, `src/comms/services/messages.py`, `src/comms/services/groups.py`, `src/comms/services/directory.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/tools/messages.py`; tests; `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 13 new tests; the full gate passed (GATE ok=1).
- **Follow-ups:** G7 part 2 adds A46's three tools.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G7, part 2: spec A46's Telegram tools (branch `comms-v0.3-catalog`).
- **Summary:** `comms_group_member_tag_set`, `comms_message_reaction_remove` and `comms_group_member_reactions_clear` on both Telegram APIs, with three new capabilities, three reviewed MTProto requests and three Bot API methods, all host-confirmed. WhatsApp is B.
- **Files changed:** `src/comms/core/providers/capability.py`, `src/comms/core/providers/semantics.py`, `src/comms/transports/telegram/chat_specs.py`, `src/comms/transports/telegram/bot/{admin_members,capability,http}.py`, `src/comms/transports/telegram/user/{admin_members,capability}.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/services/groups.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/tools/{groups,__init__}.py`, `.claude/settings.json`, `docs/verification/telegram-rpc-review.md`; tests; `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 16 new tests; the full gate passed (GATE ok=1).
- **Follow-ups:** G8: WhatsApp group writes, account and media, and A46's health status.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G8, part a: WhatsApp group writes and live group reads (branch `comms-v0.3-catalog`).
- **Summary:** Group send and pin; join requests listed, approved and rejected; participants and the invite link. Group facts are read live under `whatsapp_live`, which is never allowed for messages. People appear as `rcp_` refs; no number or id leaves.
- **Files changed:** `src/comms/transports/whatsapp/cloud/{http,groups,context}.py` (`context.py` is new), `src/comms/runtime/adapters.py`, `src/comms/runtime/facades.py`, `src/comms/services/{context,messages,groups}.py`, `src/comms/core/providers/semantics.py`, `src/comms/mcp/tools/{context,admin,messages}.py`; tests; `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 11 new tests; the Meta oracle covers every Graph call; the full gate passed (GATE ok=1).
- **Follow-ups:** G8 parts b to d: WhatsApp group create and delete, account and health, and media.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G8, part b: WhatsApp group create and delete (branch `comms-v0.3-catalog`).
- **Summary:** Meta creates a group asynchronously. The request is kept pending (schema v7) until the `group_lifecycle_update` webhook names it; the group is then filed with its `grp_`, or the creation is marked failed. Delete asks Meta. A create naming no actor when both platforms are configured is refused as ambiguous.
- **Files changed:** `src/comms/core/storage/migrations.py` (v7), `src/comms/core/campaigns/directory.py`, `src/comms/core/providers/semantics.py`, `src/comms/transports/whatsapp/cloud/{http,groups}.py`, `src/comms/transports/whatsapp/webhooks/archive.py`, `src/comms/services/{directory,groups}.py`, `src/comms/runtime/facades.py`, `src/comms/mcp/tools/admin.py`; tests; `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 5 new tests; the full gate passed (GATE ok=1).
- **Follow-ups:** Live acceptance must confirm Meta's synchronous create body (R-G8b). Next: G8 parts c and d.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G8, part c: account profile, phone status and A46's health status (branch `comms-v0.3-catalog`).
- **Summary:** Each account shows what it calls itself (untrusted), never an identity. WhatsApp phone status and messaging health are offered; health drops every entity id.
- **Files changed:** `src/comms/transports/profiles.py` (new), `src/comms/transports/whatsapp/cloud/{account,http}.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/runtime/{adapters,comms_runtime,facades}.py`, `src/comms/services/account.py`, `src/comms/core/providers/{capability,semantics}.py`, `src/comms/mcp/tools/{account,groups}.py`, `src/comms/mcp/egress.py`; tests; `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 6 new tests; the full gate passed (GATE ok=1).
- **Follow-ups:** G8 part d: media upload and download, and group photos.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G8, part d: staged media (D3), media upload and download, and group photos (branch `comms-v0.3-catalog`).
- **Summary:** Files are staged in memory for one client (`upl_`), checked by SHA-256 and used once; bytes never reach a request digest. WhatsApp media upload and paged download; group photos on the bot, the user account and WhatsApp. `NOT_OFFERED` is gone, and no open cell is left in the actor matrix. Telegram media objects are marked "not addressed" (nothing consumes them): the owner is asked to confirm.
- **Files changed:** `src/comms/services/uploads.py` (new), `src/comms/services/{media,mutations,groups}.py`, `src/comms/core/refs.py`, `src/comms/runtime/facades.py`, `src/comms/transports/telegram/{chat_specs,bot/http,bot/admin,bot/admin_chat,user/admin,user/admin_chat,telegram/telethon_adapter}.py`, `src/comms/transports/whatsapp/cloud/{http,groups,media}.py`, `src/comms/mcp/tools/{account,admin,__init__}.py`, `docs/verification/telegram-rpc-review.md`; tests; `tests/mcp/catalog_pin.json`; the matrix, the rulings, the ledger, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 15 new tests; the full gate passed (GATE ok=1).
- **Follow-ups:** G9 (the pin, the guards, D39-A, the exit test and the evidence). The owner decides on Telegram media objects and on Telegram mark-read (the frozen spec prohibits `readHistory`).

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** Catalog amendment G9: the pin, the guards, D39-A, the exit gate and the evidence (branch `comms-v0.3-catalog`).
- **Summary:** The Graph API is pinned at v26.0 (v21.0 expires on 2027-01-21). The real-daemon smoke gains four `catalog_*` checks (the directory, a location campaign, a WhatsApp group webhook read by `grp_`, `comms_context_person`). The exit test re-runs every G-task's tests from the plan's headings with nothing skipped, plus one end-to-end MCP path. The client runbooks no longer wait on the amendment.
- **Files changed:** `src/comms/transports/whatsapp/cloud/http.py`, `scripts/{smoke_daemon,e2e_smoke}.py`, `tests/security/test_catalog_amendment_exit.py` (new), `tests/security/test_d39_pre_exit.py`, `tests/conformance/meta_oracle.py`, `tests/core/providers/test_actor_matrix.py`, `tests/transports/whatsapp_cloud/test_{account_groups,classify,media,templates}.py`, `docs/verification/{comms-v0.3.md,comms-v0.3-rulings.md,comms-v0.3-actor-matrix.md,comms-v0.3-smoke-map.json}`, `docs/runbooks/clients-*.md`, `CLAUDE.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the full gate passed (GATE ok=1): 5420 passed, 4 skipped; smoke 103/103 (29 against the daemon); formal 57; ruff, format, mypy, build clean; WhatsVault 450.
- **Follow-ups:** the owner decides Telegram mark-read, Telegram media objects, and merge/push/tag push; D39-B confirms WhatsApp group create's synchronous response live.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** The owner's answers to G9's open questions: spec A47, its plan, and a WhatsApp group-photo fix (branch `comms-v0.3-catalog`).
- **Summary:** The owner allowed Telegram user mark-read and asked for Telegram media to be built; A47 specifies both (one prohibition lifted, narrowly; `comms_message_send_media` on all three actors; Telegram `med_` refs, download, user upload). The 2026-docs search confirmed WhatsApp group create answers `request_id` (pywa 4.5.0) and found a defect: the group photo must be the multipart part `profile_picture_file`, not `file`. The oracle now refuses any other part.
- **Files changed:** `src/comms/transports/whatsapp/cloud/http.py`, `tests/conformance/meta_oracle.py`, `docs/comms-spec-v0.3.md` (A47), `docs/verification/{comms-v0.3.md,comms-v0.3-rulings.md}` (A47 pin, R-G9b), `docs/superpowers/plans/2026-09-26-comms-v0.3-a47.md` (new), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the oracle test failed on the old part name and passes on the fix; the capability-id test now bounds each amendment's section (it read A47 as part of A46); the full gate (GATE ok=1).
- **Follow-ups:** the owner approves the A47 plan (H1–H6); merge and push of `comms-v0.3-catalog`.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** The A47 plan gauntleted against the developer docs (branch `comms-v0.3-catalog`).
- **Summary:** Eighteen findings (Gf1–Gf18) from Telegram's files, file-reference, datacenter and config pages, the method and constructor pages, Bot API 10.3, Meta's media reference and group messaging, pywa 4.5.0 and the installed Telethon 1.45.0. Two corrected A47: files live on their own DC (downloads go there through a borrowed sender under the same allowlist, never refused), and an uploaded file has no message to refresh its reference from (an expiry answers `NOT_FOUND`). The rest refine the plan: the bot's `med_` is keyed by `file_unique_id`; one part-upload helper covers files above 10 MB (`saveBigFilePart`) and is shared with G8's group photo; there are no kind changes on resend; `cdn_supported` stays unset; `FLOOD_PREMIUM_WAIT` is a rate limit; WhatsApp images are JPEG or PNG at most 5 MB; the bot file URL carries the token.
- **Files changed:** `docs/superpowers/plans/2026-09-26-comms-v0.3-a47.md`, `docs/comms-spec-v0.3.md` (A47 corrected), `docs/verification/comms-v0.3-rulings.md` (re-pin, R-A47-docs), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the preflight pin, capability-id and supersession tests; the full gate (GATE ok=1).
- **Follow-ups:** the owner approves the gauntleted A47 plan before H1.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** The A47 plan gauntleted again, this time by executing the code it relies on (branch `comms-v0.3-catalog`).
- **Summary:** Thirteen findings (Gx1–Gx13). Three would have broken H1–H3: Telethon's exported-sender path sends `auth.exportAuthorization` and `help.getConfig` through our allowlist; a person's Telegram `cmg_` can be the bot's, with the bot chat's ids; the mark-read facade is WhatsApp-only. Also: the migrate and expired-reference errors need catching before the general classification; there are no media columns (schema v8 `media_facts`); `file_id` is read from the retained update rather than stored twice; Telethon's public `get_input_location` is used and pinned; WhatsApp images are checked by magic bytes; the bot download is streamed, capped and path-checked; and `cmg_` replaces `msg_`, which is WhatsVault's.
- **Files changed:** `docs/superpowers/plans/2026-09-26-comms-v0.3-a47.md`, `docs/comms-spec-v0.3.md` (A47 corrected), `docs/verification/comms-v0.3-rulings.md` (re-pin, R-A47-docs2), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** each finding was produced by running Telethon 1.45.0 or our code (a temporary probe test, not committed); the full gate (GATE ok=1).
- **Follow-ups:** the owner approves the A47 plan before H1.

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** A47 H1: the Telegram user account marks a person's conversation read (branch `comms-v0.3-a47`).
- **Summary:** `messages.readHistory` on a person's peer, reviewed under `cap.message.mark_read` only; every other read-acknowledge request stays absent. The facade routes by the `cmg_`'s actor. The write path now refuses another actor's message id outside a supergroup or channel, which fixes a latent cross-actor defect for edit, delete and pin as well.
- **Files changed:** `src/comms/core/providers/semantics.py`, `src/comms/transports/telegram/user/{capability,admin,admin_messages}.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/services/{messages,writes}.py`, `src/comms/runtime/facades.py`, `tests/transports/test_mark_read.py` (new), `tests/security/test_phase4_architecture.py`, `tests/integration/test_actor_matrix_behaviour.py`, `docs/verification/{telegram-rpc-review.md,comms-v0.3-actor-matrix.md,comms-v0.3-rulings.md}`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 10 new tests, written first and seen failing; the full gate (GATE ok=1).
- **Follow-ups:** H2 (Telegram `med_` refs and schema v8).

### 2026-09-26 (Australia/Sydney)
**Raouf:**
- **Scope:** A47 H2: Telegram media as `med_` refs (branch `comms-v0.3-a47`).
- **Summary:** Schema v8 `media_facts`. A photo or document in a context item gets a `media_ref`: the user account's is keyed by the message locator, the bot's by `file_unique_id`. Kind, MIME type and size are recorded; no file id or file reference is stored a second time or output.
- **Files changed:** `src/comms/core/storage/migrations.py`, `src/comms/core/objects.py`, `src/comms/services/context.py`, `src/comms/mcp/tools/context.py`, `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/transports/telegram/{user,bot}/context.py`, `tests/runtime/test_telegram_media_refs.py` (new), `tests/mcp/catalog_pin.json` (14 context tools gain `media_ref`), the rulings, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 6 new tests, written first and seen failing; the full gate (GATE ok=1).
- **Follow-ups:** H3 (Telegram download).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** A47 H3: downloading a Telegram `med_` on both APIs (branch `comms-v0.3-a47`).
- **Summary:** Bot: `getFile`, then a streamed and capped GET, with the path checked and the token never reaching an error. User account: the message is fetched again, then `upload.getFile` in aligned slices, on the file's own DC through a reviewed borrowed sender (new `media.download` operation). One capped reader and one `DownloadRefused` in `transports/net.py`. This also fixes a latent defect: a refused WhatsApp download escaped as an internal error. The media service is built even without WhatsApp.
- **Files changed:** `src/comms/transports/net.py`, `src/comms/transports/whatsapp/cloud/media.py`, `src/comms/transports/telegram/bot/{http,media}.py` (`media.py` new), `src/comms/transports/telegram/user/media.py` (new), `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/services/media.py`, `src/comms/runtime/{adapters,comms_runtime,facades}.py`, tests (`test_telegram_download.py` new, the fake client, the admin harness, the matrix, update-RPC and phase-4 guards), `docs/verification/{telegram-rpc-review.md,comms-v0.3-actor-matrix.md,comms-v0.3-rulings.md}`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 24 new tests, written first and seen failing, plus 2 Telethon pins; the full gate (GATE ok=1).
- **Follow-ups:** H4 (`comms_message_send_media`).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** A47 H4: `comms_message_send_media` on the bot, the user account and WhatsApp (branch `comms-v0.3-a47`).
- **Summary:** A photo or document from a staged upload, inline bytes or a held `med_`, with a caption of at most 1024 UTF-16 units. Bot: multipart or by the retained `file_id`. User account: the one part upload (its own `file.upload` operation, `saveBigFilePart` above 10 MB, now shared with G8's group photo), then a keyed `messages.sendMedia`. WhatsApp: upload, then a group image or document message. Limits, kind mismatches, another account's file and a WhatsApp id older than 30 days are refused before any call.
- **Files changed:** `src/comms/core/providers/{capability,semantics,media}.py` (`media.py` new), `src/comms/services/{messages,writes}.py`, `src/comms/runtime/{facades,comms_runtime,adapters}.py`, `src/comms/mcp/tools/messages.py`, `src/comms/transports/telegram/{bot/admin,bot/admin_messages,bot/http,bot/media,bot/capability,user/admin,user/admin_messages,user/send,user/capability,telegram/telethon_adapter}.py`, `src/comms/transports/whatsapp/cloud/groups.py`, `.claude/settings.json`, tests (`test_send_media.py` new, and the catalog, pin, matrix, RPC-set and phase-4 guards), `tests/mcp/catalog_pin.json` (130 tools), `docs/verification/{telegram-rpc-review.md,comms-v0.3-actor-matrix.md,comms-v0.3-rulings.md}`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 20 new tests, written first and seen failing; the full gate (GATE ok=1).
- **Follow-ups:** H5 (user upload and inspect), H6 (the guards, D39-A checks, the exit test and the evidence).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** A47 H5: the user account's media upload, and a Telegram `med_`'s inspect and delete (branch `comms-v0.3-a47`).
- **Summary:** `comms_media_upload` with `actor: telegram_user` uploads to the account itself (`messages.uploadMedia`, peer self) and returns a reusable `med_`, sent later without a fetch. A media send's documented refusals are now final and named (an expired reference is `NOT_FOUND`), not unknown. Inspect of a Telegram `med_` reads its recorded facts with no call; delete is unsupported (Telegram has none). An upload naming no actor with both platforms configured is ambiguous.
- **Files changed:** `src/comms/core/providers/semantics.py`, `src/comms/services/media.py`, `src/comms/runtime/{facades,comms_runtime}.py`, `src/comms/mcp/tools/account.py`, `src/comms/transports/telegram/{user/admin,user/admin_messages,user/capability,telegram/telethon_adapter,telegram/send_attempt}.py`, tests (`test_telegram_upload.py` new; the fixtures and the phase-4 guard), `tests/mcp/catalog_pin.json`, `docs/verification/{telegram-rpc-review.md,comms-v0.3-actor-matrix.md,comms-v0.3-rulings.md}`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 9 new tests, written first and seen failing; the full gate (GATE ok=1).
- **Follow-ups:** H6 (the guards, D39-A checks, the exit test and the evidence).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** A47 H6: the guards, D39-A media checks against a real daemon, the exit gate, the evidence (branch `comms-v0.3-a47`).
- **Summary:** Driving the real daemon found that G8's staged media never fit the wire (a 48 KiB chunk's base64 is already 64 KiB, the request and frame cap); chunks, slices and inline files are now 32 KiB raw, and a guard test proves every file-carrying call fits on both routes. Two new real-daemon checks: a staged photo sent once by the bot with its replay, and a retained document paged back whole with its SHA-256. The A47 exit test re-runs H0–H6. Evidence and CLAUDE.md updated.
- **Files changed:** `src/comms/services/uploads.py`, `src/comms/mcp/tools/{account,admin,messages}.py`, `src/comms/runtime/{selftest,facades}.py`, `scripts/{smoke_daemon,e2e_smoke}.py`, `tests/security/{test_media_fits_the_wire,test_a47_exit}.py` (new), `tests/security/test_d39_pre_exit.py`, `tests/transports/test_telegram_download.py`, `tests/mcp/catalog_pin.json`, `docs/verification/{comms-v0.3.md,comms-v0.3-rulings.md,comms-v0.3-smoke-map.json}`, `CLAUDE.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the full gate (GATE ok=1): 5505 passed, 4 skipped; smoke 105/105 (31 against the daemon); formal 57; WhatsVault 450.
- **Follow-ups:** the owner merges and pushes `comms-v0.3-catalog` then `comms-v0.3-a47`; D39-B live media checks.

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** Land the catalog amendment and A47 on `main` and push (owner: "merge and push all").
- **Summary:** `comms-v0.3-catalog` merged (`c940ff6`), then `comms-v0.3-a47` (`f60a46f`), both `--no-ff`. The merged tree is byte-identical to the gated A47 head `2a864be`. Pushed `main`, both branches and the tags `comms-v0.3-catalog-amendment` and `comms-v0.3-a47-media`; the evidence records their SHAs.
- **Files changed:** `docs/verification/comms-v0.3.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the gate on `2a864be` (GATE ok=1: 5505 passed, smoke 105/105); `main^{tree}` equals `comms-v0.3-a47^{tree}`; `origin/main` equals `main` after the push; the evidence-reading exit tests pass.
- **Follow-ups:** D39-B (owner-run, live).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** A full end-to-end test of every function: the whole catalog swept against the real daemon (branch `comms-v0.3-sweep`).
- **Summary:** `scripts/smoke_sweep.py` calls all 130 tools over HTTP `/mcp` on `comms selftest-daemon`: 112 succeed with schema-valid output, and 18 give their pinned refusal (each with its reason). It found two tools that could answer `AMBIGUOUS_TARGET` without declaring it (fixed) and a selftest Bot API that could not serve any chat read (fixed).
- **Files changed:** `scripts/smoke_sweep.py` (new), `scripts/{smoke_daemon,e2e_smoke}.py`, `src/comms/runtime/selftest.py`, `src/comms/mcp/tools/{admin,account}.py`, `tests/mcp/catalog_pin.json`, `tests/security/{test_a47_exit,test_d39_pre_exit}.py`, `docs/verification/{comms-v0.3.md,comms-v0.3-rulings.md,comms-v0.3-smoke-map.json}`, `CLAUDE.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the full gate (GATE ok=1): 5506 passed, 4 skipped; smoke 106/106; formal 57; WhatsVault 450.
- **Follow-ups:** the owner merges and pushes `comms-v0.3-sweep`; D39-B live.

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** Land the whole-catalog sweep on `main` and push (owner: "commit and push and merge").
- **Summary:** `comms-v0.3-sweep` merged `--no-ff` as `326c12d`; the merged tree is byte-identical to the gated branch head `d899c6a`. `main` and `comms-v0.3-sweep` are pushed. On this day `main` gained: the catalog amendment (`c940ff6`, tag `comms-v0.3-catalog-amendment`), A47 (`f60a46f`, tag `comms-v0.3-a47-media`), the tag-SHA record (`cbf62dc`) and the sweep (`326c12d`).
- **Files changed:** `AGENT.md`, `CHANGELOG.md` (this entry); the ledger (gitignored).
- **Verification:** the gate on `d899c6a` (GATE ok=1: 5506 passed, 4 skipped; smoke 106/106; formal 57; WhatsVault 450); `main^{tree}` equals `comms-v0.3-sweep^{tree}`; `origin/main` equals `main`. Zurvan updated with this day's decisions, claims and open questions (tags `telegram-mcp,comms`).
- **Follow-ups:** D39-B, owner-run and live: a WhatsApp group photo and document, a Telegram download from another DC, WhatsApp group create's `request_id`, and the P §88 acceptance rows. Campaign media needs its own amendment.

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp relay R0 and R1: spec A48, the relay keys, the frozen pull signature, and one copy of Meta's signature rule (branch `comms-relay`).
- **Summary:** Spec A48 makes the approved relay design normative, including D-R1: the relay never holds Meta's app secret. Two new key purposes are minted by `comms keys provision`:
  - `relay-age-key`: a new `x25519` kind, with key id `x25519:sha256:<public>`; rotating it is refused in this version;
  - `relay-pull-key`: `hmac`.

  `comms.core.relay_sig` signs under the frozen domain `comms-relay-pull/v1`, with eight byte-equality vectors. Found while building: `slots._checked` held a second copy of the key-id rule, and it now calls `key_id_for`; the audit key-id validator accepts `x25519`. Meta's `X-Hub-Signature-256` check moved into `webhooks/signature.py` (one copy). The local listener accepts up to 8 MiB, since Meta sets no limit and batches up to 1000 updates.
- **Files changed:** `docs/comms-spec-v0.3.md` (A48), the relay design (marked approved), the plan (new), the rulings (pin, R-R0), `src/comms/core/{domains,relay_sig,validators}.py`, `src/comms/core/keys/{purposes,ids,slots,rotate}.py`, `src/comms/core/backup/age.py` (`identity_from_raw`), `src/comms/runtime/provision.py`, `src/comms/transports/whatsapp/webhooks/{signature,ingress}.py`, tests (`tests/core/test_relay_sig.py`, `tests/transports/whatsapp_webhooks/test_signature.py` new; purposes, wire-frozen, provision), `tests/fixtures/relay/pull_signature_vectors.json`.
- **Verification:** New tests written first and seen failing; full gate GATE ok=1 (5519 passed, 4 skipped; smoke 106; WhatsVault 450).
- **Follow-ups:** R2 (the Worker and Mailbox), R3 (the collector), R4 (operator and doctor), R5 (end to end).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp relay R2: the Cloudflare Worker and its Mailbox (`relay/`, branch `comms-relay`).
- **Summary:** A TypeScript Worker on the secret webhook path.
  - **Refusals:** the wrong token 404, a non-JSON body 415, a malformed signature header 401, a body over 8 MiB 413, and the Mailbox's rate bound 429. It answers 200 only once the batch is stored, and 503 otherwise.
  - **Handshake:** the verify-token handshake is in constant time.
  - **Pulls:** `/pull` and `/ack` are signed under `comms-relay-pull/v1`.
  - **Mailbox:** one SQLite Durable Object. It `age`-encrypts the envelope `{batch, part, parts, raw_b64, received_at, signature}` to the daemon and stores bodies over 1 MiB as parts in one transaction. `seq` is `AUTOINCREMENT`, and a daily alarm purges rows after 30 days and raises `purged_through`.
  - **D-R1:** no app secret anywhere.

  Running it under `wrangler dev` found that workerd refuses a main module exporting a constant, which Vitest did not catch. The limits moved to `src/limits.ts`, and a test pins the exports. Dependencies are pinned exactly and every install script is denied. The gate now runs `(cd relay && npm ci && npm run check)`.
- **Files changed:** `relay/` (new: `src/{index,mailbox,pull_sig,limits}.ts`, `test/`, `wrangler.jsonc`, `package.json`, `package-lock.json`, `tsconfig.json`, `vitest.config.ts`, `.dev.vars.example`), `.gitignore`, `tests/security/test_relay_static.py` (new), `tests/fixtures/relay/wrangler_dev_page.json` (a page from the real Worker), the relay design, the rulings (R-R2), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 14 Vitest tests in workerd, including the shared pull-signature vectors and a 2.5 MiB batch reassembled exactly; the Worker run under `wrangler dev`, with its ciphertext decrypted by the daemon's `age`; full gate GATE ok=1 (the first run caught one lint finding, fixed and re-run).
- **Follow-ups:** R3 (the collector).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp relay R3: the daemon's collector (branch `comms-relay`).
- **Summary:** `transports/whatsapp/relay_client.py` is the one new network module: one pinned https origin, signed pulls and acks, a bounded answer, strict shapes and fixed errors. The collector, `runtime/relay.py`, is a 60-second worker loop. It works in `seq` order: decrypt, check the envelope against its row, reassemble parts, verify Meta's signature (the only place it is checked, D-R1), store in the inbox, move progress forward, then ack. A refused row is quarantined in comms.db with its ciphertext, because an ack is cumulative. Gaps not covered by a purge are recorded, and a clock skew is told apart from a wrong key.
  - Schema v9 holds `relay_state`, `relay_quarantine` and `relay_gaps`.
  - `comms.json` takes `"relay": {"url": ...}`, and with a relay the local listener is not served; the verify token lives in the Worker.
  - The composition loads the relay keys from the key slots.
- **Files changed:** `src/comms/transports/whatsapp/relay_client.py`, `src/comms/runtime/relay.py` (new); `src/comms/runtime/{adapters,assemble,settings,workers}.py`, `src/comms/core/storage/migrations.py`; tests (`tests/runtime/test_relay_collector.py`, `test_relay_wiring.py`, `tests/transports/test_relay_client.py` new; egress pin, v8 pin); the egress matrix in `docs/verification/comms-v0.3.md`; the rulings (R-R3); `AGENT.md`; `CHANGELOG.md`.
- **Verification:** 35 new tests, written first and seen failing, including a crash between the commit and the ack, junk, parts, gaps, clock skew, and the real Worker's captured ciphertext; full gate GATE ok=1.
- **Follow-ups:** R4 (operator commands, doctor), R5 (end to end).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp relay R4: the owner's relay commands and doctor (branch `comms-relay`).
- **Summary:** `comms relay` runs locally and only reads.
  - `recipient` prints the public key.
  - `export-pull-key` and `new-path` refuse a terminal and write only to a pipe, with no trailing newline.
  - `status` reports the collector's progress and counts.
  - `setup` prints the ordered checklist.

  Doctor adds `RELAY_UNREACHABLE`, `RELAY_REFUSED`, `RELAY_CLOCK`, `RELAY_STALE` (only while the daemon is trying), `RELAY_BACKLOG_OLD`, `RELAY_GAP` and `RELAY_QUARANTINE`, and none when no relay was ever used. `runtime/doctor.open_read_only` is the one read-only opener.
- **Files changed:** `src/comms/runtime/operator/relay.py` (new), `src/comms/cli.py`, `src/comms/cli_commands/operator.py`, `src/comms/core/doctor.py`, `src/comms/runtime/doctor.py`; tests (`tests/core/test_doctor_relay.py`, `tests/runtime/test_relay_operator.py` new; the operator-group pin); the plan and design (`new-path`); the rulings (R-R4); `AGENT.md`; `CHANGELOG.md`.
- **Verification:** 18 new tests, written first and seen failing; full gate GATE ok=1.
- **Follow-ups:** R5 (the smoke against `wrangler dev`, the runbook, the evidence).

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp relay R5: end to end, the runbook, the evidence (branch `comms-relay`). The relay plan is complete.
- **Summary:** Two new D39-A checks (now 34) run the real selftest daemon against the real Worker under `wrangler dev`:
  - the Worker's secrets come from the daemon's own keys through `comms relay` pipes;
  - a signed and a forged webhook are posted while the daemon is stopped;
  - after start, the signed one is read back once over MCP, the forged one is quarantined, the mailbox drains, and the audit verifies.

  `runtime/selftest_relay.LoopbackRelay` is the selftest's own route from https-loopback to plain HTTP, refusing any other host; only `selftest.py` imports it. The runbook `whatsapp-relay.md` covers deploy, day to day, doctor findings, rotation and a suspect account. The runbook parser checks the command before a pipe. The first full gate caught a flaky Worker boundary test (±301 s across two clocks); the exact boundary is now pinned deterministically. `tests/security/test_relay_exit.py` re-runs R0–R5 from the plan's headings.
- **Files changed:** `src/comms/runtime/selftest_relay.py` (new), `src/comms/runtime/selftest.py`, `scripts/smoke_daemon.py`, `scripts/e2e_smoke.py`, `relay/test/relay.test.ts`, `docs/runbooks/whatsapp-relay.md` (new), `docs/verification/comms-relay.md` (new), the smoke map, the rulings (R-R5), tests (`tests/runtime/test_selftest_relay.py`, `tests/security/test_relay_exit.py` new; egress, runbooks, D39 check count), `CLAUDE.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** full gate GATE ok=1: 5596 passed, 4 skipped; smoke 108/108 (34 against the real daemon); formal 57; WhatsVault 450; relay 15 Vitest tests in workerd.
- **Follow-ups:** owner-run steps: `wrangler login`, the four Worker secrets (`comms relay setup`), `wrangler deploy`, Meta's callback URL, then the live check under D39-B. Merge and push await the owner.

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp relay: merged, pushed and deployed (owner-authorised).
- **Summary:**
  - **Merge:** `comms-relay` merged to `main` (`ea8a7f1`) with tag `comms-relay-v1`, and both pushed.
  - **Host:** the service-account install is not runnable yet: the `comms` binary sits under `~/Desktop`, which other users cannot reach, and there is no launchd job for `comms daemon`. The owner chose to run comms under their own user.
    - State: `~/Library/Application Support/comms/state`; runtime: `…/comms/run`, both 0700.
    - Keys provisioned; cutover COMPLETE; the daemon runs with `relay.url` set.
  - **Worker:** deployed to `https://comms-relay.raoof-r12.workers.dev` on the owner's Cloudflare account. The pull key and recipient went from `comms relay` into a transient 0600 secrets file that was removed at once. The path token and verify token are kept in `…/comms/relay-meta.env` (0600), because they are also typed into Meta.
  - **Live probes:** 404 on unknown paths and on a wrong token, the handshake echoes, a signed pull returns 200, and a forged pull returns 401.
  - **Meta:** W-Vault's callback URL was verified and saved by Meta's own handshake. The subscribed fields are `messages`, `group_lifecycle_update`, `group_participants_update`, `group_settings_update` and `group_status_update`. Meta's dashboard test message reached the relay, encrypted (mailbox depth 1).
- **Files changed:** `AGENT.md` and `CHANGELOG.md` only. Nothing secret is in the repo.
- **Verification:** the probes above, run against production.
- **Follow-ups (owner):**
  - type Meta's app secret with `comms credential set meta-app-secret`; the daemon then collects and verifies the waiting row;
  - publish the W-Vault app, because unpublished apps get only dashboard test webhooks;
  - later, a real service-account install, which means re-piping the two relay keys.

### 2026-09-27 (Australia/Sydney)
**Raouf:**
- **Scope:** W-Vault's public privacy policy on this repository's GitHub Pages (owner-authorised), required before Meta will publish the app.
- **Summary:**
  - **Sources:** written from Meta's 2026 Privacy Policy Expectations (the app's own policy, clearly marked, crawlable, stating what is collected, why, and how to request deletion), the WhatsApp Business Messaging Policy (published policy; data other than message content used only to support messaging; no sharing between customers), and Meta's Cloud API data-privacy page (30-day retention).
  - **Policy content:** it names the operator, what is collected, how it is used, the processors (Meta, Cloudflare with ciphertext only, and Anthropic when the operator asks for AI help), storage and security, retention, deletion steps, rights under the Australian Privacy Act and the GDPR, children, and changes.
  - **Pages:** plain HTML with no script and no tracking; a `.github/workflows/pages.yml` publishes `site/` alone, with actions pinned to commit SHAs; Pages is enabled with the workflow as its source.
  - **The live daemon** moved to `local_port` 8866, because the gate's host probes need 8766 free.
  - **Flaky timeout:** the 2.5 MiB Worker test now has an explicit 30 s budget after one timeout under load.
- **Files changed:** `site/` (new), `.github/workflows/pages.yml` (new), `tests/security/test_public_site.py` (new), `relay/test/relay.test.ts`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** 5 new site tests; the full gate GATE ok=1 (5601 passed; smoke 108; relay 15).
- **Follow-ups:** set the policy URL and the deletion URL in Meta's app settings, then publish W-Vault.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** W-Vault published in Meta (owner-authorised).
- **Summary:**
  - **Pages:** GitHub Pages deployed `site/` through the pinned workflow (run succeeded). `/`, `/privacy/` and `style.css` answer 200 to Meta's crawler user agent.
  - **Settings:** W-Vault's Basic settings now point at `https://raoof128.github.io/telegram-mcp/privacy/`, with deletion instructions at `…/privacy/#deletion`; both persisted after a reload.
  - **Publish:** Meta reported "All required app settings are complete", then "Your app was successfully published".
  - **Use cases:** Threads, Instagram and Messenger stay attached with standard access only; any advanced permission still needs App Review.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the live URL probes, Meta's confirmation, and the settings read back.
- **Follow-ups (owner):**
  - type Meta's app secret with `comms credential set meta-app-secret`, so the daemon verifies and collects what the relay holds;
  - the app's contact email is still the older `titanfall.1380@gmail.com`;
  - the Terms of Service URL is Meta's placeholder `https://www.facebook.com/`.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** Meta's app secret stored in comms; the relay path verified end to end in production (owner-authorised).
- **Summary:**
  - **Secret handling:** after the owner re-entered their Facebook password, the browser wrote the revealed secret straight to a gitignored 0600 file; the script output never entered the transcript. A pseudo-terminal typed it at `comms credential set meta-app-secret`'s `getpass` prompt (version 1, adapters reloaded), and the file was then deleted.
  - **The waiting message:** Meta's dashboard test webhook, held in the relay since 13:28Z, was pulled, decrypted and verified against Meta's real signature, then inboxed, processed and archived (`whatsapp_messages` = 1). The relay was acked and drained to depth 0, with no quarantine and no gap.
  - **Doctor:** `ok` true, with no `CREDENTIAL_UNCONFIRMED` for the app secret (confirmed in operation, R-E6).
- **Files changed:** `AGENT.md`, `CHANGELOG.md`.
- **Verification:** `comms relay status`, `comms doctor`, a signed pull (depth 0), and a read-only count of the inbox and archive.
- **Follow-ups:** a real WhatsApp message to the business number (D39-B live acceptance); the Meta contact email and Terms of Service URL.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** WhatsApp pricing, which number is in use, and group announcements. Research and decisions only; no code.
- **Summary:**
  - **Current number:** the live install uses Meta's test number +1 555 200 6424 (phone number id `1236981939507514`, WABA `2507089659791632`). It can message only verified test recipients, and there are none. The owner's personal number (0402 310 686) is not connected; the owner decided to leave it for now.
  - **Pricing (Meta docs, 2026):**
    - Receiving is free.
    - Until 1 October 2026, replies inside the 24-hour customer service window are free.
    - From 1 October 2026, service messages are charged at the utility rate, after 1,000 free per business number per month. The free tier is stated by partners (360dialog, SendPulse, Wati) and not yet on Meta's own page.
    - Templates the business starts are always charged. Australia is on the "Rest of Asia Pacific" rate card.
  - **Personal number as the business number:** it must first be deleted from WhatsApp (history lost). Coexistence needs the WhatsApp Business app plus a Solution Partner or Tech Provider, drops group sync and keeps 6 months of history. Advised against; a spare number is the clean route.
  - **Groups API limits:** Official Business Account only (30 days on the platform, business verification, approved display name, two-step verification), at most 8 participants, invite-link only, API-created groups only, and each group send uses one unit per delivered recipient. comms can never post into existing phone-app groups or communities.
  - **No messages sent yet:** the live system has sent nothing, because the access token, bot token and Telegram session are not configured.
  - **Recommendation for society announcements:** Telegram groups through comms, and a WhatsApp Community announcement group posted manually.
  - **Sending through WhatsApp Web** in the controlled browser is possible, but WhatsApp's Terms forbid automated or bulk sending and it risks a ban on the owner's number. It is to be done only as occasional one-off sends the owner approves (text and group shown first), never as a comms pipeline or a one-to-one broadcast. Not set up.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`.
- **Verification:** Meta's pricing, non-template pricing, Groups API, Official Business Account and registration pages, read 2026-09-28.
- **Follow-ups (owner):** a spare number for production; the Telegram bot token or session for announcements; the Meta contact email and Terms of Service URL.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** Telegram set up on the live install: the bot and the owner's user account (owner-authorised; the owner logged into Telegram Web in the controlled browser).
- **Summary:**
  - **Bot:** @raouf_comms_bot ("Raouf Comms") was created through the verified @BotFather (id 93372553; an impostor "BotFather", 7836447530, was avoided). Its token went browser → 0600 file → a pty at `comms credential set telegram-bot-token` (version 1, proved live, reloaded) → deleted. The token never entered the transcript.
  - **User account:**
    - A my.telegram.org app, "Raouf Comms", api_id 35628079 (not secret), was created.
    - Its `api_hash` went browser → file → `security -i` on stdin (never in argv) into the login Keychain as `telegram-mcp`/`api_hash`, and `read_api_hash()` reads it back.
    - `telegram_api_id` was set in `comms.json` and the daemon restarted.
    - `comms transport telegram login` ran with the phone and the code read from Telegram's service chat (777000). Two-step verification is off on the account. The result is `authorized: true`, account ref `tga_…`, and the session is `state/telegram/primary.session` (0600).
  - **The first login attempt** got `MALFORMED_REQUEST` because it hit the daemon before its background Telegram reconnect had finished ("Telegram unreachable at start"). A bare Telethon connect took 4.8 s. A retry worked.
  - **MCP client:** `claude-code` was added (`cli_algtfvgpaq53qhy4ntohhapzfv`, seed at `~/.config/comms/claude-code.seed`, 0600).
  - **Account profile over HTTP `/mcp`:** `telegram_bot` and `telegram_user` are configured and reachable; `whatsapp_cloud` is not configured (no access token).
- **Defects found:**
  1. `comms doctor` always reports `CREDENTIAL_NOT_CONFIGURED telegram-session`: the session is created by `transport telegram login`, not the credential store, but doctor checks the store (false finding; `ok` is still true).
  2. The login CLI prints only the error code and drops the message ("telegram refused the step: …"), which hid the real cause.
  3. The first login step right after a daemon start fails while Telegram is still connecting, instead of waiting or answering with a clear code.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`. No code.
- **Verification:** `auth status` shows authorized; `comms doctor` is ok; `comms_account_profile` shows both Telegram actors reachable.
- **Follow-ups:**
  - fix the three defects above (gated);
  - log Telegram Web and my.telegram.org out of the controlled browser if they are not wanted there;
  - add the bot to society groups for announcements;
  - set up WhatsApp's `meta-access-token` when production WhatsApp sending is wanted.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** Fix the Telegram defects found while setting Telegram up live: three reported, one found underneath them (branch `telegram-fixes`, ruling R-TG1).
- **Summary:**
  1. **Guard:** Telethon's own requests (`UPDATE_RPCS`: `connect` on a logged-in session sends `users.GetUsers`, `updates.GetState`, `updates.GetDifference`; the update loop adds difference requests) were reviewed but never admitted by the guard, so every start reported "Telegram unreachable". The one guard, `_admitted`, now allows only an operation's own requests inside it and only `UPDATE_RPCS` outside every operation. A first attempt, wrapping `connect()` in an operation, was rejected: the update-loop task inherits that context.
  2. **Bot poller:** the 25 s long poll ran under a 10 s client timeout, so the bot received nothing, and it froze the daemon's event loop about 10 s in every 16. `getUpdates` now gets its own read timeout (the poll plus 10 s); `poll_once_async` waits in a thread while the offset read and every write stay on the loop thread; `Workers` await an awaitable step.
  3. **Doctor:** it judges `telegram-session` by the session file (`SESSION_FILE`, one copy), not the credential store.
  4. **CLI:** it prints `CODE: reason` for every refusal (login and operator commands).
- **Files changed:** `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/transports/telegram/bot/{http,updates}.py`, `src/comms/runtime/{workers,doctor}.py`, `src/comms/core/doctor.py`, `src/comms/cli.py`; tests (`tests/unit/test_telethon_session.py`, `tests/transports/telegram_bot/test_updates.py`, `tests/runtime/test_workers.py`, `tests/core/test_doctor.py`, `tests/runtime/operator/test_doctor_cli.py`, `tests/cli/test_cli_operator.py`); the rulings (R-TG1); `AGENT.md`; `CHANGELOG.md`.
- **Verification:**
  - 11 new tests, written first and seen failing.
  - Full gate GATE ok=1 (5611 passed; smoke 108/108; formal 57; WhatsVault 450; relay 15).
  - Live checks:
    - the real session starts ready in both update modes (3.0 s and 2.8 s);
    - the daemon log no longer says "unreachable at start";
    - admin requests are answered steadily, about every 2 s, with no 10 s stalls;
    - doctor no longer reports `telegram-session`;
    - a `/start` sent to @raouf_comms_bot from the owner's account was retained within seconds (1 update, offset advanced).
- **Follow-ups:** the owner confirms the new "raoufcomms" login in Telegram ("Yes, it's me"); other worker steps (relay pull, delivery) still make short synchronous calls on the loop, bounded by their timeouts.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** First live message sent through the comms MCP: to the owner's Telegram Saved Messages (owner-requested test).
- **Summary:** Over HTTP `/mcp` with the `claude-code` client:
  - `comms_location_create` made "Personal" (`loc_ah2k…`).
  - `comms_directory_destination_create` added the private chat 70267295 ("Saved Messages", `dst_al7w…`); private chats get no `grp_`.
  - A one-destination campaign ran: `create`, `set_content`, `set_targets {destinations}`, `validate`, `preview` (1 recipient), `send`. It finished COMPLETE/SENT, with the job ACCEPTED on the first attempt, and the text appeared in Saved Messages at 07:57.

  Only the user account can post to Saved Messages, so `telegram_delivery_actor` was set to `telegram_user` for this test and restored to the bot default afterwards (two daemon restarts).
- **Findings:**
  - The catalog has no direct "send to one person" tool: `comms_message_send` takes only a `grp_`, so a DM goes through a campaign.
  - The campaign's Telegram actor is one install-wide setting, not per campaign.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`.
- **Verification:** `comms_campaign_status` and `delivery_report`, and the message read back in Telegram Web.
- **Follow-ups:** consider a person-addressed send (or a per-campaign actor) if one-off DMs through the MCP are wanted.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** The owner's Friends group message, and the defect it exposed (branch `telegram-creator-rights`, ruling R-TG2).
- **Summary:**
  - **The message:** the owner asked for a cute Persian "good morning, please confirm numbers for Cafe Cat on Sunday so I can call and book" in their Friends group. The MCP send was refused (`CAPABILITY_UNAVAILABLE`), so the message was sent from the owner's own Telegram Web session (read back at 08:04). Nothing was sent twice.
  - **Causes:**
    - I first entered Telegram Web's id (`-4331185481`); comms wants `-1004331185481`. That destination is disabled and the correct one added.
    - v0.3 has no dialog discovery, so the session's entity cache was empty. It was filled once through the adapter's reviewed `admin.discover` read, with the daemon stopped.
    - **The defect:** Telegram's `getParticipant` answer for the creator omitted the channel from `chats`, and comms read that as not authorized for every right. `self_rights` now makes one `messages.getPeerDialogs` read (already reviewed; added to `cap.member.get` and to the review document) when the channel is missing; `channels.getChannels` stays absent.
- **Files changed:** `src/comms/transports/telegram/telegram/telethon_adapter.py`, `docs/verification/telegram-rpc-review.md`, `tests/transports/telegram_user/test_self_rights.py`, the rulings (R-TG2), `AGENT.md`, `CHANGELOG.md`.
- **Verification:**
  - 4 new tests (2 seen failing first).
  - Full gate GATE ok=1 (5615 passed; smoke 108).
  - Live: Friends reads as megagroup/creator, and over MCP `telegram_user` has `message.send`, `message.pin` and `admin.promote` AVAILABLE.
- **Follow-ups:**
  - dialog discovery for v0.3 (the entity cache fills only from updates);
  - `scan_dialogs`' `_views` raises on an unknown entity type;
  - a person-addressed send tool.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** A live end-to-end run of every Telegram tool that can address the owner's Saved Messages, and the defects it found (branch `telegram-e2e-fixes`, ruling R-TG3).
- **Summary:**
  - **Coverage:** 49 tools were driven over HTTP `/mcp` as the owner's account: account and status, directory, locations, audiences, campaigns (sent, scheduled then unscheduled then rescheduled, cancelled, retry, resolve), context read-back and paging, mark-read, and media stage, upload, inspect, download and delete. 63 of 65 checks passed on the first run.
  - **Not coverable here:** the 62 group-addressed tools cannot address a private chat.
  - **Defects found and fixed:**
    1. `comms_account_status` and `comms_telegram_bot_status` answered INTERNAL_ERROR, because the bot's snapshot ran `int("account")`. The account-level identity now has one home (`ACCOUNT_TARGET`), and the bot answers it from `getMe`.
    2. Every photo the user account uploaded was named `file`, and Telegram refused it (`PHOTO_EXT_INVALID`); the upload reported OUTCOME_UNKNOWN, and staged photo sends and group photos shared the same helper. Uploads are now named by type (`file.jpg`, `file.png`), and upload refusals are FAILED with their code.
  - **Not a defect:** a freshly uploaded file answers download with NOT_FOUND by design, since Telegram downloads read a message's media (A47).
  - **A side effect of the first run:** its cleanup step opted out the owner's own Telegram identity as a contact. Opt-outs are permanent by design and no tool reverses one, so campaigns can no longer address the owner as a person; the Saved Messages destination still works.
- **Files changed:** `src/comms/transports/telegram/{capabilities,bot/capability,user/capability,telegram/telethon_adapter}.py`; tests (`tests/transports/telegram_bot/test_capability.py`, `tests/transports/test_telegram_upload.py`, `tests/runtime/test_media_staged.py`); the rulings (R-TG3); `AGENT.md`; `CHANGELOG.md`.
- **Verification:**
  - 8 new tests, seen failing first.
  - Full gate GATE ok=1 (5622 passed; smoke 108/108; formal 57; WhatsVault 450; relay 15).
  - Live: both status tools answer, a photo upload returns SUCCEEDED with a `med_`, inspect works, and download and delete give their documented refusals.
- **Follow-ups:**
  - a throwaway private group to cover the 62 group tools live;
  - decide whether the owner may reverse an opt-out;
  - dialog discovery;
  - a person-addressed send tool.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** A live end-to-end run of every Telegram group tool in a throwaway private supergroup, and the defects it found (branch `telegram-group-e2e-fixes`, ruling R-TG4).
- **Summary:**
  - **The run:** the owner's account created "comms e2e test" (a forum), added @raouf_comms_bot, restricted and unrestricted it, promoted it, updated its rights and tagged it. Then 83 calls covered 68 distinct tools as both actors: send, reply, edit, pin, forward, delete; photo and document sends (the R-TG3 fix held); reads, search, summary, media inspect and download; permissions, title, description and photo; invites and join requests; topics; demote, remove, ban, unban; migrate (refused, since only a basic group migrates); a broadcast channel created, posted to and deleted; then the group deleted. 78 passed first time, and two apparent failures were the test's own wrong expectations.
  - **Defects fixed:**
    1. `comms_group_permissions_get` answered NOT_AUTHORIZED: `default_permissions` still expected the channel in `getParticipant` (R-TG2's defect in a second function). One helper, `_channel_chats`, now serves both.
    2. `comms_context_thread` was unsupported for the user account although the actor matrix serves it by `messages.getReplies`; the user context now reads threads through `fetch_replies`.
    3. A too-small group photo (`PHOTO_CROP_SIZE_SMALL`) was reported OUTCOME_UNKNOWN; documented chat-photo refusals are now FAILED INVALID_ARGUMENT.
  - **Rate limit:** after the morning's burst of group creation, photos and deletes, Telegram rate-limited the account for a while. comms answered RATE_LIMITED correctly, and the probe group's delete succeeded on retry an hour later.
- **Files changed:** `src/comms/transports/telegram/telegram/telethon_adapter.py`, `src/comms/transports/telegram/user/context.py`; tests (`tests/transports/telegram_user/test_reads_g6.py`, `tests/transports/telegram_user/test_context.py`, `tests/runtime/test_media_staged.py`); the rulings (R-TG4); `AGENT.md`; `CHANGELOG.md`.
- **Verification:**
  - 6 new tests, seen failing first.
  - Full gate GATE ok=1 (5628 passed; smoke 108/108).
  - Live on the new code: `permissions_get` answers; `context_thread` returns the reply; a 96 px photo is FAILED INVALID_ARGUMENT, a 512 px photo SUCCEEDED; the probe group was deleted. No test group remains.
- **Follow-ups:**
  - a RATE_LIMITED write result carries no retry-after in its MCP output;
  - the daemon exited between sessions and needs a keep-alive (launchd) under the owner user;
  - dialog discovery;
  - a person-addressed send;
  - owner-reversible opt-out.

### 2026-09-28 (Australia/Sydney)
**Raouf:**
- **Scope:** A repository-wide documentation freshness audit: every document checked against the code, with the defects it exposed fixed (branch `docs-freshness-audit`, ruling R-DOC1). The logs and Zurvan were brought up to date first.
- **Summary:**
  - **Inventory:** 80 documents outside WhatsVault, plus its 34.
    - **Kept as dated records:** 29 plans and specs, the provenance files, the phase evidence and AGENT.md and CHANGELOG.md.
    - **Left frozen:** the hash-pinned v0.3 spec and design, and the frozen v0.1.10 specification.
  - **Two code defects found by reading the docs against the code:**
    1. `comms mcp --stdio` defaulted to the daemon at port 8765, while the daemon listens on `local_port`, default 8766. A client set up by the client runbooks (no `--daemon`) would have reached nothing. Every test passed `--daemon`, so the default was never exercised. Both parsers now use one `DEFAULT_DAEMON`, pinned equal to the runtime's `HOST` and `LOCAL_PORT`.
    2. Bare `comms --help` printed the legacy `telegram-mcp` usage. It now prints the comms usage and names the verbs still forwarded to the legacy CLI.
  - **Stale documents repaired:**
    - `README.md` described the Phase 3 synthetic demo and was rewritten.
    - `CLAUDE.md`: "nothing has touched Telegram", the relay "still to deploy", "no runtime provisioned", the WhatsVault "nothing edited" rule, and the test count.
    - The client runbooks (130 tools, not 109; the proxy flags for a non-default install).
    - `install.md` never said the user login needs `telegram_api_id` in `comms.json` and the `api_hash` in the Keychain.
    - The relay runbook lacked Meta's webhook-field subscription and `CLOUDFLARE_ACCOUNT_ID`.
    - `comms-v0.3.md`: three superseded statements annotated, and a live-operation section added.
    - `comms-relay.md` now records the deployment.
    - `formal/README.md` gains the missing campaign model.
    - The Telegram RPC review named the pre-5b-1 adapter path.
    - Ruling R-E2 cited a test file that never existed.
    - WhatsVault's provenance and README.
    - `dependencies.md`: `httpx` is now a runtime dependency, and the relay's npm pins are listed.
    - Four plan and spec status lines that still read "draft" or "pending".
    - The package description.
- **Files changed:**
  - `src/comms/cli.py`, `src/comms/mcp/stdio_proxy.py`, `pyproject.toml`;
  - `README.md`, `CLAUDE.md`, `formal/README.md`;
  - `docs/runbooks/{install,clients-claude-code,clients-codex,clients-chatgpt,whatsapp-relay,live-acceptance-whatsapp}.md`;
  - `docs/verification/{comms-v0.3,comms-relay,comms-v0.3-rulings,dependencies,telegram-rpc-review}.md`;
  - `docs/provenance/whatsvault.md`, `docs/comms-spec-v0.2.md`, and three `docs/superpowers/` status lines;
  - `transports/whatsapp/README.md` (under R-DOC1);
  - the tests `tests/mcp/test_stdio_proxy.py`, `tests/cli/test_cli_operator.py`, `tests/integration/test_comms_entry_points.py` and `tests/integration/test_whatsvault_provenance.py`;
  - `AGENT.md`, `CHANGELOG.md`.
- **Verification:**
  - New tests seen failing first.
  - The documented client configuration was driven against the live daemon: 130 tools listed, and a call answered.
  - Every path the current docs name was checked to exist.
  - Full gate GATE ok=1: 5632 passed, 4 skipped; smoke 108/108; formal 57; ruff, format, mypy and build clean; WhatsVault 450; relay 15.
- **Follow-ups:**
  - no Markdown linter or link checker is installed, so none was run;
  - the P §88 acceptance rows stay PENDING OWNER until the runbooks' records are filled in;
  - the service-account install is still not done, and nothing keeps the daemon running.

### 2026-10-04 (Australia/Sydney)
**Raouf:**
- **Scope:** Proposed amendment A49, Instagram as a comms actor: `docs/instagram-spec-v0.6.md` (branch `comms-instagram-spec`). A documentation change only; no code, no catalog, no pin touched.
- **Summary:**
  - The TypeScript `Instagram MCP Server` spec v0.5 (repository `Raoof128/Instagram-MCP`) was gauntleted line by line against the current Meta, MCP, Claude Code and `@napi-rs/keyring` sources (its `GAUNTLET-v0.5.md`): 7 corrections, 28 tightenings, four gates closed or narrowed.
  - It is rewritten here as a Python proposal that fits comms instead of a second server: one actor `instagram` (`{capability, admin, context}`), 23 `comms_instagram_*` tools, publish as a durable saga (A41) ending `IN_FLIGHT` for a processing Reel, tokens in staged secret slots `meta-ig-access-token/<alias>` (A13), `iga_`/`igm_`/`igc_` refs, a second pinned Graph origin `https://graph.instagram.com` (amendment to A26), and a `requires_user_interaction` catalog flag emitted as `_meta` for the public-posting tools (D5 stands: host UX only).
  - Carried corrections: latest Graph API is v26.0; dashboard tokens are long-lived by doc (no app-secret exchange); `follows`, `profile_visits`, `profile_activity` are Feed and Story only; `caption` is documented Facebook-Login-only; `timeframe` is `this_week` or `this_month`; the Bearer header is undocumented on `graph.instagram.com` (gate GI-1, no token-in-URL fallback under A26).
  - Dropped from v0.5: the confirm-token ceremony, the OS keychain store, the in-process active account, the HEAD preflight of model-supplied URLs, env flags.
- **Files changed:** `docs/instagram-spec-v0.6.md` (new); `AGENT.md`; `CHANGELOG.md`.
- **Verification:**
  - `uv sync --locked`; `uv run pytest tests/security/test_runbooks.py tests/security/test_v03_preflight.py tests/security/test_supersession.py -q`: 69 passed. The v0.3 spec pin is untouched.
  - The full gate was not run: no source file changed.
- **Follow-ups:**
  - adoption ruling R-IG0 (append A49 to `docs/comms-spec-v0.3.md`, re-pin);
  - open question 3 (an advisory `preview_digest` on the publish tools) needs an owner decision before MI-3;
  - GI-1 (Bearer on `graph.instagram.com`) decides whether MI-1 can proceed inside A26.


### 2026-10-04 (Australia/Sydney), later
**Raouf:**
- **Scope:** Revision 2 of the Instagram proposal (A49) and its implementation plan, on branch `comms-instagram-spec`. Documentation only; no source, pin or catalog touched.
- **Summary:**
  - The v0.6 gauntlet (`GAUNTLET-v0.6.md` in `Raoof128/Instagram-MCP`, `85cf0b1`) found that revision 1 described executor behaviour comms does not have (`IN_FLIGHT` as a caller-visible result, resume by `op_ref`, step records carrying a provider ref) and left 14 implied code changes unstated.
  - Revision 2 of `docs/instagram-spec-v0.6.md` re-cuts publishing as three single-effect CREATE tools (`container_create`, `carousel_create`, `publish`) on a durable `igk_` ledger row, so no executor, recovery, relay or proxy change is needed and every call fits the proxy's 30 s forward timeout (D-I13). It drops `IN_FLIGHT` and the resume tool (22 tools, 14 reads and 8 writes), makes the error table step-scoped (no CREATE is ever retried by comms), lists every required code change with the pin it moves (section 14), and fixes the wording the gauntlet marked wrong: `test_egress.py` is an httpx-import allowlist, `smoke_sweep.py` is the catalog sweep, the alias grammar excludes the `_no_secrets` substrings, the refresh call's query-string token is named in GI-1, `mcp/http.py` must pass `meta=`.
  - New plan `docs/superpowers/plans/2026-10-04-comms-instagram.md`: tasks IG-0 to IG-6 for the agent (test-first, one pin regeneration per task, named tests per review focus), IG-7 for the owner (tokens, live gates GI-1 to GI-8, ruling R-IG0), and an agent brief.
- **Files changed:** `docs/instagram-spec-v0.6.md`; `docs/superpowers/plans/2026-10-04-comms-instagram.md` (new); `AGENT.md`; `CHANGELOG.md`.
- **Verification:**
  - `uv run pytest tests/security/test_runbooks.py tests/security/test_v03_preflight.py tests/security/test_supersession.py tests/core/providers/test_protocols.py -q`: green. The v0.3 spec pin is untouched.
  - `mcp` 2.2.0 driven live over stdio with the proxy's `Server` construction: legacy `initialize`, modern `server/discover` and bare modern `tools/list` served; tool `_meta` survived `ListToolsResult.model_validate` (gauntlet v0.6, section A).
  - The full gate was not run: no source file changed.
- **Follow-ups:**
  - IG-0 pins this revision and copies the gauntlet record into `docs/verification/`;
  - GI-1 (Bearer on `graph.instagram.com`, including `/refresh_access_token`) is the first live step and can stop MI-1 for a ruling;
  - open questions 1 to 4 in the spec need owner answers before MI-3.


### 2026-10-04 (Australia/Sydney), IG-0
**Raouf:**
- **Scope:** Plan `2026-10-04-comms-instagram.md` task IG-0: pre-flight for proposed A49 (Instagram). No production code.
- **Summary:**
  - Baseline gate on `6e51350` (this host: Linux, running as root, no IPv6): pytest 5623 passed, 6 skipped, 7 failed; smoke 106 of 108; formal, ruff, format, mypy, build, WhatsVault and the relay all pass. The 7 pytest failures (`test_install.py` x4, `test_v03_part_b_exit.py`, `test_audit_handlers.py` anchor repair, `test_doctor.py` off-probe) and the 2 smoke failures (`doctor headless`: IPv6 unavailable; `install plans are inert`) are host artefacts and form the reference set later gates must not grow.
  - Ruling R-IG1: execution in a development worktree (branch `ig-work`), gating each task commit in the main checkout before `comms-instagram-spec` moves; the Instagram spec joins the pins `test_v03_preflight.py` enforces.
  - Ruling R-IG2: Instagram keeps its own three tables and an `igp_` ref for a DM counterpart (no `rcp_`/`cmg_` reuse, so no transport CHECK changes); Instagram reads are their own tools paging through `cur_`; `--exchange` deferred; the token is typed at the hidden prompt. Spec and plan amended and pinned.
  - The v0.6 gauntlet record is copied to `docs/verification/instagram-gauntlet-v0.6.md`.
- **Files changed:** `docs/instagram-spec-v0.6.md`, `docs/superpowers/plans/2026-10-04-comms-instagram.md`, `docs/verification/comms-v0.3-rulings.md`, `docs/verification/instagram-gauntlet-v0.6.md` (new), `tests/security/test_v03_preflight.py`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** `tests/security/test_v03_preflight.py` passes, and fails when the Instagram spec drifts from its pin (seen failing). Doc tests green.
- **Follow-ups:** IG-1 (the actor exists).


### 2026-10-04 (Australia/Sydney), IG-1
**Raouf:**
- **Scope:** Plan task IG-1, proposed A49: the Instagram actor exists (enums, settings, purposes, schema v10, the pinned client, accounts and their operator commands). No MCP tool yet.
- **Summary:**
  - **Core:** 14 Instagram `Capability` members; `SUPPORT` gives them to `instagram` alone and adds it to `history.read` and `message.reply`; `SEMANTICS` (reads `READ`; container, carousel, publish and comment reply `CREATE`; hide and toggle `SET_STATE`; comment delete `DESTRUCTIVE_NONIDEMPOTENT`; the DM reply `MESSAGE_SEND` with no key); `ADAPTER_CONTRACTS["instagram"]`; refs `iga_`, `igk_`, `igm_`, `igc_`, `igp_`; the typed audit payload accepts actor `instagram` and a new `admin.instagram_account` event; `IDENTITY_MISMATCH` and `NOT_ENOUGH_DATA` join the error model.
  - **Secrets:** `purpose_of` resolves `meta-ig-access-token.<alias>` (staged, opaque) beside the static purposes; the secret store, credential rotation, key ids and credential audit events use it. An alias never contains a word comms.json refuses as secret-like.
  - **Schema v10:** `instagram_accounts`, `instagram_containers`, `instagram_objects`, with immutable bindings and one live row per alias and per user id; no existing table changes (R-IG2).
  - **Transport package:** `GraphIgApi` (pinned `https://graph.instagram.com`, the token only in the Authorization header, closed nodes and edges, no `access_token` parameter ever), `config` (the comms.json section), `store`, `accounts` (lazy `/me` identity check, a mismatch blocks the alias), `capability` (per-account ceilings), `doctor`.
  - **Operator:** `comms transport instagram account add|list|remove`, `token refresh`, `doctor` (R-IG3: under `transport`), through the staged rotation with a `/me` proof; a refresh persists the token Meta returns; per-alias proofs guard `credential rotate meta-ig-access-token.<alias>`.
  - **Catalog:** `ACTOR` and the capability-list transport gain `instagram`; the pin regenerates (`57e490cc1f538286…` to `21cc382adb9370a7…`); `PENDING_A49` names each capability whose tool a later task builds.
- **Files changed:** `src/comms/core/{audit/specs,credentials,errors,keys/purposes,keys/secrets,keys/slots,providers/capability,providers/protocols,providers/semantics,refs,storage/migrations}.py`; `src/comms/mcp/{catalog,schemas}.py`; `src/comms/runtime/{adapters,assemble,facades,proofs,settings}.py`, `runtime/operator/{__init__,context,credentials,instagram}.py`; `src/comms/cli_commands/operator.py`; `src/comms/transports/instagram/` (new); tests under `tests/transports/instagram/`, `tests/runtime/operator/test_instagram_accounts.py`, and the pinning tests that moved (`test_protocols`, `test_semantics`, `test_refs_*`, `test_errors`, `test_egress`, `test_catalog_pin`, `test_relay_collector`); docs (spec, plan, rulings R-IG3 and pins).
- **Verification:** new tests seen failing first; IG-1 targeted run 275 passed; the parallel sweep of the rest of the suite showed only the baseline set; full gate in the main checkout on this commit (see the ledger line).
- **Follow-ups:** IG-2 (the read tools).


### 2026-10-04 (Australia/Sydney), IG-2
**Raouf:**
- **Scope:** Plan task IG-2, proposed A49: the twelve Instagram read tools, end to end.
- **Summary:**
  - **Tools (142 in the catalog):** `comms_instagram_account_list`, `whoami`, `profile_get`, `media_list`, `media_get`, `media_insights`, `account_insights`, `comment_list`, `comment_replies`, `tag_list`, `conversation_list`, `conversation_messages`. Every id is an opaque ref (`igm_`, `igc_`, `igp_`); captions, comments and DM text only in `untrusted_text`; usernames and labels only under `untrusted`; Meta paging cursors become client-bound `cur_` tokens bound to the tool, its arguments, the account and the client.
  - **Service:** `InstagramService` in `src/comms/runtime/instagram.py` (R-IG4); each read resolves the account, checks its identity once per daemon lifetime, checks the capability, calls Meta, and maps a refusal to a fixed code (`classify.read_refusal`).
  - **Insights:** the tables move to `core/providers/instagram_insights.py` (R-IG4); validation per section 7, one metric group per call; Feed-only metrics refused for a video; `crossposted_views`, `facebook_views` and `engagement` never requested; code 10 is `NOT_ENOUGH_DATA`.
  - **DMs:** conversations name each counterpart by `igp_`; message details are read sequentially at 2 per second, at most 20.
  - **Settings:** `instagram.caption` (false by default) turns captions on after gate GI-4.
  - **Wiring:** `Services.instagram`, the facades, the egress classes, identity inspection for every Instagram ref, the actor matrix (its own table; header-aware parser), `PENDING_A49` down to IG-3 and IG-4.
- **Files changed:** `src/comms/runtime/{instagram,comms_runtime,facades}.py`; `src/comms/core/{identities,providers/instagram_insights}.py`; `src/comms/mcp/{egress,tools/__init__,tools/account,tools/instagram}.py`; `src/comms/transports/instagram/{config,classify,insights,media,comments,messages}.py`; `docs/verification/comms-v0.3-actor-matrix.md`; tests (`tests/runtime/test_instagram_reads.py`, `tests/transports/instagram/world.py`, the matrix parser and behaviour test, `test_catalog_pin.py`, the config test); spec, plan, rulings R-IG4 and pins; the catalog pin (`c6eb7dee1cd3eb70…`).
- **Verification:** new tests seen failing first; 68 Instagram tests pass, including one through the real dispatcher; MCP, egress sweep, host permissions, AI boundary, layering, facades and matrix behaviour suites pass; ruff, format, mypy clean; full gate on the commit in the main checkout (ledger line).
- **Follow-ups:** IG-3 (comment and DM writes).


### 2026-10-04 (Australia/Sydney), IG-3
**Raouf:**
- **Scope:** Plan task IG-3, proposed A49: the explicit outcome table, comment moderation and DM replies through the real mutation executor.
- **Summary:**
  - **Tools (147 in the catalog):** `comms_instagram_comment_reply` (CREATE; records the reply's `igc_`), `comment_hide`, `comments_enabled_set`, `comment_delete` and `message_send`. Each needs `account` (no default for a write), a `request_id`, the account's identity check, the capability (the `comms.json` ceiling: `writes`, or `dms` for a DM) and one Graph call, classified by `IG_CODES`. All five are in the ask list and the egress classes.
  - **Classifier:** `transports/instagram/classify.py` holds section 8's table; an undocumented pair, a 5xx, a non-JSON body or an ambiguous transport error is `OUTCOME_UNKNOWN`, never retried; a connection never made is `PROVIDER_UNAVAILABLE`.
  - **Adapter:** `InstagramAdmin` resolves each ref inside the target account (another account's ref is `NOT_FOUND` and sends nothing); `register()` lets IG-4's publishing join the same adapter.
  - **DMs:** a pre-check reads the newest messages; a closed 24-hour window is `WINDOW_CLOSED` with nothing sent or recorded; `dm_disclosure` is appended; at most 1000 UTF-8 bytes.
  - **Conformance:** `ADAPTER_CONTRACTS["instagram"]` now grows with the code (R-IG3 (8)): `capability` cases in IG-1, `context` in IG-2, `admin` here. The IG-1 and IG-2 commits were amended before landing, after the IG-1 gate found the gap.
  - **Ruling R-IG5:** the reply argument is `text`; DM message ids are base64url; the catalog pin is regenerated (`c6eb7dee1cd3eb70…` to `afe1a371d3e0aa65…`).
- **Files changed:** `src/comms/transports/instagram/{admin,classify}.py`; `src/comms/runtime/{instagram,adapters,facades}.py`; `src/comms/mcp/{egress,tools/instagram}.py`; `src/comms/core/providers/protocols.py`; `.claude/settings.json`; `docs/verification/comms-v0.3-{actor-matrix,rulings}.md`; tests (`tests/runtime/test_instagram_writes.py`, `tests/transports/instagram/test_classify.py`, `tests/conformance/instagram.py`, `test_protocols.py`, `test_catalog_pin.py`, the catalog pin).
- **Verification:** new tests seen failing first; 162 Instagram tests pass, including crash at every executor point, replay, cross-account refs and the injected-comment case; MCP, conformance, egress sweep, host permissions, AI boundary, layering, facades, ambiguity and matrix suites pass; ruff, format, mypy clean; full gate on the commit in the main checkout (ledger line).
- **Follow-ups:** IG-4 (publishing).


### 2026-10-04 (Australia/Sydney), IG-4
**Raouf:**
- **Scope:** Plan task IG-4, proposed A49: publishing on the durable `igk_` container ledger.
- **Summary:**
  - **Tools (152 in the catalog):** `comms_instagram_publish_quota` and `publish_preview` (reads); `container_create`, `carousel_create` and `publish` (CREATE writes, each one `request_id` and one provider effect, all three in the ask list and the egress classes). The catalog now follows section 5's order.
  - **Ledger:** every container Meta makes is an `igk_` row the moment Meta answers, so the 400-per-24-hours budget never undercounts, even across a crash. A full ledger is `FAILED CONTAINER_BUDGET`; a full live post quota is `FAILED PUBLISH_CAP`; both answer before Meta with nothing recorded.
  - **Publish:** one status read, then `media_publish`. `IN_PROGRESS`, `ERROR` and `EXPIRED` answer `CONTAINER_NOT_READY`, `CONTAINER_FAILED` and `CONTAINER_EXPIRED`; a container the ledger knows as published answers `SUCCEEDED` with its `igm_` and makes no call; one Meta reports published but comms never named is `OUTCOME_UNKNOWN` (A19). Nothing polls (D-I13).
  - **URLs:** `transports/instagram/urls.py` passes only `https` URLs to a public DNS name (no userinfo, IP literal in any spelling, `localhost` or private-use name, port but 443, whitespace; at most 2,048 characters). comms never fetches them.
  - **Preview:** read-only; reports kind, caption counts, policy, the ledger, the live quota and the refusal a create would answer, with an advisory `preview_digest` that the creates may echo (open question 3, built as proposed; the owner may drop it).
  - **Replay fix:** a replayed `request_id` now skips every pre-check and answers its record (A28). IG-3's `message_send` re-checked the DM window on replay and could answer `WINDOW_CLOSED` for a DM already sent; a test now covers it.
  - **Ruling R-IG6:** the points above; the catalog pin is regenerated (`afe1a371d3e0aa65…` to `de8c9897d107510b…`); `PENDING_A49` is empty.
- **Files changed:** `src/comms/transports/instagram/{urls,publish,admin}.py`; `src/comms/runtime/{instagram,adapters,comms_runtime,facades}.py`; `src/comms/mcp/{egress,tools/instagram}.py`; `.claude/settings.json`; `docs/verification/comms-v0.3-{actor-matrix,rulings}.md`; tests (`tests/runtime/test_instagram_publish.py`, `tests/transports/instagram/{test_urls,test_publish_ledger,world}.py`, `tests/runtime/test_instagram_writes.py`, `test_catalog_pin.py`, the catalog pin).
- **Verification:** new tests seen failing first, including the replay flaw against the unfixed service; 241 Instagram tests pass, including every crash point, replay, the budget, the quota and cross-account children; MCP, conformance, egress, host permissions, AI boundary, layering, wire-size, runtime, ambiguity and matrix suites pass (1427); ruff, format, mypy clean; full gate on the commit in the main checkout (ledger line).
- **Follow-ups:** IG-5 (`requires_user_interaction` through the daemon).


### 2026-10-04 (Australia/Sydney), IG-5
**Raouf:**
- **Scope:** Plan task IG-5, proposed A49: `requires_user_interaction` from the catalog through the daemon and the stdio proxy.
- **Summary:**
  - **Flag:** `ToolSpec.requires_user_interaction` (false by default); `write(..., requires_user_interaction=)`; set on `comms_instagram_publish`, `comment_reply`, `comment_delete` and `message_send`. Claude Code then prompts on every call to them, in every permission mode (D-I3); all four stay in the ask list too.
  - **Wire:** `_entry` emits `"_meta": {"anthropic/requiresUserInteraction": true}` only for a flagged tool, so no other entry or digest changes; `mcp/http.py` `_tools()` passes it to `types.Tool`, which the daemon builds field by field; the stdio proxy's `ListToolsResult.model_validate` keeps it.
  - **Ruling R-IG7:** the alias spelling `_meta=` (mypy); the structural `tools/list` test allows `_meta` on a flagged tool only; the pin is regenerated (`de8c9897d107510b…` to `e8d5da8e115a14a6…`, four digests).
- **Files changed:** `src/comms/mcp/{spec,catalog,http,schemas,tools/instagram}.py`; `docs/verification/comms-v0.3-rulings.md`; tests (`tests/mcp/test_catalog_meta.py`, `test_stdio_proxy.py`, `test_catalog_pin.py`, the catalog pin).
- **Verification:** the four new tests seen failing first; MCP, host permissions, AI boundary, wire-size and publishing suites pass (903); ruff, format, mypy clean; full gate on the commit in the main checkout (ledger line).
- **Follow-ups:** IG-6 (doctor, smoke sweep, runbooks, exit test, CLAUDE.md).


### 2026-10-04 (Australia/Sydney), IG-6
**Raouf:**
- **Scope:** Plan task IG-6, proposed A49: the doctor, the smoke, the runbooks, the exit test and `CLAUDE.md`. The implementation of A49 is complete; adoption waits for the owner's steps (plan IG-7, ruling R-IG0).
- **Summary:**
  - **Doctor:** `comms doctor` now checks each Instagram account offline against `comms.json` and its token metadata (`IG_ACCOUNT_UNREGISTERED`, `IG_ACCOUNT_UNCONFIGURED`, `IG_TOKEN_MISSING`, `IG_TOKEN_EXPIRED`, `IG_TOKEN_EXPIRING` as a warning); a `comms.json` that does not load is `SETTINGS_INVALID`. The identity check stays with `comms transport instagram doctor`.
  - **Smoke:** a new check proves the prompt flag survives the real stdio proxy (109 checks). The daemon sweep expects `NOT_CONFIGURED` from every Instagram tool on the selftest daemon (fixed in the IG-2 commit, R-IG4 (6), after the plan's ordering would have failed IG-2 to IG-5's smoke gate); `tests/runtime/test_instagram_sweep.py` drives all 22 tools through the real dispatcher against a fake graph.instagram.com.
  - **Runbooks:** `live-acceptance-instagram.md` (new: GI-1 to GI-8, the throwaway account, the hidden prompt); `install.md` (adding an account, refresh); `clients-claude-code.md` (the ask rules, the prompt flag, `instagram.default`).
  - **Exit test:** `tests/security/test_instagram_exit.py` pins the 22 names and order, the catalog digest and count (152), the ask list, the egress classes, `NETWORK_MODULES`, `_meta` on exactly four tools, `ADAPTER_CONTRACTS["instagram"]`, the five prefixes, the actor enums and schema v10.
  - **Ruling R-IG8:** the points above. `CLAUDE.md` gains the A49 paragraph, the Map row and the counts.
- **Files changed:** `src/comms/runtime/{doctor,operator/instagram}.py`; `src/comms/transports/instagram/doctor.py`; `scripts/{e2e_smoke,smoke_daemon}.py`; `docs/runbooks/{live-acceptance-instagram,install,clients-claude-code}.md`; `docs/verification/{comms-v0.3-rulings.md,comms-v0.3-smoke-map.json}`; `CLAUDE.md`; tests (`tests/security/test_instagram_exit.py`, `tests/runtime/test_instagram_sweep.py`, `tests/runtime/operator/test_doctor_cli.py`, `tests/conformance/test_live_gating.py`, `tests/security/test_runbooks.py`).
- **Verification:** new tests seen failing first; 5,898 tests collected (262 more than the baseline's 5,636); the affected suites pass (1503); ruff, format, mypy clean; full gate on the commit in the main checkout (ledger line).
- **Follow-ups:** the owner's IG-7: add a throwaway account, run GI-1 first, decide open questions 1 to 4, then ruling R-IG0 adopts A49.


### 2026-10-04 (Australia/Sydney), A49 gate ledger
**Raouf:**
- **Scope:** The gate record for plan tasks IG-1 to IG-6 (R-IG1, R-IG8 (5)): a commit cannot hold its own result, so this entry follows the last gate.
- **Summary:** each task commit passed the full `CLAUDE.md` Verify list in the main checkout, detached at that commit. The host is Linux, running as root, with no IPv6, so the verdict is "host-adjusted": the only failures are exactly the baseline's (`test_install.py` x4, `test_v03_part_b_exit.py`, the audit anchor-repair test and the doctor off-probe test; smoke `doctor headless` and `install plans are inert`). Contracts, formal, ruff, format, mypy, build, WhatsVault and the relay pass on every commit.

  | Task | Commit | pytest (passed, baseline failures, skipped) | Smoke | Catalog |
  |---|---|---|---|---|
  | IG-0 | `8dac743` | baseline: 5623, 7, 6 | 106 of 108 | 130, `57e490cc…` |
  | IG-1 | `5260e25` | 5673, 7, 6 | 106 of 108 | 130, `21cc382a…` |
  | IG-2 | `6e13325` | 5713, 7, 6 | 106 of 108 | 142, `c6eb7dee…` |
  | IG-3 | `245d89c` | 5778, 7, 6 | 106 of 108 | 147, `afe1a371…` |
  | IG-4 | `e9051a6` | 5862, 7, 6 | 106 of 108 | 152, `de8c9897…` |
  | IG-5 | `20fee34` | 5867, 7, 6 | 106 of 108 | 152, `e8d5da8e…` |
  | IG-6 | `3e52a2c` | 5885, 7, 6 | 107 of 109 | 152, `e8d5da8e…` |

- **What the gates found:** the first IG-1 gate found `ADAPTER_CONTRACTS["instagram"]` advertised with no conformance cases (R-IG3 (8)); the IG-2 gate found the smoke sweep and two exit tests pinning 130 tools (R-IG4 (6)); the IG-6 gate found the preview digest's wire domain and the real-daemon smoke count unpinned (R-IG6, R-IG8). Each was fixed in the commit that caused it before `comms-instagram-spec` moved, so the branch holds only gated commits.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the gate logs on the execution host; this entry's own commit is gated the same way.
- **Follow-ups:** the owner's IG-7 (a throwaway account, GI-1 first, open questions 1 to 4, ruling R-IG0).


### 2026-10-04 (Australia/Sydney), A49 end-to-end smoke
**Raouf:**
- **Scope:** The owner's request for a full end-to-end smoke covering every function: Instagram now runs on the real daemon, through the installed binary, not only in the pytest suite.
- **Summary:**
  - **Seam:** `comms selftest-daemon` builds the real Instagram adapters (accounts, capability, admin, publishing ledger) over a scripted graph.instagram.com when `comms.json` names Instagram accounts; `Adapters.instagram_transport` hands the same transport to the operator commands. Production passes `None`, the network (R-IG9).
  - **Smoke:** `drive_instagram` adds an account at the hidden prompt through a real pty, drives all 22 tools over HTTP `/mcp`, replays a DM, runs both doctors, refreshes the token, verifies the audit chain and removes the account. Nine checks; the smoke is 118 checks, 44 against a real daemon.
- **Files changed:** `src/comms/runtime/{selftest,adapters,assemble}.py`; `scripts/{smoke_daemon,e2e_smoke}.py`; `docs/verification/{comms-v0.3-rulings.md,comms-v0.3-smoke-map.json}`; `tests/security/test_d39_pre_exit.py`; `CLAUDE.md`.
- **Verification:** the nine checks pass on their own against a real selftest daemon; smoke-map and D39 exit tests pass; ruff, format, mypy clean; full gate on the commit in the main checkout.
- **Follow-ups:** none from the smoke; the owner's IG-7 live gates remain.


### 2026-10-04 (Australia/Sydney), README for the Instagram actor
**Raouf:**
- **Scope:** The owner asked for the public repositories to be professional and fully documented, with no secret pushed.
- **Summary:**
  - **README:** the proposed Instagram actor (A49), the catalog count with it (152), its status (gated against a scripted Graph; live gates GI-1 to GI-8 still to run; adoption by ruling R-IG0), its runbooks, its layout row and its specification.
  - **Secret scan:** every added line in this branch's history and the changed files were scanned (patterns for Meta, Instagram, Telegram, cloud and private keys, plus `detect-secrets`). The only hits are deliberate fakes: the canary test tokens, the public age test vectors, the relay's `TEST_IDENTITY` and synthetic Meta-shaped ids. No real credential is tracked; the relay's production values are Cloudflare secrets.
  - **Design repository:** `Raoof128/Instagram-MCP` gained a README, architecture notes, a security policy, contributing guide, code of conduct, changelog and MIT licence (matching WhatsVault), with the specification and plan mirrors updated to `3874771`.
- **Files changed:** `README.md`, `AGENT.md`, `CHANGELOG.md`.
- **Verification:** documentation only; the README's paths exist; ruff and the runbook tests are unaffected.
- **Follow-ups:** comms itself has no licence file; choosing one is the owner's call.


### 2026-10-04 (Australia/Sydney), IG-8: Stories publishing
**Raouf:**
- **Scope:** The owner asked for the MCP to publish Stories as well as posts. Plan task IG-8, spec revision 3, ruling R-IG10.
- **Summary:**
  - **Facts checked first:** Meta's Instagram Login content-publishing guide confirms `media_type=STORIES` with `image_url` or `video_url` on `graph.instagram.com`, under the scopes already required. The IG User Media reference refuses caption, location, alt text, `share_to_feed`, cover, thumbnail offset and AI label on a Story; stickers are not supported; a Story video runs 3 to 60 s, 100 MB at most.
  - **Tool:** `comms_instagram_container_create` (and `publish_preview`) gain kinds `story_image` and `story_video`. A Story takes only its URL; anything else is refused before Meta. `publish` publishes it like any container. No new tool, scope or host.
  - **Ledger:** migration v11 rebuilds `instagram_containers` so its `kind` admits `story`, keeping every v10 row, the index and the immutability trigger.
  - **Pins:** spec and plan re-pinned with R-IG10; the catalog pin moves for two tools (`e8d5da8e115a14a6…` to `1032910948054f25…`).
- **Files changed:** `src/comms/core/storage/migrations.py`; `src/comms/transports/instagram/{publish,store}.py`; `src/comms/mcp/tools/instagram.py`; `docs/instagram-spec-v0.6.md`; the plan; `docs/verification/{comms-v0.3-rulings.md,comms-v0.3-smoke-map.json}`; `docs/runbooks/live-acceptance-instagram.md`; `scripts/{smoke_daemon,e2e_smoke}.py`; `README.md`; `CLAUDE.md`; tests (`test_store.py`, `test_publish_ledger.py`, `test_instagram_publish.py`, `test_instagram_sweep.py`, `test_instagram_exit.py`, the catalog pin).
- **Verification:** the new tests seen failing first (11 more, 5,909 collected); the Instagram suites pass; the real-daemon smoke publishes a Story through the installed binary; full gate on the commit.
- **Follow-ups:** a live Story on the throwaway account (runbook, GI-3's run).


### 2026-10-05 (Australia/Sydney), renamed to comms-mcp
**Raouf:**
- **Scope:** The owner asked to rename the project from `telegram-mcp` to `comms-mcp`.
- **Summary:**
  - **Renamed:** the Python distribution (`pyproject.toml` `name`, `uv.lock`; no dependency changed) and every link to the repository and its public pages (`site/`, README). The GitHub repository itself is renamed by the owner in its settings.
  - **Kept on purpose:** the `telegram-mcp` console script, the Keychain service, `/private/var/run/telegram-mcp`, logger names and every frozen wire (`CLAUDE.md`, Non-negotiables). Historical records (plans, rulings, verification, this audit trail) keep the names they had.
  - **Meta:** GitHub Pages does not redirect a renamed project site, so W-Vault's Privacy Policy and data deletion URLs in the Meta app settings must move to `https://raoof128.github.io/comms-mcp/privacy/` as soon as the repository is renamed.
- **Files changed:** `pyproject.toml`, `uv.lock`, `site/index.html`, `site/privacy/index.html`, `README.md`, `CLAUDE.md`, `tests/security/test_ai_boundary.py`, `tests/security/test_egress.py` (the supply-chain pin compares dependencies, not the project's own renamed entry), `AGENT.md`, `CHANGELOG.md`.
- **Verification:** `uv lock` changed only the project's own entry; the full gate on the commit.
- **Follow-ups:** the owner renames the repository, then updates the two Meta URLs.

### 2026-10-05 (Australia/Sydney), IG-9: reading Stories
**Raouf:**
- **Scope:** The owner asked for "the story section" to be built if needed. Stories could be published (IG-8) but not read back. Plan task IG-9, spec revision 4, ruling R-IG11.
- **Summary:**
  - **Facts checked first:** the IG User reference lists `GET /<IG_ID>/stories` (the account's live Stories) under Instagram Login, but the edge's own page shows only `graph.facebook.com`, so it is 🧪 GI-3 on `graph.instagram.com`. Story insights take their own metrics (`navigation`, `replies`, `profile_activity` and others) and answer under five viewers with error 10.
  - **Tools:** `comms_instagram_story_list` reads live Stories as ordinary `igm_` refs through a client-bound cursor, asking for no caption or media URL. `comms_instagram_story_insights` checks its metrics and breakdown before any call; too few viewers is `NOT_ENOUGH_DATA`. No new capability, scope, host or table.
  - **Pins:** spec and plan re-pinned with R-IG11; the catalog moves to 154 tools (`1032910948054f25…` to `ce65f29fdffec396…`).
- **Files changed:** `src/comms/core/providers/instagram_insights.py`; `src/comms/transports/instagram/{http,insights}.py`; `src/comms/runtime/{instagram,facades,selftest}.py`; `src/comms/mcp/{egress.py,tools/instagram.py}`; `docs/instagram-spec-v0.6.md`; the plan; `docs/verification/{comms-v0.3-rulings.md,comms-v0.3-actor-matrix.md,comms-v0.3-smoke-map.json}`; `docs/runbooks/live-acceptance-instagram.md`; `scripts/{smoke_daemon,e2e_smoke}.py`; `README.md`; `CLAUDE.md`; tests (`test_instagram_stories.py` new, `test_instagram_sweep.py`, `test_instagram_exit.py`, the catalog pin).
- **Verification:** the new tests seen failing first (5,923 collected); the Instagram, MCP, egress and host-permission suites pass; the real-daemon smoke reads a Story and its insights through the installed binary; full gate on the commit.
- **Follow-ups:** GI-3 on the throwaway account proves the stories edge on the Instagram Login host.


### 2026-10-05 (Australia/Sydney), IG-9 and the rename merged; gate ledger
**Raouf:**
- **Scope:** The owner approved merging Story reads (IG-9) and the `comms-mcp` rename into `main`, then asked for every log to be updated and every branch merged safely. A commit cannot hold its own gate result, so this entry records both gates.
- **Summary:**
  - **Merges:** `main` fast-forwarded to IG-9 (`ba05c05`), then took `comms-mcp-rename` as merge `1f66f3e`. The only conflicts were the append-only `AGENT.md` and `CHANGELOG.md`; both entries were kept.
  - **Gates:** each commit passed the full `CLAUDE.md` Verify list in the main checkout, detached at that commit. The host is Linux, running as root, with no IPv6, so the verdict is "host-adjusted": the only failures are exactly the baseline's (`test_install.py` x4, `test_v03_part_b_exit.py`, the audit anchor-repair test and the doctor off-probe test; smoke `doctor headless` and `install plans are inert`).

    | Commit | What | pytest (passed, baseline failures, skipped) | Smoke | Catalog |
    |---|---|---|---|---|
    | `ba05c05` | IG-9: reading Stories | 5910, 7, 6 | 116 of 118 | 154, `ce65f29f…` |
    | `1f66f3e` | merge: the rename | 5910, 7, 6 | 116 of 118 | 154, `ce65f29f…` |

  - **GitHub:** `main` pushed (`9374c6c..1f66f3e`); the Pages workflow deployed it. All 24 remote branches are ancestors of `main`, so none holds unmerged work.
  - **Venv:** the distribution swap removes the shared console scripts; `uv sync --locked --reinstall-package comms-mcp` restores `comms` and `telegram-mcp`.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`.
- **Verification:** the two gate logs on the execution host; `git merge-base --is-ancestor` for every remote branch against `origin/main`.
- **Follow-ups (owner):** the GitHub repository is still `Raoof128/telegram-mcp`, so links to `comms-mcp` answer 404 until it is renamed in Settings. After the rename: W-Vault's Privacy Policy and data deletion URLs in the Meta app become `https://raoof128.github.io/comms-mcp/privacy/` (Pages does not redirect); on the Mac, `git remote set-url`, `uv sync --locked --reinstall-package comms-mcp` and a daemon restart. Remote branch deletion is refused from this session (HTTP 403), so the merged branches are the owner's to delete. Then IG-7 (GI-1 first; GI-3 proves the stories edge).


### 2026-10-05 (Australia/Sydney), Instagram live acceptance, first run
**Raouf:**
- **Scope:** The owner renamed the repository, then asked for the Instagram live gates to run on their own account, @punpun.r12, instead of a throwaway.
- **Summary:**
  - **Host:** clone switched to `Raoof128/comms-mcp`. Both W-Vault URLs now point at `https://raoof128.github.io/comms-mcp/privacy/` (`#deletion` for data deletion). The daemon runs from this checkout on the existing state, backed up first to `state.bak-2026-10-05`. All 25 merged remote branches were deleted, leaving `main`.
  - **Account:** `comms.json` gains `instagram` (`default` `main`; `main`: label `punpun.r12`, `writes` and `dms` true). punpun.r12 is an Instagram Tester on W-Vault-IG. Its token was added at the hidden prompt in Terminal.app and proved by `GET /me` (`iga_akejch7j6q3tbjh6snuj6n2ftw`, expires 2026-12-04).
  - **Gates:** GI-3 and GI-5 pass. GI-1 passes doctor and the comment hide round trip; its refresh needs a 24-hour-old token. GI-4 passes with captions off. Publishing (feed image and Story), comment reply, replay, replies and delete all ran live. The test post was deleted afterwards. The images were served from Pages for the run only (`d79f2c1`, removed in `d41e8ef`).
  - **Findings:** a thread without exactly one counterpart (conversation 25, likely a group) fails the whole `conversation_list` page, so no cursor passes it. `media_get` on a deleted post answers `INVALID_ARGUMENT` (Meta code 100). Both need a ruling; no code changed.
- **Files changed:** `docs/verification/live-acceptance/2026-10-05-instagram.md` (new), `AGENT.md`, `CHANGELOG.md`. Earlier, on `main`: `site/test/` added and removed.
- **Verification:** a scripted MCP stdio client against the running daemon (154 tools, 24 Instagram); every result was read back through comms. The live caption was checked against the permalink's `og:description`. Documentation only, so the full gate was not run.
- **Follow-ups (owner):** token refreshes on 2026-10-06 after 16:04 and a day later (GI-1, GI-2); GI-4 with captions on; GI-6 and GI-7 in Claude Code and Desktop; GI-8 messages and one DM reply; `story_insights` once five people have viewed the Story; rulings on the two findings, then R-IG0.


### 2026-10-05 (Australia/Sydney), clients registered, a second Instagram account, the comms-mcp skill
**Raouf:**
- **Scope:** The owner asked for comms to be registered in Claude Code and Codex, for the society's Instagram account to be added with writes on, and for a skill covering the whole tool surface.
- **Summary:**
  - **Clients:**
    - **Claude Code:** comms is a user-scope MCP server in `~/.claude.json`, using the existing `claude-code.seed`; `claude mcp get comms` reports Connected. The repo's 61 `permissions.ask` rules are merged into `~/.claude/settings.json`, so every consequential write prompts (R-A20).
    - **Codex:** `comms client add --name codex` made `cli_adgyxqose5ba5etojwxamnwjtf` with `~/.config/comms/codex.seed` (0600), and `[mcp_servers.comms]` was added to `~/.codex/config.toml`. A read through the Codex seed answered.
    - **Proxy flags:** both entries pass `--daemon http://127.0.0.1:8866 --runtime-dir ~/Library/Application Support/comms/run`. Each config was backed up as `*.bak-comms-20261005` first.
  - **Second account:**
    - `comms.json` gains `instagram.accounts.mqps` (label `mqpersiansociety`, `writes` true, `dms` false). @mqpersiansociety is an Instagram Tester on W-Vault-IG.
    - Its token was added at the hidden prompt and proved by `GET /me`: `iga_akybk67tcni7nkohuiic7jj664`, expires 2026-12-04.
    - Reads verified live: whoami, profile, quota, account insights, media and Story lists, comments and conversations. An `igm_` from `mqps` read under `main` answers `NOT_FOUND`, so refs stay isolated per account.
    - `publish_preview` answers `writes_allowed: true`.
  - **Skill:** `~/.claude/skills/comms-mcp/` (linked into `~/.codex/skills/`). Contents:
    - `SKILL.md`: health, refs, `request_id`, outcomes, safety rules and error codes.
    - References: `tools.md`, all 154 tools generated from the live catalog; `messaging.md`; `instagram.md`.
    - Scripts: `health.sh`, `call.py` with `--redact`, `dump_catalog.py`.
    - Validated with skill-creator. A fresh agent used it to answer a read-only question correctly; its six gaps were fixed.
- **Files changed:** `AGENT.md`, `CHANGELOG.md`, `docs/verification/live-acceptance/2026-10-05-instagram.md` (addendum). Outside the repo: `comms.json`, the two client configs, `~/.claude/settings.json`, the skill.
- **Verification:** `comms transport instagram doctor` reports OK for both aliases, and `comms doctor` reports `ok: true`. Every Instagram read above went through the stdio proxy. Documentation only, so the full gate was not run.
- **Follow-ups (owner):** restart Claude Code and Codex to load comms, then run GI-6 and GI-7 there. Nothing restarts the daemon after a reboot (`scripts/health.sh --start` in the skill). The token refreshes and the GI-8 DM work stand as before.
