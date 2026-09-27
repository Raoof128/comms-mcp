// Spec A48 (Task R2): the relay Worker and its Mailbox, run inside workerd.
import { env, exports } from "cloudflare:workers";
import { evictDurableObject, reset, runDurableObjectAlarm, runInDurableObject } from "cloudflare:test";
import { afterEach, describe, expect, it } from "vitest";
import wranglerConfig from "../wrangler.jsonc?raw";
import vectors from "../../tests/fixtures/relay/pull_signature_vectors.json";
import * as main from "../src/index";
import { MAX_BODY_BYTES, PART_BYTES, RETENTION_MS } from "../src/limits";
import type { Mailbox } from "../src/mailbox";
import { hexToBytes, sign, verify } from "../src/pull_sig";
import { BODY, HOOK, SIG, control, open, post } from "./fixtures";

afterEach(async () => {
  await reset(); // every test starts from an empty mailbox
});

const stub = () => env.MAILBOX.get(env.MAILBOX.idFromName("mailbox"));

async function pullAll(after = 0) {
  const response = await control("/pull", { after, limit: 50 });
  expect(response.status).toBe(200);
  return (await response.json()) as {
    rows: { seq: number; batch: string; part: number; parts: number; received_at: number; ciphertext_b64: string }[];
    purged_through: number;
    depth: number;
    oldest_received_at: number | null;
  };
}

describe("the webhook path", () => {
  it("stores a delivery encrypted to the daemon, with its signature header", async () => {
    expect((await post(HOOK, BODY)).status).toBe(200);
    const page = await pullAll();
    expect(page.rows).toHaveLength(1);
    const plain = await open(page.rows[0].ciphertext_b64);
    expect(Object.keys(plain)).toEqual(["batch", "part", "parts", "raw_b64", "received_at", "signature"]);
    expect(atob(plain.raw_b64 as string)).toBe(BODY);
    expect(plain.signature).toBe(SIG);
    expect(plain.part).toBe(0);
    expect(plain.parts).toBe(1);
    expect(plain.batch).toBe(page.rows[0].batch);
    expect(page.depth).toBe(1);
  });

  it("refuses in order: path token, content type, signature format, size", async () => {
    const wrong = HOOK.slice(0, -1) + (HOOK.endsWith("A") ? "B" : "A");
    expect((await post(wrong, BODY)).status).toBe(404);
    expect((await post(`${HOOK}x`, BODY)).status).toBe(404);
    expect((await post(wrong, BODY, { "content-type": "text/plain" })).status).toBe(404);
    expect((await post(HOOK, BODY, { "content-type": "text/plain" })).status).toBe(415);
    expect((await post(HOOK, BODY, { "x-hub-signature-256": "sha256=zz" })).status).toBe(401);
    expect((await post(HOOK, BODY, { "x-hub-signature-256": "sha1=" + "ab".repeat(20) })).status).toBe(401);
    expect((await post(HOOK, BODY, { "x-hub-signature-256": SIG, "content-type": "text/json" })).status).toBe(415);
    const big = new Uint8Array(MAX_BODY_BYTES + 1);
    expect((await post(HOOK, big)).status).toBe(413);
    expect((await pullAll()).rows).toHaveLength(0);
  });

  it("answers the verify handshake and never stores it", async () => {
    const q = "hub.mode=subscribe&hub.verify_token=test-verify-token&hub.challenge=1158201444";
    const good = await exports.default.fetch(new Request(`${HOOK}?${q}`));
    expect(good.status).toBe(200);
    expect(await good.text()).toBe("1158201444");
    const bad = await exports.default.fetch(new Request(`${HOOK}?${q.replace("test-verify-token", "nope")}`));
    expect(bad.status).toBe(403);
    expect((await pullAll()).rows).toHaveLength(0);
  });

  it("answers 503 when the mailbox cannot store, so Meta retries", async () => {
    await runInDurableObject(stub(), (instance: Mailbox) => {
      // The encryption fails inside the Durable Object: nothing is stored.
      (instance as unknown as { env: Env }).env = { ...env, RELAY_AGE_RECIPIENT: "age1broken" };
    });
    expect((await post(HOOK, BODY)).status).toBe(503);
    expect((await pullAll()).depth).toBe(0);
  });

  it("bounds the rate, and a refused delivery stores nothing", async () => {
    const codes: number[] = [];
    for (let i = 0; i < 62; i++) codes.push((await post(HOOK, `{"n":${i}}`)).status);
    expect(codes.slice(0, 60).every((c) => c === 200)).toBe(true);
    expect(codes.slice(60)).toEqual([429, 429]);
    expect((await pullAll()).depth).toBe(60);
  });

  it("stores a batch over 1 MiB as parts that reassemble to the exact bytes", async () => {
    const size = Math.floor(2.5 * PART_BYTES);
    const raw = new Uint8Array(size);
    for (let i = 0; i < size; i++) raw[i] = (i * 31 + 7) & 0xff;
    expect((await post(HOOK, raw)).status).toBe(200);
    const rows = [];
    let after = 0;
    for (;;) {
      const page = await pullAll(after);
      if (page.rows.length === 0) break;
      rows.push(...page.rows);
      after = page.rows[page.rows.length - 1].seq;
    }
    expect(rows.map((r) => [r.part, r.parts])).toEqual([
      [0, 3],
      [1, 3],
      [2, 3],
    ]);
    expect(new Set(rows.map((r) => r.batch)).size).toBe(1);
    const joined = new Uint8Array(size);
    let at = 0;
    for (const r of rows) {
      const slice = atob((await open(r.ciphertext_b64)).raw_b64 as string);
      for (let i = 0; i < slice.length; i++) joined[at++] = slice.charCodeAt(i);
    }
    expect(at).toBe(size);
    expect(joined).toEqual(raw);
  }, 30_000); // 2.5 MiB encrypted and decrypted: heavy under load (R-R2); a Durable Object gets 30 s
});

describe("pull and ack", () => {
  it("refuses a bad, stale or foreign signature", async () => {
    expect((await control("/pull", { after: 0, limit: 1 }, { tamper: true })).status).toBe(401);
    // Clearly outside and inside the window: the two sides read the clock a moment apart, so
    // the exact 300 s boundary is pinned against verify() with an explicit clock below.
    expect((await control("/pull", { after: 0, limit: 1 }, { skew: 330 })).status).toBe(401);
    expect((await control("/pull", { after: 0, limit: 1 }, { skew: -330 })).status).toBe(401);
    expect((await control("/pull", { after: 0, limit: 1 }, { skew: 270 })).status).toBe(200);
    expect((await control("/ack", { through: 9 }, { key: "00".repeat(32) })).status).toBe(401);
    expect((await control("/pull", { after: -1, limit: 1 })).status).toBe(400);
    expect((await control("/pull", { after: 0, limit: 51 })).status).toBe(400);
    expect((await control("/ack", { through: "9" })).status).toBe(400);
  });

  it("accepts exactly 300 s of skew either way, and not 301", async () => {
    const key = env.RELAY_PULL_KEY;
    const body = new TextEncoder().encode("{}");
    const signed = await sign(hexToBytes(key), "POST", "/ack", "1000", body);
    for (const [now, ok] of [[1300, true], [700, true], [1301, false], [699, false]] as const) {
      expect(await verify(key, "POST", "/ack", "1000", body, signed, now)).toBe(ok);
    }
    expect(await verify(key, "POST", "/ack", "01000", body, signed, 1000)).toBe(false);
    expect(await verify(key, "POST", "/ack", "1000", body, signed.toUpperCase(), 1000)).toBe(false);
  });

  it("acks idempotently and keeps rows after the acked seq", async () => {
    for (let i = 0; i < 3; i++) expect((await post(HOOK, `{"n":${i}}`)).status).toBe(200);
    const [a, b, c] = (await pullAll()).rows;
    const first = await control("/ack", { through: b.seq });
    expect(await first.json()).toEqual({ deleted: 2 });
    const again = await control("/ack", { through: b.seq });
    expect(await again.json()).toEqual({ deleted: 0 });
    expect((await pullAll()).rows.map((r) => r.seq)).toEqual([c.seq]);
    expect(a.seq < b.seq && b.seq < c.seq).toBe(true);
  });

  it("never reuses a seq after a full drain (AUTOINCREMENT)", async () => {
    await post(HOOK, BODY);
    const first = (await pullAll()).rows[0].seq;
    await control("/ack", { through: first });
    expect((await pullAll()).depth).toBe(0);
    await post(HOOK, BODY);
    expect((await pullAll()).rows[0].seq).toBeGreaterThan(first);
  });

  it("survives eviction", async () => {
    await post(HOOK, BODY);
    await evictDurableObject(stub());
    const page = await pullAll();
    expect(page.rows).toHaveLength(1);
    expect(atob((await open(page.rows[0].ciphertext_b64)).raw_b64 as string)).toBe(BODY);
  });

  it("purges rows older than 30 days and reports purged_through", async () => {
    await post(HOOK, '{"old":1}');
    await post(HOOK, '{"old":2}');
    await post(HOOK, '{"new":1}');
    const [old1, old2, fresh] = (await pullAll()).rows;
    await runInDurableObject(stub(), (_instance: Mailbox, state: DurableObjectState) => {
      state.storage.sql.exec(
        "UPDATE mail SET received_at = ? WHERE seq <= ?",
        Date.now() - RETENTION_MS - 1000,
        old2.seq,
      );
    });
    expect(await runDurableObjectAlarm(stub())).toBe(true);
    const page = await pullAll();
    expect(page.rows.map((r) => r.seq)).toEqual([fresh.seq]);
    expect(page.purged_through).toBe(old2.seq);
    expect(old1.seq).toBeLessThan(old2.seq);
  });
});

describe("the frozen wire and D-R1", () => {
  it("reproduces every shared pull-signature vector", async () => {
    for (const v of vectors) {
      expect(await sign(hexToBytes(v.key), v.method, v.path, String(v.timestamp), hexToBytes(v.body))).toBe(v.signature);
    }
  });

  it("exports only what workerd accepts from a main module", () => {
    // Found by running `wrangler dev`: a constant exported here stops the runtime from starting.
    expect(Object.keys(main).sort()).toEqual(["Mailbox", "default"]);
  });

  it("holds no Meta app secret", () => {
    const names = Object.keys(env).filter((n) => !n.startsWith("__VITEST_POOL_WORKERS_"));
    expect(names.sort()).toEqual(["MAILBOX", "META_VERIFY_TOKEN", "RELAY_AGE_RECIPIENT", "RELAY_PATH_TOKEN", "RELAY_PULL_KEY"]);
    expect(/app[_-]?secret/i.test(wranglerConfig)).toBe(false);
  });
});
