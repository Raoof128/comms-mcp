// The relay's pull signature (spec A48): the TypeScript copy. The Python copy is
// src/comms/core/relay_sig.py; tests/fixtures/relay/pull_signature_vectors.json binds the two.
//
// hex(HMAC-SHA256(key, "comms-relay-pull/v1\0" ‖ method ‖ "\0" ‖ path ‖ "\0" ‖ timestamp ‖ "\0" ‖ body))

export const WINDOW_SECONDS = 300;
const DOMAIN = "comms-relay-pull/v1\0";
const TIMESTAMP = /^(0|[1-9][0-9]{0,11})$/;
const HEX64 = /^[0-9a-f]{64}$/;

function message(method: string, path: string, timestamp: string, body: Uint8Array): Uint8Array {
  const head = new TextEncoder().encode(`${DOMAIN}${method}\0${path}\0${timestamp}\0`);
  const out = new Uint8Array(head.length + body.length);
  out.set(head);
  out.set(body, head.length);
  return out;
}

export function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16);
  return out;
}

function toHex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sign(
  key: Uint8Array,
  method: string,
  path: string,
  timestamp: string,
  body: Uint8Array,
): Promise<string> {
  const hmacKey = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return toHex(await crypto.subtle.sign("HMAC", hmacKey, message(method, path, timestamp, body)));
}

/** Equal-length digests of both sides, compared in constant time. */
export async function constantTimeEqual(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [da, db] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  return crypto.subtle.timingSafeEqual(da, db);
}

export async function verify(
  keyHex: string,
  method: string,
  path: string,
  timestamp: string | null,
  body: Uint8Array,
  signature: string | null,
  nowSeconds: number,
): Promise<boolean> {
  if (!HEX64.test(keyHex) || timestamp === null || signature === null) return false;
  if (!TIMESTAMP.test(timestamp) || !HEX64.test(signature)) return false;
  if (Math.abs(nowSeconds - Number(timestamp)) > WINDOW_SECONDS) return false;
  const expected = await sign(hexToBytes(keyHex), method, path, timestamp, body);
  return constantTimeEqual(expected, signature);
}
