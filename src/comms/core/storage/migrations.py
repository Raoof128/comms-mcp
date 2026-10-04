"""Append-only numbered migrations for comms.db (design §2, G23).

Each pending migration runs in ONE ``BEGIN IMMEDIATE`` with its version row, so
a failure leaves neither partial schema nor an advanced version (measured, M11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from comms.core.storage.db import write_tx

__all__ = [
    "MIGRATIONS",
    "SCHEMA_V1",
    "SCHEMA_V2",
    "SCHEMA_V3",
    "SCHEMA_V4",
    "Migration",
    "migrate",
]


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]
    # Runs with foreign keys off (set outside the transaction) and must leave
    # ``PRAGMA foreign_key_check`` empty: the 5b-3 table-rebuild method.
    rebuild: bool = False


_SCHEMA_V1_SQL = """
CREATE TABLE locations (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), created_at TEXT NOT NULL);
CREATE TABLE recipients (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), created_at TEXT NOT NULL);
CREATE TABLE delivery_identities (id INTEGER PRIMARY KEY,
  transport TEXT NOT NULL CHECK (transport IN ('telegram','whatsapp')), identity TEXT NOT NULL,
  UNIQUE (transport, identity));
CREATE TABLE destinations (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  transport TEXT NOT NULL CHECK (transport = 'telegram'), platform_identity TEXT NOT NULL,
  identity_id INTEGER NOT NULL REFERENCES delivery_identities(id) ON DELETE RESTRICT,
  display_name TEXT NOT NULL, capabilities TEXT NOT NULL DEFAULT '{}',
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), created_at TEXT NOT NULL);
CREATE INDEX destinations_location ON destinations (location_id);
CREATE UNIQUE INDEX destinations_one_enabled_per_identity ON destinations (identity_id) WHERE enabled = 1;
CREATE TABLE contact_points (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  recipient_id INTEGER NOT NULL REFERENCES recipients(id) ON DELETE RESTRICT,
  transport TEXT NOT NULL CHECK (transport IN ('telegram','whatsapp')), platform_identity TEXT NOT NULL,
  identity_id INTEGER NOT NULL REFERENCES delivery_identities(id) ON DELETE RESTRICT,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), opted_out_at TEXT, created_at TEXT NOT NULL);
CREATE INDEX contact_points_recipient ON contact_points (recipient_id);
CREATE UNIQUE INDEX contact_points_one_enabled_per_transport ON contact_points (recipient_id, transport) WHERE enabled = 1;
CREATE UNIQUE INDEX contact_points_one_enabled_per_identity ON contact_points (identity_id) WHERE enabled = 1;
CREATE TABLE location_members (location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  recipient_id INTEGER NOT NULL REFERENCES recipients(id) ON DELETE RESTRICT, PRIMARY KEY (location_id, recipient_id));
CREATE INDEX location_members_recipient ON location_members (recipient_id);
CREATE TABLE audiences (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE audience_members (id INTEGER PRIMARY KEY,
  audience_id INTEGER NOT NULL REFERENCES audiences(id) ON DELETE RESTRICT,
  member_location_id INTEGER REFERENCES locations(id) ON DELETE RESTRICT,
  member_audience_id INTEGER REFERENCES audiences(id) ON DELETE RESTRICT,
  member_destination_id INTEGER REFERENCES destinations(id) ON DELETE RESTRICT,
  member_recipient_id INTEGER REFERENCES recipients(id) ON DELETE RESTRICT,
  CHECK ((member_location_id IS NOT NULL) + (member_audience_id IS NOT NULL)
       + (member_destination_id IS NOT NULL) + (member_recipient_id IS NOT NULL) = 1),
  CHECK (member_audience_id IS NULL OR member_audience_id <> audience_id));
CREATE UNIQUE INDEX audience_members_unique ON audience_members (audience_id,
  IFNULL(member_location_id,0), IFNULL(member_audience_id,0), IFNULL(member_destination_id,0), IFNULL(member_recipient_id,0));
CREATE TABLE campaigns (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
  lifecycle TEXT NOT NULL CHECK (lifecycle IN ('DRAFT','READY','SCHEDULED','SENDING','COMPLETE','CANCELLED')),
  content TEXT NOT NULL, targets TEXT NOT NULL, options TEXT NOT NULL,
  summary TEXT CHECK (summary IS NULL OR summary IN ('IN_PROGRESS','INDETERMINATE','SENT','PARTIAL','CANCELLED','FAILED')),
  current_generation_id INTEGER REFERENCES generations(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK ((summary IS NULL) = (current_generation_id IS NULL)));
CREATE TABLE generations (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL, send_at TEXT NOT NULL, content TEXT NOT NULL,
  snapshot_digest TEXT NOT NULL CHECK (length(snapshot_digest) = 64),
  status TEXT NOT NULL CHECK (status IN ('active','discarded')));
CREATE INDEX generations_campaign ON generations (campaign_id);
CREATE TABLE delivery_jobs (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE RESTRICT,
  transport TEXT NOT NULL CHECK (transport IN ('telegram','whatsapp')),
  identity_id INTEGER NOT NULL REFERENCES delivery_identities(id) ON DELETE RESTRICT,
  idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) = 64),
  payload BLOB, payload_digest TEXT, skip_reason TEXT,
  state TEXT NOT NULL CHECK (state IN ('PENDING','IN_FLIGHT','ACCEPTED','DELIVERED','FAILED_TRANSIENT',
    'FAILED_PERMANENT','OUTCOME_UNKNOWN','CANCELLED','SKIPPED_PLATFORM_POLICY','SKIPPED_REVALIDATION')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  UNIQUE (generation_id, transport, identity_id),
  CHECK ((payload IS NULL) = (payload_digest IS NULL)),
  CHECK ((payload IS NULL) = (skip_reason IS NOT NULL)),
  CHECK ((state = 'SKIPPED_PLATFORM_POLICY') = (payload IS NULL)),
  CHECK (payload_digest IS NULL OR (length(payload_digest) = 64 AND payload_digest NOT GLOB '*[^0-9a-f]*')));
CREATE TABLE job_origins (id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES delivery_jobs(id) ON DELETE RESTRICT,
  endpoint_ref TEXT NOT NULL, path TEXT NOT NULL,          -- TG-JCS-v1 array of refs, target first, endpoint last
  CHECK (json_valid(path) AND json_type(path) = 'array' AND json_array_length(path) >= 1),
  CHECK (json_extract(path, '$[#-1]') = endpoint_ref));
CREATE INDEX job_origins_job ON job_origins (job_id);
CREATE TABLE delivery_attempts (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  job_id INTEGER NOT NULL REFERENCES delivery_jobs(id) ON DELETE RESTRICT,
  attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1), started_at TEXT NOT NULL, finished_at TEXT,
  outcome TEXT CHECK (outcome IS NULL OR outcome IN ('ACCEPTED','DELIVERED','FAILED_TRANSIENT','FAILED_PERMANENT','OUTCOME_UNKNOWN')),
  provider_message_ref TEXT, UNIQUE (job_id, attempt_no),
  CHECK ((finished_at IS NULL) = (outcome IS NULL)));
CREATE INDEX delivery_attempts_provider_ref ON delivery_attempts (provider_message_ref) WHERE provider_message_ref IS NOT NULL;
CREATE TABLE provider_events (id INTEGER PRIMARY KEY,
  transport TEXT NOT NULL CHECK (transport IN ('telegram','whatsapp')), provider_event_ref TEXT NOT NULL,
  provider_message_ref TEXT NOT NULL,
  job_id INTEGER REFERENCES delivery_jobs(id) ON DELETE RESTRICT,
  attempt_id INTEGER REFERENCES delivery_attempts(id) ON DELETE RESTRICT,
  reported_status TEXT NOT NULL CHECK (reported_status IN ('ACCEPTED','DELIVERED','FAILED_PERMANENT')),
  disposition TEXT NOT NULL CHECK (disposition IN ('applied','recorded','refused','pending_match')),
  received_at TEXT NOT NULL, UNIQUE (transport, provider_event_ref),
  CHECK (disposition <> 'pending_match' OR attempt_id IS NULL),
  CHECK (disposition NOT IN ('applied','recorded') OR attempt_id IS NOT NULL));
CREATE INDEX provider_events_pending ON provider_events (transport, provider_message_ref) WHERE disposition = 'pending_match';
CREATE TABLE campaign_events (event_seq INTEGER PRIMARY KEY AUTOINCREMENT, event_ref TEXT NOT NULL UNIQUE,
  campaign_ref TEXT, event_type TEXT NOT NULL, ts TEXT NOT NULL, payload TEXT NOT NULL);
-- Transport agreement (G14): an endpoint or job must name its identity's transport.
CREATE TRIGGER destinations_transport_matches_identity BEFORE INSERT ON destinations
  WHEN (SELECT transport FROM delivery_identities WHERE id = NEW.identity_id) IS NOT NEW.transport
  BEGIN SELECT RAISE(ABORT, 'endpoint transport mismatch'); END;
CREATE TRIGGER contact_points_transport_matches_identity BEFORE INSERT ON contact_points
  WHEN (SELECT transport FROM delivery_identities WHERE id = NEW.identity_id) IS NOT NEW.transport
  BEGIN SELECT RAISE(ABORT, 'endpoint transport mismatch'); END;
CREATE TRIGGER delivery_jobs_transport_matches_identity BEFORE INSERT ON delivery_jobs
  WHEN (SELECT transport FROM delivery_identities WHERE id = NEW.identity_id) IS NOT NEW.transport
  BEGIN SELECT RAISE(ABORT, 'job transport mismatch'); END;
-- An origin's endpoint must resolve to its job's (transport, identity) (G14).
CREATE TRIGGER job_origins_endpoint_matches_job BEFORE INSERT ON job_origins
  WHEN NOT EXISTS (SELECT 1 FROM delivery_jobs j WHERE j.id = NEW.job_id AND (
    EXISTS (SELECT 1 FROM destinations d WHERE d.ref = NEW.endpoint_ref AND d.identity_id = j.identity_id AND d.transport = j.transport)
    OR EXISTS (SELECT 1 FROM contact_points c WHERE c.ref = NEW.endpoint_ref AND c.identity_id = j.identity_id AND c.transport = j.transport)))
  BEGIN SELECT RAISE(ABORT, 'origin endpoint does not match its job'); END;
-- The current generation belongs to its campaign and is active (G16).
CREATE TRIGGER campaigns_insert_has_no_generation BEFORE INSERT ON campaigns
  WHEN NEW.current_generation_id IS NOT NULL BEGIN SELECT RAISE(ABORT, 'generation belongs to another campaign'); END;
CREATE TRIGGER campaigns_generation_owned BEFORE UPDATE OF current_generation_id ON campaigns
  WHEN NEW.current_generation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM generations g
    WHERE g.id = NEW.current_generation_id AND g.campaign_id = NEW.id AND g.status = 'active')
  BEGIN SELECT RAISE(ABORT, 'generation belongs to another campaign'); END;
-- Immutability (R11, §7.1).
CREATE TRIGGER destinations_identity_immutable BEFORE UPDATE OF transport, platform_identity, identity_id, location_id, ref
  ON destinations BEGIN SELECT RAISE(ABORT, 'destination identity is immutable'); END;
CREATE TRIGGER contact_points_identity_immutable BEFORE UPDATE OF transport, platform_identity, identity_id, recipient_id, ref
  ON contact_points BEGIN SELECT RAISE(ABORT, 'contact point identity is immutable'); END;
CREATE TRIGGER delivery_identities_immutable BEFORE UPDATE ON delivery_identities
  BEGIN SELECT RAISE(ABORT, 'delivery identity is immutable'); END;
CREATE TRIGGER generations_frozen BEFORE UPDATE OF ref, campaign_id, created_at, send_at, content, snapshot_digest
  ON generations BEGIN SELECT RAISE(ABORT, 'generation is frozen'); END;
CREATE TRIGGER generations_status_one_way BEFORE UPDATE OF status ON generations
  WHEN NOT (OLD.status = 'active' AND NEW.status = 'discarded')
  BEGIN SELECT RAISE(ABORT, 'generation is frozen'); END;
CREATE TRIGGER jobs_binding_frozen BEFORE UPDATE OF ref, generation_id, transport, identity_id,
  idempotency_key, payload, payload_digest, skip_reason ON delivery_jobs
  BEGIN SELECT RAISE(ABORT, 'job binding is frozen'); END;
CREATE TRIGGER job_origins_frozen_u BEFORE UPDATE ON job_origins BEGIN SELECT RAISE(ABORT, 'origins are frozen'); END;
CREATE TRIGGER job_origins_frozen_d BEFORE DELETE ON job_origins BEGIN SELECT RAISE(ABORT, 'origins are frozen'); END;
CREATE TRIGGER attempts_binding_frozen BEFORE UPDATE OF ref, job_id, attempt_no, started_at ON delivery_attempts
  BEGIN SELECT RAISE(ABORT, 'attempt binding is frozen'); END;
CREATE TRIGGER attempts_provider_ref_set_once BEFORE UPDATE OF provider_message_ref ON delivery_attempts
  WHEN OLD.provider_message_ref IS NOT NULL BEGIN SELECT RAISE(ABORT, 'provider reference is frozen'); END;
CREATE TRIGGER provider_events_only_pending_resolves BEFORE UPDATE ON provider_events
  WHEN OLD.disposition <> 'pending_match' OR NEW.transport IS NOT OLD.transport
    OR NEW.provider_event_ref IS NOT OLD.provider_event_ref OR NEW.provider_message_ref IS NOT OLD.provider_message_ref
    OR NEW.reported_status IS NOT OLD.reported_status OR NEW.received_at IS NOT OLD.received_at
  BEGIN SELECT RAISE(ABORT, 'provider event is frozen'); END;
CREATE TRIGGER provider_events_no_delete BEFORE DELETE ON provider_events
  BEGIN SELECT RAISE(ABORT, 'provider event is frozen'); END;
-- Endpoints are disabled, never deleted (§2): job origins name them by ref, not by FK.
CREATE TRIGGER destinations_never_deleted BEFORE DELETE ON destinations
  BEGIN SELECT RAISE(ABORT, 'endpoints are disabled, never deleted'); END;
CREATE TRIGGER contact_points_never_deleted BEFORE DELETE ON contact_points
  BEGIN SELECT RAISE(ABORT, 'endpoints are disabled, never deleted'); END;
CREATE TRIGGER campaign_events_append_only_u BEFORE UPDATE ON campaign_events
  BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
CREATE TRIGGER campaign_events_append_only_d BEFORE DELETE ON campaign_events
  BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
"""


def _statements(sql: str) -> tuple[str, ...]:
    """One statement per entry: whole-line comments dropped, then split on ";\n" (trigger
    bodies are single-line, so their inner ";" is never followed by a newline)."""
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return tuple(part.strip() for part in "\n".join(lines).split(";\n") if part.strip())


SCHEMA_V1: tuple[str, ...] = _statements(_SCHEMA_V1_SQL)

# comms v0.3: assembled across Part A's tasks before the single merge (plan Global Constraints).
_SCHEMA_V2_SQL = """
CREATE TABLE key_slots (purpose TEXT NOT NULL, version INTEGER NOT NULL CHECK (version >= 1), key_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','TRUSTED_RETIRED','VERIFICATION_ONLY','REVOKED','RETIRED','ORPHAN','DESTROYED')),
  created_at TEXT NOT NULL, retired_at TEXT, PRIMARY KEY (purpose, version));
CREATE UNIQUE INDEX key_slots_one_active ON key_slots (purpose) WHERE state = 'ACTIVE';
CREATE TRIGGER key_slots_binding_immutable BEFORE UPDATE OF purpose, version, key_id, created_at ON key_slots
  BEGIN SELECT RAISE(ABORT, 'key slot binding is immutable'); END;
CREATE TABLE verification_keys (key_id TEXT PRIMARY KEY, purpose TEXT NOT NULL, algorithm TEXT NOT NULL,
  public_key BLOB NOT NULL, activated_at TEXT NOT NULL, retired_at TEXT,
  trust_state TEXT NOT NULL CHECK (trust_state IN ('ACTIVE','TRUSTED_RETIRED','VERIFICATION_ONLY','REVOKED')));
CREATE TRIGGER verification_keys_public_immutable BEFORE UPDATE OF key_id, purpose, algorithm, public_key
  ON verification_keys BEGIN SELECT RAISE(ABORT, 'verification key is immutable'); END;
CREATE TABLE audit_events (event_id TEXT PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL, subject_ref TEXT,
  subject_digest TEXT, payload TEXT NOT NULL,
  chain_epoch INTEGER NOT NULL CHECK (chain_epoch >= 1), chain_seq INTEGER NOT NULL CHECK (chain_seq >= 1),
  prev_event_mac TEXT NOT NULL, event_mac TEXT NOT NULL, UNIQUE (chain_epoch, chain_seq));
CREATE TABLE audit_checkpoints (checkpoint_ref TEXT PRIMARY KEY, chain_epoch INTEGER NOT NULL,
  chain_seq INTEGER NOT NULL, last_event_id TEXT NOT NULL, last_event_mac TEXT NOT NULL, reason TEXT NOT NULL,
  created_at TEXT NOT NULL, signing_key_id TEXT NOT NULL, signature TEXT NOT NULL);
CREATE TRIGGER audit_events_append_only_u BEFORE UPDATE ON audit_events
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER audit_events_append_only_d BEFORE DELETE ON audit_events
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER audit_checkpoints_append_only_u BEFORE UPDATE ON audit_checkpoints
  BEGIN SELECT RAISE(ABORT, 'checkpoints are append-only'); END;
CREATE TRIGGER audit_checkpoints_append_only_d BEFORE DELETE ON audit_checkpoints
  BEGIN SELECT RAISE(ABORT, 'checkpoints are append-only'); END;
CREATE TABLE audit_integrity (id INTEGER PRIMARY KEY CHECK (id = 1),
  state TEXT NOT NULL CHECK (state IN ('ok','degraded')), reason TEXT, since TEXT);
INSERT INTO audit_integrity (id, state) VALUES (1, 'ok');
CREATE TABLE audit_lineage (cutover_ref TEXT PRIMARY KEY, legacy_chain_domain TEXT NOT NULL,
  legacy_final_epoch INTEGER NOT NULL, legacy_final_head TEXT NOT NULL, legacy_checkpoint_digest TEXT NOT NULL,
  legacy_checkpoint_key_id TEXT NOT NULL, comms_chain_domain TEXT NOT NULL, comms_genesis_digest TEXT NOT NULL,
  comms_first_epoch INTEGER NOT NULL, lineage_digest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER audit_lineage_immutable_u BEFORE UPDATE ON audit_lineage
  BEGIN SELECT RAISE(ABORT, 'lineage is immutable'); END;
CREATE TRIGGER audit_lineage_immutable_d BEFORE DELETE ON audit_lineage
  BEGIN SELECT RAISE(ABORT, 'lineage is immutable'); END;
CREATE TABLE cutover_state (id INTEGER PRIMARY KEY CHECK (id = 1), cutover_ref TEXT,
  phase TEXT NOT NULL CHECK (phase IN ('NONE','CUTOVER_ENTERED','LEGACY_DRAINED','LEGACY_VERIFIED','LEGACY_SEALED',
    'LEGACY_ANCHORED','COMMS_GENESIS','COMMS_ANCHORED','LEGACY_CLIENT_AUTH_REVOKED','COMPLETE')),
  legacy_checkpoint_digest TEXT, updated_at TEXT NOT NULL);
INSERT INTO cutover_state (id, phase, updated_at) VALUES (1, 'NONE', '1970-01-01T00:00:00.000000Z');
CREATE TABLE cutover_transitions (from_phase TEXT NOT NULL, to_phase TEXT NOT NULL, PRIMARY KEY (from_phase, to_phase));
INSERT INTO cutover_transitions VALUES ('NONE','CUTOVER_ENTERED'), ('CUTOVER_ENTERED','LEGACY_DRAINED'),
  ('LEGACY_DRAINED','LEGACY_VERIFIED'), ('LEGACY_VERIFIED','LEGACY_SEALED'), ('LEGACY_SEALED','LEGACY_ANCHORED'),
  ('LEGACY_ANCHORED','COMMS_GENESIS'), ('COMMS_GENESIS','COMMS_ANCHORED'),
  ('COMMS_ANCHORED','LEGACY_CLIENT_AUTH_REVOKED'), ('LEGACY_CLIENT_AUTH_REVOKED','COMPLETE');
CREATE TRIGGER cutover_transitions_fixed_u BEFORE UPDATE ON cutover_transitions
  BEGIN SELECT RAISE(ABORT, 'cutover transitions are fixed'); END;
CREATE TRIGGER cutover_transitions_fixed_d BEFORE DELETE ON cutover_transitions
  BEGIN SELECT RAISE(ABORT, 'cutover transitions are fixed'); END;
CREATE TRIGGER cutover_exact_next_state BEFORE UPDATE OF phase ON cutover_state
  WHEN NEW.phase IS NOT OLD.phase AND NOT EXISTS (SELECT 1 FROM cutover_transitions
       WHERE from_phase = OLD.phase AND to_phase = NEW.phase)
  BEGIN SELECT RAISE(ABORT, 'cutover moves only to its exact next state'); END;
CREATE TRIGGER cutover_fields_immutable BEFORE UPDATE OF cutover_ref, legacy_checkpoint_digest ON cutover_state
  WHEN (OLD.cutover_ref IS NOT NULL AND NEW.cutover_ref IS NOT OLD.cutover_ref)
    OR (OLD.legacy_checkpoint_digest IS NOT NULL AND NEW.legacy_checkpoint_digest IS NOT OLD.legacy_checkpoint_digest)
  BEGIN SELECT RAISE(ABORT, 'cutover identity is immutable'); END;
ALTER TABLE campaign_events ADD COLUMN event_digest TEXT;
"""
SCHEMA_V2: tuple[str, ...] = _statements(_SCHEMA_V2_SQL)

# comms v0.3 A12 (Task B8): the keyed campaign commitment on each generation. NULL only for
# a generation frozen without the audit writer (the 5b-4 unit harness), which never
# reaches the chain.
_SCHEMA_V3_SQL = """
ALTER TABLE generations ADD COLUMN campaign_commitment TEXT
  CHECK (campaign_commitment IS NULL OR length(campaign_commitment) = 64);
ALTER TABLE generations ADD COLUMN campaign_commit_key_id TEXT;
CREATE TRIGGER generations_commitment_immutable BEFORE UPDATE OF campaign_commitment, campaign_commit_key_id
  ON generations BEGIN SELECT RAISE(ABORT, 'a campaign commitment is immutable'); END;
CREATE TRIGGER verification_keys_trust_one_way BEFORE UPDATE OF trust_state ON verification_keys
  WHEN (CASE NEW.trust_state WHEN 'ACTIVE' THEN 0 WHEN 'TRUSTED_RETIRED' THEN 1
          WHEN 'VERIFICATION_ONLY' THEN 2 ELSE 3 END)
     < (CASE OLD.trust_state WHEN 'ACTIVE' THEN 0 WHEN 'TRUSTED_RETIRED' THEN 1
          WHEN 'VERIFICATION_ONLY' THEN 2 ELSE 3 END)
  BEGIN SELECT RAISE(ABORT, 'signer trust is one-way'); END;
CREATE TABLE maintenance_flags (name TEXT PRIMARY KEY, value INTEGER NOT NULL CHECK (value IN (0, 1)));
INSERT INTO maintenance_flags (name, value) VALUES ('truncating', 0);
DROP TRIGGER audit_events_append_only_d;
CREATE TRIGGER audit_events_delete_only_behind_root BEFORE DELETE ON audit_events
  WHEN (SELECT value FROM maintenance_flags WHERE name = 'truncating') IS NOT 1
  BEGIN SELECT RAISE(ABORT, 'audit is append-only: deletes only by truncation behind a root'); END;
-- Task B25: this installation's stable ref, which backups bind to.
CREATE TABLE installation (id INTEGER PRIMARY KEY CHECK (id = 1), installation_ref TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL);
CREATE TRIGGER installation_immutable BEFORE UPDATE ON installation
  BEGIN SELECT RAISE(ABORT, 'the installation ref is immutable'); END;
-- A15 (Task B20): directory identities of endpoints disabled past the retention window are
-- replaced by 'redacted:<delivery_identities.id>' (unique per row); nothing else may change.
ALTER TABLE destinations ADD COLUMN disabled_at TEXT;
ALTER TABLE contact_points ADD COLUMN disabled_at TEXT;
DROP TRIGGER delivery_identities_immutable;
CREATE TRIGGER delivery_identities_immutable BEFORE UPDATE ON delivery_identities
  WHEN NOT (NEW.id IS OLD.id AND NEW.transport IS OLD.transport AND NEW.identity = 'redacted:' || OLD.id
    AND OLD.identity NOT LIKE 'redacted:%')
  BEGIN SELECT RAISE(ABORT, 'delivery identity is immutable'); END;
DROP TRIGGER destinations_identity_immutable;
CREATE TRIGGER destinations_identity_immutable BEFORE UPDATE OF transport, platform_identity, identity_id, location_id, ref
  ON destinations WHEN NOT (NEW.transport IS OLD.transport AND NEW.identity_id IS OLD.identity_id
    AND NEW.location_id IS OLD.location_id AND NEW.ref IS OLD.ref
    AND NEW.platform_identity = 'redacted:' || OLD.identity_id)
  BEGIN SELECT RAISE(ABORT, 'destination identity is immutable'); END;
DROP TRIGGER contact_points_identity_immutable;
CREATE TRIGGER contact_points_identity_immutable BEFORE UPDATE OF transport, platform_identity, identity_id, recipient_id, ref
  ON contact_points WHEN NOT (NEW.transport IS OLD.transport AND NEW.identity_id IS OLD.identity_id
    AND NEW.recipient_id IS OLD.recipient_id AND NEW.ref IS OLD.ref
    AND NEW.platform_identity = 'redacted:' || OLD.identity_id)
  BEGIN SELECT RAISE(ABORT, 'contact point identity is immutable'); END;
-- A15 (Task B19): campaign-body redaction. The only edit a frozen generation or job ever
-- accepts is its body going (content -> '{}', payload -> NULL) with redacted_at set once;
-- every digest stays. delivery_jobs is rebuilt to relax its payload CHECKs for that case.
ALTER TABLE generations ADD COLUMN redacted_at TEXT;
DROP TRIGGER generations_frozen;
CREATE TRIGGER generations_frozen BEFORE UPDATE OF ref, campaign_id, created_at, send_at, content,
  snapshot_digest, redacted_at ON generations
  WHEN NOT (NEW.ref IS OLD.ref AND NEW.campaign_id IS OLD.campaign_id AND NEW.created_at IS OLD.created_at
    AND NEW.send_at IS OLD.send_at AND NEW.snapshot_digest IS OLD.snapshot_digest
    AND OLD.redacted_at IS NULL AND NEW.redacted_at IS NOT NULL AND NEW.content = '{}')
  BEGIN SELECT RAISE(ABORT, 'generation is frozen'); END;
CREATE TABLE delivery_jobs_v3 (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE RESTRICT,
  transport TEXT NOT NULL CHECK (transport IN ('telegram','whatsapp')),
  identity_id INTEGER NOT NULL REFERENCES delivery_identities(id) ON DELETE RESTRICT,
  idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) = 64),
  payload BLOB, payload_digest TEXT, skip_reason TEXT,
  state TEXT NOT NULL CHECK (state IN ('PENDING','IN_FLIGHT','ACCEPTED','DELIVERED','FAILED_TRANSIENT',
    'FAILED_PERMANENT','OUTCOME_UNKNOWN','CANCELLED','SKIPPED_PLATFORM_POLICY','SKIPPED_REVALIDATION')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  redacted_at TEXT,
  UNIQUE (generation_id, transport, identity_id),
  CHECK ((payload IS NULL) = (payload_digest IS NULL) OR redacted_at IS NOT NULL),
  CHECK ((payload IS NULL) = (skip_reason IS NOT NULL) OR redacted_at IS NOT NULL),
  CHECK ((state = 'SKIPPED_PLATFORM_POLICY') = (payload IS NULL) OR redacted_at IS NOT NULL),
  CHECK (redacted_at IS NULL OR payload IS NULL),
  CHECK (payload_digest IS NULL OR (length(payload_digest) = 64 AND payload_digest NOT GLOB '*[^0-9a-f]*')));
INSERT INTO delivery_jobs_v3 (id, ref, generation_id, transport, identity_id, idempotency_key, payload,
  payload_digest, skip_reason, state, attempt_count)
  SELECT id, ref, generation_id, transport, identity_id, idempotency_key, payload, payload_digest,
    skip_reason, state, attempt_count FROM delivery_jobs;
DROP TRIGGER job_origins_endpoint_matches_job;
DROP TABLE delivery_jobs;
ALTER TABLE delivery_jobs_v3 RENAME TO delivery_jobs;
CREATE TRIGGER job_origins_endpoint_matches_job BEFORE INSERT ON job_origins
  WHEN NOT EXISTS (SELECT 1 FROM delivery_jobs j WHERE j.id = NEW.job_id AND (
    EXISTS (SELECT 1 FROM destinations d WHERE d.ref = NEW.endpoint_ref AND d.identity_id = j.identity_id AND d.transport = j.transport)
    OR EXISTS (SELECT 1 FROM contact_points c WHERE c.ref = NEW.endpoint_ref AND c.identity_id = j.identity_id AND c.transport = j.transport)))
  BEGIN SELECT RAISE(ABORT, 'origin endpoint does not match its job'); END;
CREATE TRIGGER delivery_jobs_transport_matches_identity BEFORE INSERT ON delivery_jobs
  WHEN (SELECT transport FROM delivery_identities WHERE id = NEW.identity_id) IS NOT NEW.transport
  BEGIN SELECT RAISE(ABORT, 'job transport mismatch'); END;
CREATE TRIGGER jobs_binding_frozen BEFORE UPDATE OF ref, generation_id, transport, identity_id,
  idempotency_key, payload, payload_digest, skip_reason, redacted_at ON delivery_jobs
  WHEN NOT (NEW.ref IS OLD.ref AND NEW.generation_id IS OLD.generation_id AND NEW.transport IS OLD.transport
    AND NEW.identity_id IS OLD.identity_id AND NEW.idempotency_key IS OLD.idempotency_key
    AND NEW.payload_digest IS OLD.payload_digest AND NEW.skip_reason IS OLD.skip_reason
    AND OLD.redacted_at IS NULL AND NEW.redacted_at IS NOT NULL AND NEW.payload IS NULL)
  BEGIN SELECT RAISE(ABORT, 'job binding is frozen'); END;
-- A24 (Task C12): Bot API updates. One row: the update mode (polling or webhook, never both)
-- and the next getUpdates offset, which only moves forward and commits with each ingest.
CREATE TABLE bot_update_offset (id INTEGER PRIMARY KEY CHECK (id = 1),
  mode TEXT NOT NULL CHECK (mode IN ('polling','webhook')),
  next_offset INTEGER NOT NULL CHECK (next_offset >= 0), updated_at TEXT NOT NULL);
CREATE TRIGGER bot_update_offset_forward_only BEFORE UPDATE OF next_offset ON bot_update_offset
  WHEN NEW.next_offset < OLD.next_offset
  BEGIN SELECT RAISE(ABORT, 'the update offset only moves forward'); END;
CREATE TABLE bot_updates (update_id INTEGER PRIMARY KEY CHECK (update_id >= 0), chat_id INTEGER,
  kind TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE INDEX bot_updates_chat ON bot_updates (chat_id, update_id);
-- A42 (Task C15): a provider request key (the MTProto random_id) is written on the attempt in
-- the claim transaction, before the call. It is unique per transport actor across jobs; the
-- same job's later attempts reuse it (that is the dedupe). Set once. outcome_code names why an
-- attempt failed without a call (RANDOM_ID_COLLISION).
ALTER TABLE delivery_attempts ADD COLUMN provider_request_key TEXT;
ALTER TABLE delivery_attempts ADD COLUMN transport_actor TEXT;
ALTER TABLE delivery_attempts ADD COLUMN outcome_code TEXT;
CREATE INDEX delivery_attempts_request_key ON delivery_attempts (transport_actor, provider_request_key)
  WHERE provider_request_key IS NOT NULL;
CREATE TRIGGER attempts_request_key_set_once BEFORE UPDATE OF provider_request_key, transport_actor ON delivery_attempts
  WHEN OLD.provider_request_key IS NOT NULL OR OLD.transport_actor IS NOT NULL
    OR (NEW.provider_request_key IS NULL) <> (NEW.transport_actor IS NULL)
  BEGIN SELECT RAISE(ABORT, 'provider request key is frozen'); END;
CREATE TRIGGER attempts_request_key_scoped_unique BEFORE UPDATE OF provider_request_key ON delivery_attempts
  WHEN EXISTS (SELECT 1 FROM delivery_attempts a WHERE a.transport_actor = NEW.transport_actor
    AND a.provider_request_key = NEW.provider_request_key AND a.job_id <> NEW.job_id)
  BEGIN SELECT RAISE(ABORT, 'provider request key collision'); END;
-- A24 (Task C21): MTProto messages received on the session's update stream, retained once
-- each (event_ref = "<marked chat>:<message id>").
CREATE TABLE user_updates (event_ref TEXT PRIMARY KEY, chat_id TEXT NOT NULL, message_id INTEGER NOT NULL,
  kind TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE INDEX user_updates_chat ON user_updates (chat_id, message_id);
-- A22 (Task C23): the customer-service window, mirrored from webhook ingestion into state
-- Comms owns; it only moves forward. A23: a campaign's frozen template binding (one per
-- campaign; choosing among languages per recipient is Part D's).
CREATE TABLE endpoint_window (identity_id INTEGER PRIMARY KEY REFERENCES delivery_identities(id) ON DELETE RESTRICT,
  last_customer_message_at TEXT NOT NULL, observed_at TEXT NOT NULL, source_event_ref TEXT NOT NULL);
CREATE TABLE template_bindings (campaign_id INTEGER PRIMARY KEY REFERENCES campaigns(id) ON DELETE RESTRICT,
  name TEXT NOT NULL, language TEXT NOT NULL, schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
  parameters TEXT NOT NULL, bound_at TEXT NOT NULL);
-- A43 (Task C29): the durable webhook inbox. Verified raw bodies (inside SQLCipher), one row per
-- body digest; each fan-out effect has its own flag, set once, and completed_at closes the row.
CREATE TABLE webhook_inbox (id INTEGER PRIMARY KEY, provider_event_ref TEXT NOT NULL UNIQUE, received_at TEXT NOT NULL,
  body BLOB NOT NULL,
  archive_done INTEGER NOT NULL DEFAULT 0 CHECK (archive_done IN (0,1)),
  window_done INTEGER NOT NULL DEFAULT 0 CHECK (window_done IN (0,1)),
  status_done INTEGER NOT NULL DEFAULT 0 CHECK (status_done IN (0,1)),
  completed_at TEXT,
  CHECK (completed_at IS NULL OR (archive_done = 1 AND window_done = 1 AND status_done = 1)));
CREATE INDEX webhook_inbox_open ON webhook_inbox (id) WHERE completed_at IS NULL;
CREATE TRIGGER webhook_inbox_flags_forward BEFORE UPDATE ON webhook_inbox
  WHEN NEW.archive_done < OLD.archive_done OR NEW.window_done < OLD.window_done OR NEW.status_done < OLD.status_done
    OR (OLD.completed_at IS NOT NULL AND NEW.completed_at IS NOT OLD.completed_at)
    OR NEW.body IS NOT OLD.body OR NEW.provider_event_ref IS NOT OLD.provider_event_ref
  BEGIN SELECT RAISE(ABORT, 'webhook inbox rows only move forward'); END;
CREATE TRIGGER attempts_outcome_code_set_once BEFORE UPDATE OF outcome_code ON delivery_attempts
  WHEN OLD.outcome_code IS NOT NULL BEGIN SELECT RAISE(ABORT, 'outcome code is frozen'); END;
"""
SCHEMA_V3: tuple[str, ...] = _statements(_SCHEMA_V3_SQL)

# comms v0.3 Part D: assembled across Part D's tasks before the single merge.
_SCHEMA_V4_SQL = """
-- D7 (P §18): a person's display name, the owner's own label (never a provider identity).
ALTER TABLE recipients ADD COLUMN display_name TEXT;
-- D1 (design D.4): a group is one Telegram group or channel destination, one to one.
CREATE TABLE groups (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  destination_id INTEGER NOT NULL UNIQUE REFERENCES destinations(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL);
CREATE TRIGGER groups_are_group_destinations BEFORE INSERT ON groups
  WHEN (SELECT platform_identity FROM destinations WHERE id = NEW.destination_id) NOT GLOB 'group:*'
    AND (SELECT platform_identity FROM destinations WHERE id = NEW.destination_id) NOT GLOB 'channel:*'
  BEGIN SELECT RAISE(ABORT, 'not a group destination'); END;
CREATE TRIGGER groups_binding_immutable BEFORE UPDATE ON groups
  BEGIN SELECT RAISE(ABORT, 'a group mapping is immutable'); END;
-- D1b (G13): durable opaque refs for provider objects. The provider identity stays inside
-- SQLCipher; a binding never changes; only last_seen_at moves.
CREATE TABLE provider_objects (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL CHECK (kind IN ('message','invite','template','topic','media')),
  transport TEXT NOT NULL CHECK (transport IN ('telegram','whatsapp')), actor TEXT NOT NULL,
  destination_id INTEGER REFERENCES destinations(id) ON DELETE RESTRICT,
  provider_identity TEXT NOT NULL, created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL);
CREATE UNIQUE INDEX provider_objects_identity ON provider_objects
  (kind, transport, actor, ifnull(destination_id, 0), provider_identity);
CREATE TRIGGER provider_objects_binding_immutable BEFORE UPDATE OF ref, kind, transport, actor,
  destination_id, provider_identity, created_at ON provider_objects
  BEGIN SELECT RAISE(ABORT, 'a provider object binding is immutable'); END;
-- D3 (A28, A41, G14–G16): one row per write request, born IN_FLIGHT in the transaction that
-- validates it (PREPARED is deliberately not a stored state); request ids are opaque req_ refs,
-- unique per authenticated client; saga steps are persisted one by one.
CREATE TABLE mutations (id INTEGER PRIMARY KEY, op_ref TEXT NOT NULL UNIQUE,
  authenticated_client TEXT NOT NULL,
  request_id TEXT NOT NULL CHECK (length(request_id) = 30 AND substr(request_id, 1, 4) = 'req_'
    AND substr(request_id, 5) NOT GLOB '*[^a-z2-7]*'),
  request_digest TEXT NOT NULL CHECK (length(request_digest) = 64), tool TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('local','provider')), target_refs TEXT NOT NULL, actor TEXT,
  retry_class TEXT NOT NULL, ambiguity_policy TEXT NOT NULL CHECK (ambiguity_policy IN ('retry_same_key','resolve_only')),
  state TEXT NOT NULL CHECK (state IN ('IN_FLIGHT','SUCCEEDED','FAILED','OUTCOME_UNKNOWN')),
  audit_status TEXT NOT NULL DEFAULT 'ANCHORED' CHECK (audit_status IN ('ANCHORED','DEGRADED')),
  provider_request_key TEXT, provider_code TEXT, result TEXT, result_digest TEXT,
  retried INTEGER NOT NULL DEFAULT 0 CHECK (retried IN (0,1)), created_at TEXT NOT NULL, finished_at TEXT,
  UNIQUE (authenticated_client, request_id));
CREATE TABLE mutation_steps (id INTEGER PRIMARY KEY, mutation_id INTEGER NOT NULL REFERENCES mutations(id) ON DELETE RESTRICT,
  step_no INTEGER NOT NULL CHECK (step_no >= 1), capability TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING','IN_FLIGHT','SUCCEEDED','FAILED','OUTCOME_UNKNOWN')),
  provider_request_key TEXT, provider_code TEXT, UNIQUE (mutation_id, step_no));
-- D9 (A30, G13): the comms security epoch (bumped by a revocation; handles and cursors of an
-- older epoch are stale), client-bound ctx_ handles and key-versioned cur_ cursors.
CREATE TABLE security_epoch (id INTEGER PRIMARY KEY CHECK (id = 1), epoch INTEGER NOT NULL CHECK (epoch >= 1));
INSERT INTO security_epoch (id, epoch) VALUES (1, 1);
CREATE TRIGGER security_epoch_forward BEFORE UPDATE ON security_epoch WHEN NEW.epoch <= OLD.epoch
  BEGIN SELECT RAISE(ABORT, 'the security epoch only moves forward'); END;
CREATE TABLE ctx_handles (ref TEXT PRIMARY KEY, client TEXT NOT NULL, owner TEXT NOT NULL, security_epoch INTEGER NOT NULL,
  query_digest TEXT NOT NULL, target_ref TEXT NOT NULL, actor TEXT NOT NULL, snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE cursors (ref TEXT PRIMARY KEY, ctx_ref TEXT NOT NULL REFERENCES ctx_handles(ref) ON DELETE CASCADE,
  position TEXT NOT NULL, cursor_key_version INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
-- D27 (A33): local MCP clients; the daemon's seed copy is a cml1-client-seed key-slot version
CREATE TABLE clients (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  seed_version INTEGER NOT NULL UNIQUE CHECK (seed_version >= 1),
  created_at TEXT NOT NULL, rotated_at TEXT);
-- D32 (A35): OAuth refresh tokens, stored hashed; one family per authorization, rotated on use
CREATE TABLE oauth_refresh_tokens (id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64), family TEXT NOT NULL,
  client_id TEXT NOT NULL, subject TEXT NOT NULL, scopes TEXT NOT NULL, resource TEXT NOT NULL,
  security_epoch INTEGER NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0,1)),
  revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0,1)));
CREATE INDEX oauth_refresh_family ON oauth_refresh_tokens (family);
CREATE TRIGGER mutations_born_in_flight BEFORE INSERT ON mutations WHEN NEW.state <> 'IN_FLIGHT'
  BEGIN SELECT RAISE(ABORT, 'a mutation is born IN_FLIGHT'); END;
CREATE TRIGGER mutations_binding_immutable BEFORE UPDATE OF op_ref, authenticated_client, request_id,
  request_digest, tool, scope, target_refs, actor, retry_class, ambiguity_policy, created_at ON mutations
  BEGIN SELECT RAISE(ABORT, 'a mutation binding is immutable'); END;
CREATE TRIGGER mutations_state_forward BEFORE UPDATE OF state ON mutations
  WHEN NEW.state <> OLD.state AND NOT (
    (OLD.state = 'IN_FLIGHT' AND NEW.state IN ('SUCCEEDED','FAILED','OUTCOME_UNKNOWN'))
    OR (OLD.state = 'OUTCOME_UNKNOWN' AND NEW.state IN ('SUCCEEDED','FAILED')))
  BEGIN SELECT RAISE(ABORT, 'a mutation state only moves forward'); END;
CREATE TRIGGER mutations_request_key_set_once BEFORE UPDATE OF provider_request_key ON mutations
  WHEN OLD.provider_request_key IS NOT NULL AND NEW.provider_request_key IS NOT OLD.provider_request_key
  BEGIN SELECT RAISE(ABORT, 'the provider request key is set once'); END;
CREATE TRIGGER mutations_retried_once BEFORE UPDATE OF retried ON mutations WHEN OLD.retried = 1 AND NEW.retried <> 1
  BEGIN SELECT RAISE(ABORT, 'a mutation is re-invoked at most once'); END;
CREATE TRIGGER mutations_never_deleted BEFORE DELETE ON mutations
  BEGIN SELECT RAISE(ABORT, 'mutations are kept'); END;
CREATE TRIGGER mutation_steps_binding_immutable BEFORE UPDATE OF mutation_id, step_no, capability ON mutation_steps
  BEGIN SELECT RAISE(ABORT, 'a step binding is immutable'); END;
CREATE TRIGGER mutation_steps_state_forward BEFORE UPDATE OF state ON mutation_steps
  WHEN NEW.state <> OLD.state AND NOT (
    (OLD.state = 'PENDING' AND NEW.state IN ('IN_FLIGHT','FAILED'))
    OR (OLD.state = 'IN_FLIGHT' AND NEW.state IN ('SUCCEEDED','FAILED','OUTCOME_UNKNOWN'))
    OR (OLD.state = 'OUTCOME_UNKNOWN' AND NEW.state IN ('SUCCEEDED','FAILED')))
  BEGIN SELECT RAISE(ABORT, 'a step state only moves forward'); END;
CREATE TRIGGER mutation_steps_request_key_set_once BEFORE UPDATE OF provider_request_key ON mutation_steps
  WHEN OLD.provider_request_key IS NOT NULL AND NEW.provider_request_key IS NOT OLD.provider_request_key
  BEGIN SELECT RAISE(ABORT, 'the provider request key is set once'); END;
CREATE TRIGGER mutation_steps_never_deleted BEFORE DELETE ON mutation_steps
  BEGIN SELECT RAISE(ABORT, 'mutation steps are kept'); END;
"""
SCHEMA_V4: tuple[str, ...] = _statements(_SCHEMA_V4_SQL)

# D39-PRE E10b (owner decision, 2026-09-25): the comms-native WhatsApp archive. Webhook bodies
# are parsed with WhatsVault's public normaliser; each message is kept once by its semantic key
# and served as the ``whatsapp_webhook_archive`` context source. v4 shipped on main, so this is
# v5. Bodies age out with the other inbound bodies (``purge_inbound``).
_SCHEMA_V5_SQL = """
CREATE TABLE whatsapp_messages (id INTEGER PRIMARY KEY, semantic_key TEXT NOT NULL UNIQUE,
  phone_number_id TEXT, chat TEXT NOT NULL, sender_wa_id TEXT, wamid TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('in','out')), type TEXT NOT NULL, body TEXT,
  sender_name TEXT, sent_at TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE INDEX whatsapp_messages_by_chat ON whatsapp_messages (chat, sent_at, id);
"""
SCHEMA_V5: tuple[str, ...] = _statements(_SCHEMA_V5_SQL)

# Catalog amendment G1 (A45): WhatsApp groups are destinations. The destinations CHECK allowed
# Telegram only, so the table is rebuilt (the 5b-3 method, foreign keys off) to allow a
# ``whatsapp`` destination whose identity is a group (``group:<id>``, or ``redacted:<id>`` once
# A15 redacts it); a WhatsApp contact stays a person's contact point. Every index and trigger
# that names the table (measured from a v5 database) is recreated verbatim.
_SCHEMA_V6_SQL = """
CREATE TABLE destinations_v6 (id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  transport TEXT NOT NULL CHECK (transport = 'telegram' OR (transport = 'whatsapp'
    AND (platform_identity GLOB 'group:?*' OR platform_identity GLOB 'redacted:?*'))),
  platform_identity TEXT NOT NULL,
  identity_id INTEGER NOT NULL REFERENCES delivery_identities(id) ON DELETE RESTRICT,
  display_name TEXT NOT NULL, capabilities TEXT NOT NULL DEFAULT '{}',
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), created_at TEXT NOT NULL, disabled_at TEXT);
INSERT INTO destinations_v6 (id, ref, location_id, transport, platform_identity, identity_id,
  display_name, capabilities, enabled, created_at, disabled_at)
  SELECT id, ref, location_id, transport, platform_identity, identity_id, display_name, capabilities,
    enabled, created_at, disabled_at FROM destinations;
DROP TRIGGER groups_are_group_destinations;
DROP TRIGGER job_origins_endpoint_matches_job;
DROP TABLE destinations;
ALTER TABLE destinations_v6 RENAME TO destinations;
CREATE INDEX destinations_location ON destinations (location_id);
CREATE UNIQUE INDEX destinations_one_enabled_per_identity ON destinations (identity_id) WHERE enabled = 1;
CREATE TRIGGER destinations_identity_immutable BEFORE UPDATE OF transport, platform_identity, identity_id, location_id, ref
  ON destinations WHEN NOT (NEW.transport IS OLD.transport AND NEW.identity_id IS OLD.identity_id
    AND NEW.location_id IS OLD.location_id AND NEW.ref IS OLD.ref
    AND NEW.platform_identity = 'redacted:' || OLD.identity_id)
  BEGIN SELECT RAISE(ABORT, 'destination identity is immutable'); END;
CREATE TRIGGER destinations_never_deleted BEFORE DELETE ON destinations
  BEGIN SELECT RAISE(ABORT, 'endpoints are disabled, never deleted'); END;
CREATE TRIGGER destinations_transport_matches_identity BEFORE INSERT ON destinations
  WHEN (SELECT transport FROM delivery_identities WHERE id = NEW.identity_id) IS NOT NEW.transport
  BEGIN SELECT RAISE(ABORT, 'endpoint transport mismatch'); END;
CREATE TRIGGER groups_are_group_destinations BEFORE INSERT ON groups
  WHEN (SELECT platform_identity FROM destinations WHERE id = NEW.destination_id) NOT GLOB 'group:*'
    AND (SELECT platform_identity FROM destinations WHERE id = NEW.destination_id) NOT GLOB 'channel:*'
  BEGIN SELECT RAISE(ABORT, 'not a group destination'); END;
CREATE TRIGGER job_origins_endpoint_matches_job BEFORE INSERT ON job_origins
  WHEN NOT EXISTS (SELECT 1 FROM delivery_jobs j WHERE j.id = NEW.job_id AND (
    EXISTS (SELECT 1 FROM destinations d WHERE d.ref = NEW.endpoint_ref AND d.identity_id = j.identity_id AND d.transport = j.transport)
    OR EXISTS (SELECT 1 FROM contact_points c WHERE c.ref = NEW.endpoint_ref AND c.identity_id = j.identity_id AND c.transport = j.transport)))
  BEGIN SELECT RAISE(ABORT, 'origin endpoint does not match its job'); END;
"""
SCHEMA_V6: tuple[str, ...] = _statements(_SCHEMA_V6_SQL)

# Catalog amendment G8: a WhatsApp group is created asynchronously (Meta answers a request id; the
# group id arrives in a group_lifecycle_update webhook carrying it). The pending creation keeps
# where the group belongs until the webhook files it as a destination; nothing is ever deleted.
_SCHEMA_V7_SQL = """
CREATE TABLE pending_group_creations (id INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
  location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  name TEXT NOT NULL, created_at TEXT NOT NULL,
  destination_id INTEGER REFERENCES destinations(id) ON DELETE RESTRICT,
  failed_at TEXT, CHECK (destination_id IS NULL OR failed_at IS NULL));
CREATE TRIGGER pending_group_creations_settle_once BEFORE UPDATE ON pending_group_creations
  WHEN OLD.destination_id IS NOT NULL OR OLD.failed_at IS NOT NULL
    OR NEW.request_id IS NOT OLD.request_id OR NEW.location_id IS NOT OLD.location_id
  BEGIN SELECT RAISE(ABORT, 'a pending group creation settles once'); END;
CREATE TRIGGER pending_group_creations_kept BEFORE DELETE ON pending_group_creations
  BEGIN SELECT RAISE(ABORT, 'pending group creations are kept'); END;
"""
SCHEMA_V7: tuple[str, ...] = _statements(_SCHEMA_V7_SQL)

# Spec A47 (H2, Gx8): what a ``med_`` is — its kind, MIME type and size, and where it came from.
# ``provider_objects`` binds a ref to its identity immutably and has no room for these; no file
# id or file reference is kept here (Gx9): the source that holds one is read when it is used.
_SCHEMA_V8_SQL = """
CREATE TABLE media_facts (object_id INTEGER PRIMARY KEY REFERENCES provider_objects(id) ON DELETE CASCADE,
  media_kind TEXT NOT NULL CHECK (media_kind IN ('photo', 'document')),
  mime TEXT NOT NULL CHECK (length(mime) BETWEEN 3 AND 128),
  size INTEGER CHECK (size IS NULL OR size >= 0),
  origin TEXT NOT NULL CHECK (origin IN ('telegram_message', 'telegram_bot_update', 'telegram_upload')),
  recorded_at TEXT NOT NULL);
"""
SCHEMA_V8: tuple[str, ...] = _statements(_SCHEMA_V8_SQL)

# Spec A48 (R3): the relay collector's durable state. One row of progress; the rows the daemon
# refused (kept, since an ack is cumulative); and each gap the relay's numbering showed.
_SCHEMA_V9_SQL = """
CREATE TABLE relay_state (id INTEGER PRIMARY KEY CHECK (id = 1),
  acked_through INTEGER NOT NULL DEFAULT 0 CHECK (acked_through >= 0),
  purged_through INTEGER NOT NULL DEFAULT 0 CHECK (purged_through >= 0),
  depth INTEGER CHECK (depth IS NULL OR depth >= 0),
  oldest_received_at TEXT,
  last_attempt_at TEXT,
  last_success_at TEXT,
  last_error TEXT CHECK (last_error IS NULL OR last_error IN ('unreachable', 'refused', 'clock', 'malformed')),
  clock_skew_s INTEGER);
CREATE TRIGGER relay_state_forward BEFORE UPDATE ON relay_state
  WHEN NEW.acked_through < OLD.acked_through OR NEW.purged_through < OLD.purged_through
  BEGIN SELECT RAISE(ABORT, 'relay progress only moves forward'); END;
CREATE TABLE relay_quarantine (seq INTEGER PRIMARY KEY CHECK (seq >= 1),
  reason TEXT NOT NULL CHECK (reason IN ('decrypt', 'envelope', 'signature', 'parts')),
  ciphertext_sha256 TEXT NOT NULL CHECK (length(ciphertext_sha256) = 64),
  ciphertext BLOB,
  quarantined_at TEXT NOT NULL);
CREATE TABLE relay_gaps (id INTEGER PRIMARY KEY,
  from_seq INTEGER NOT NULL CHECK (from_seq >= 1),
  to_seq INTEGER NOT NULL CHECK (to_seq >= from_seq),
  found_at TEXT NOT NULL);
"""
SCHEMA_V9: tuple[str, ...] = _statements(_SCHEMA_V9_SQL)

# Proposed A49 (Instagram, R-IG2): three tables of its own, so no existing table, trigger or
# CHECK changes. An account row binds a ref to its alias and Instagram user id; at most one live
# row per alias and per user id, and the binding never changes (a removed account keeps its
# row, removed). A container row is the 400-container ledger (section 6). An object row is one
# opaque ref per (account, kind, provider identity): media, comment, or a DM counterpart.
_SCHEMA_V10_SQL = """
CREATE TABLE instagram_accounts (id INTEGER PRIMARY KEY,
  ref TEXT NOT NULL UNIQUE CHECK (length(ref) = 30 AND substr(ref, 1, 4) = 'iga_'),
  alias TEXT NOT NULL CHECK (length(alias) BETWEEN 1 AND 32 AND alias NOT GLOB '*[^a-z0-9_-]*'),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 1 AND 20 AND user_id NOT GLOB '*[^0-9]*'),
  obtained_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_identity_check_at TEXT,
  created_at TEXT NOT NULL, removed_at TEXT);
CREATE UNIQUE INDEX instagram_accounts_live_alias ON instagram_accounts (alias) WHERE removed_at IS NULL;
CREATE UNIQUE INDEX instagram_accounts_live_user ON instagram_accounts (user_id) WHERE removed_at IS NULL;
CREATE TRIGGER instagram_accounts_binding_immutable BEFORE UPDATE OF ref, alias, user_id, created_at
  ON instagram_accounts BEGIN SELECT RAISE(ABORT, 'instagram account binding is immutable'); END;
CREATE TRIGGER instagram_accounts_removal_final BEFORE UPDATE OF removed_at ON instagram_accounts
  WHEN OLD.removed_at IS NOT NULL BEGIN SELECT RAISE(ABORT, 'a removed account stays removed'); END;
CREATE TABLE instagram_containers (id INTEGER PRIMARY KEY,
  ref TEXT NOT NULL UNIQUE CHECK (length(ref) = 30 AND substr(ref, 1, 4) = 'igk_'),
  account_id INTEGER NOT NULL REFERENCES instagram_accounts(id) ON DELETE RESTRICT,
  kind TEXT NOT NULL CHECK (kind IN ('image', 'reel', 'carousel', 'child')),
  creation_id TEXT NOT NULL CHECK (length(creation_id) BETWEEN 1 AND 20 AND creation_id NOT GLOB '*[^0-9]*'),
  created_at TEXT NOT NULL,
  status TEXT CHECK (status IS NULL OR status IN ('IN_PROGRESS', 'FINISHED', 'ERROR', 'EXPIRED', 'PUBLISHED')),
  media_ref TEXT CHECK (media_ref IS NULL OR (length(media_ref) = 30 AND substr(media_ref, 1, 4) = 'igm_')),
  UNIQUE (account_id, creation_id));
CREATE INDEX instagram_containers_recent ON instagram_containers (account_id, created_at);
CREATE TRIGGER instagram_containers_binding_immutable BEFORE UPDATE OF ref, account_id, kind, creation_id, created_at
  ON instagram_containers BEGIN SELECT RAISE(ABORT, 'instagram container binding is immutable'); END;
CREATE TABLE instagram_objects (id INTEGER PRIMARY KEY,
  ref TEXT NOT NULL UNIQUE CHECK (length(ref) = 30 AND substr(ref, 1, 4) IN ('igm_', 'igc_', 'igp_')),
  account_id INTEGER NOT NULL REFERENCES instagram_accounts(id) ON DELETE RESTRICT,
  kind TEXT NOT NULL CHECK (kind IN ('media', 'comment', 'person')),
  provider_identity TEXT NOT NULL CHECK (length(provider_identity) BETWEEN 1 AND 64),
  created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
  UNIQUE (account_id, kind, provider_identity));
CREATE TRIGGER instagram_objects_binding_immutable BEFORE UPDATE OF ref, account_id, kind, provider_identity, created_at
  ON instagram_objects BEGIN SELECT RAISE(ABORT, 'instagram object binding is immutable'); END;
"""
SCHEMA_V10: tuple[str, ...] = _statements(_SCHEMA_V10_SQL)

MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, SCHEMA_V1),
    Migration(2, SCHEMA_V2),
    Migration(3, SCHEMA_V3, rebuild=True),
    Migration(4, SCHEMA_V4),
    Migration(5, SCHEMA_V5),
    Migration(6, SCHEMA_V6, rebuild=True),
    Migration(7, SCHEMA_V7),
    Migration(8, SCHEMA_V8),
    Migration(9, SCHEMA_V9),
    Migration(10, SCHEMA_V10),  # proposed A49
)


def migrate(conn: Any, migrations: tuple[Migration, ...] = MIGRATIONS) -> int:
    """Apply every migration not yet recorded; return the resulting version."""
    if [m.version for m in migrations] != list(range(1, len(migrations) + 1)):
        raise ValueError("migrations must be numbered 1..n in order")
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    done = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
    prior_fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    for migration in migrations:
        if migration.version in done:
            continue
        if migration.rebuild:
            conn.execute("PRAGMA foreign_keys = OFF")  # outside the transaction, or it is ignored
        try:
            with write_tx(conn):
                for statement in migration.statements:
                    conn.execute(statement)
                if migration.rebuild and conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("foreign key check failed after rebuild")
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (migration.version,)
                )
        finally:
            if migration.rebuild:
                conn.execute(f"PRAGMA foreign_keys = {'ON' if prior_fk else 'OFF'}")
    row = conn.execute("SELECT max(version) FROM schema_version").fetchone()
    return int(row[0] or 0)
