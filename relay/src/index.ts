// The comms relay Worker (spec A48): Meta's webhooks in, signed pulls out.
//
// D-R1: the Worker holds no Meta app secret. What arrives on the secret path is stored
// unverified, encrypted to the daemon; the daemon is the only verifier. Refusals, in order:
// wrong path token 404; content type other than JSON 415; a missing or malformed
// X-Hub-Signature-256 401 (format only); a body over 8 MiB 413; the rate bound 429. The answer is
// 200 only after the Mailbox stored every part, and 503 otherwise, so Meta retries.
import { MAX_BODY_BYTES, PAGE_ROWS } from "./limits";
import { Mailbox } from "./mailbox";
import { constantTimeEqual, verify } from "./pull_sig";

export { Mailbox };

const HOOK_PREFIX = "/webhooks/meta/";
const SIGNATURE = /^sha256=[0-9a-f]{64}$/;
const PATH_TOKEN = /^[A-Za-z0-9_-]{43}$/; // 32 random bytes, base64url
const RECIPIENT = /^age1[02-9ac-hj-np-z]{58}$/;
const MAX_CONTROL_BODY = 1024;

function status(code: number): Response {
  return new Response(null, { status: code });
}

function mailbox(env: Env): DurableObjectStub<Mailbox> {
  return env.MAILBOX.get(env.MAILBOX.idFromName("mailbox"));
}

function configured(env: Env): boolean {
  return (
    PATH_TOKEN.test(env.RELAY_PATH_TOKEN ?? "") &&
    /^[0-9a-f]{64}$/.test(env.RELAY_PULL_KEY ?? "") &&
    RECIPIENT.test(env.RELAY_AGE_RECIPIENT ?? "") &&
    (env.META_VERIFY_TOKEN ?? "").length > 0
  );
}

async function readCapped(request: Request, cap: number): Promise<Uint8Array | null> {
  if (request.body === null) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > cap) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.byteLength;
  }
  return out;
}

async function hook(request: Request, env: Env, token: string): Promise<Response> {
  if (!(await constantTimeEqual(token, env.RELAY_PATH_TOKEN))) return status(404);
  if (request.method === "GET") {
    const q = new URL(request.url).searchParams;
    const given = q.get("hub.verify_token");
    const challenge = q.get("hub.challenge");
    if (q.get("hub.mode") !== "subscribe" || given === null || challenge === null) return status(403);
    if (!(await constantTimeEqual(given, env.META_VERIFY_TOKEN))) return status(403);
    return new Response(challenge, { status: 200, headers: { "content-type": "text/plain" } });
  }
  if (request.method !== "POST") return status(405);
  const type = (request.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
  if (type !== "application/json") return status(415);
  const signature = request.headers.get("x-hub-signature-256");
  if (signature === null || !SIGNATURE.test(signature)) return status(401);
  const declared = request.headers.get("content-length");
  if (declared !== null && (!/^[0-9]+$/.test(declared) || Number(declared) > MAX_BODY_BYTES)) return status(413);
  const raw = await readCapped(request, MAX_BODY_BYTES);
  if (raw === null) return status(413);
  try {
    return status(await mailbox(env).store(raw.buffer as ArrayBuffer, signature));
  } catch {
    return status(503); // not stored, so not acknowledged: Meta retries
  }
}

function integerField(value: unknown, max: number): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max ? value : null;
}

async function control(request: Request, env: Env, path: "/pull" | "/ack"): Promise<Response> {
  if (request.method !== "POST") return status(405);
  const body = await readCapped(request, MAX_CONTROL_BODY);
  if (body === null) return status(413);
  const ok = await verify(
    env.RELAY_PULL_KEY,
    "POST",
    path,
    request.headers.get("x-comms-timestamp"),
    body,
    request.headers.get("x-comms-signature"),
    Math.floor(Date.now() / 1000),
  );
  if (!ok) return status(401);
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(body));
  } catch {
    return status(400);
  }
  const fields = (parsed ?? {}) as Record<string, unknown>;
  if (path === "/pull") {
    const after = integerField(fields.after, Number.MAX_SAFE_INTEGER);
    const limit = integerField(fields.limit, PAGE_ROWS);
    if (after === null || limit === null || limit < 1) return status(400);
    return Response.json(await mailbox(env).pull(after, limit));
  }
  const through = integerField(fields.through, Number.MAX_SAFE_INTEGER);
  if (through === null) return status(400);
  return Response.json({ deleted: await mailbox(env).ack(through) });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!configured(env)) return status(503);
    const { pathname } = new URL(request.url);
    if (pathname.startsWith(HOOK_PREFIX)) return hook(request, env, pathname.slice(HOOK_PREFIX.length));
    if (pathname === "/pull" || pathname === "/ack") return control(request, env, pathname);
    return status(404);
  },
} satisfies ExportedHandler<Env>;
