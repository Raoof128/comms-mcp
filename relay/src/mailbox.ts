// The Mailbox (spec A48): one SQLite Durable Object holding age ciphertext for the daemon.
//
// Encryption happens here, not in the Worker: a Durable Object request has 30 s of CPU, a free
// Worker 10 ms. `seq` is AUTOINCREMENT so it never repeats after a drain. A daily alarm purges
// rows older than 30 days and raises `purged_through`, so a purge is never mistaken for a loss.
import { DurableObject } from "cloudflare:workers";
import * as age from "age-encryption";
import { PAGE_BYTES, PAGE_ROWS, PART_BYTES, RETENTION_MS } from "./limits";

const DAY_MS = 24 * 60 * 60 * 1000;
// A single mailbox, so an in-memory bucket is exact. It resets on eviction, which only loosens
// it; Meta retries a refused delivery for 36 hours.
const BUCKET_CAPACITY = 60;
const BUCKET_PER_SECOND = 0.5;

export interface Row {
  seq: number;
  received_at: number;
  batch: string;
  part: number;
  parts: number;
  ciphertext_b64: string;
}

export interface Page {
  rows: Row[];
  purged_through: number;
  depth: number;
  oldest_received_at: number | null;
}

function b64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function randomBatch(): string {
  const raw = crypto.getRandomValues(new Uint8Array(16));
  return [...raw].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Canonical JSON (TG-JCS-v1 for this shape: sorted ASCII keys, no whitespace, integers). */
function envelope(fields: {
  batch: string;
  part: number;
  parts: number;
  raw_b64: string;
  received_at: number;
  signature: string;
}): Uint8Array {
  const text =
    `{"batch":${JSON.stringify(fields.batch)},"part":${fields.part},"parts":${fields.parts},` +
    `"raw_b64":${JSON.stringify(fields.raw_b64)},"received_at":${fields.received_at},` +
    `"signature":${JSON.stringify(fields.signature)}}`;
  return new TextEncoder().encode(text);
}

export class Mailbox extends DurableObject<Env> {
  private tokens = BUCKET_CAPACITY;
  private refilled = Date.now();

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      ctx.storage.sql.exec(
        `CREATE TABLE IF NOT EXISTS mail (
           seq INTEGER PRIMARY KEY AUTOINCREMENT,
           received_at INTEGER NOT NULL,
           batch TEXT NOT NULL,
           part INTEGER NOT NULL,
           parts INTEGER NOT NULL,
           ciphertext BLOB NOT NULL)`,
      );
      ctx.storage.sql.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v INTEGER NOT NULL)");
      if ((await ctx.storage.getAlarm()) === null) await ctx.storage.setAlarm(Date.now() + DAY_MS);
    });
  }

  private takeToken(): boolean {
    const now = Date.now();
    this.tokens = Math.min(BUCKET_CAPACITY, this.tokens + ((now - this.refilled) / 1000) * BUCKET_PER_SECOND);
    this.refilled = now;
    if (this.tokens < 1) return false;
    this.tokens -= 1;
    return true;
  }

  /** 200 once every part is stored, 429 when the rate bound refuses it. */
  async store(raw: ArrayBuffer, signature: string): Promise<200 | 429> {
    if (!this.takeToken()) return 429;
    const bytes = new Uint8Array(raw);
    const parts = Math.max(1, Math.ceil(bytes.length / PART_BYTES));
    const batch = randomBatch();
    const received_at = Date.now();
    const sealed: Uint8Array[] = [];
    for (let part = 0; part < parts; part++) {
      const slice = bytes.subarray(part * PART_BYTES, (part + 1) * PART_BYTES);
      const e = new age.Encrypter();
      e.addRecipient(this.env.RELAY_AGE_RECIPIENT);
      sealed.push(await e.encrypt(envelope({ batch, part, parts, raw_b64: b64(slice), received_at, signature })));
    }
    this.ctx.storage.transactionSync(() => {
      sealed.forEach((ciphertext, part) =>
        this.ctx.storage.sql.exec(
          "INSERT INTO mail (received_at, batch, part, parts, ciphertext) VALUES (?, ?, ?, ?, ?)",
          received_at,
          batch,
          part,
          parts,
          ciphertext,
        ),
      );
    });
    return 200;
  }

  private meta(k: string): number {
    const row = this.ctx.storage.sql.exec<{ v: number }>("SELECT v FROM meta WHERE k = ?", k).toArray()[0];
    return row ? row.v : 0;
  }

  pull(after: number, limit: number): Page {
    const rows: Row[] = [];
    let bytes = 0;
    const cursor = this.ctx.storage.sql.exec<{
      seq: number;
      received_at: number;
      batch: string;
      part: number;
      parts: number;
      ciphertext: ArrayBuffer;
    }>(
      "SELECT seq, received_at, batch, part, parts, ciphertext FROM mail WHERE seq > ? ORDER BY seq LIMIT ?",
      after,
      Math.min(limit, PAGE_ROWS),
    );
    for (const r of cursor) {
      if (rows.length > 0 && bytes + r.ciphertext.byteLength > PAGE_BYTES) break;
      bytes += r.ciphertext.byteLength;
      const { ciphertext, ...rest } = r;
      rows.push({ ...rest, ciphertext_b64: b64(new Uint8Array(ciphertext)) });
    }
    const stats = this.ctx.storage.sql
      .exec<{ depth: number; oldest: number | null }>("SELECT count(*) AS depth, min(received_at) AS oldest FROM mail")
      .one();
    return { rows, purged_through: this.meta("purged_through"), depth: stats.depth, oldest_received_at: stats.oldest };
  }

  /** Deletes every row with seq <= through; repeating it deletes nothing new. */
  ack(through: number): number {
    return this.ctx.storage.sql.exec("DELETE FROM mail WHERE seq <= ?", through).rowsWritten;
  }

  async alarm(): Promise<void> {
    const cutoff = Date.now() - RETENTION_MS;
    const purged = this.ctx.storage.sql
      .exec<{ top: number | null }>("SELECT max(seq) AS top FROM mail WHERE received_at < ?", cutoff)
      .one().top;
    if (purged !== null) {
      this.ctx.storage.transactionSync(() => {
        this.ctx.storage.sql.exec("DELETE FROM mail WHERE seq <= ?", purged);
        this.ctx.storage.sql.exec(
          "INSERT INTO meta (k, v) VALUES ('purged_through', ?) ON CONFLICT(k) DO UPDATE SET v = max(v, excluded.v)",
          purged,
        );
      });
    }
    await this.ctx.storage.setAlarm(Date.now() + DAY_MS);
  }
}
