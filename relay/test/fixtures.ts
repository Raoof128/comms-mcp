// Test-only material, derived from fixed strings in vitest.config.ts: never a real key.
import { env, exports } from "cloudflare:workers";
import * as age from "age-encryption";
import { sign } from "../src/pull_sig";

export const TEST_IDENTITY = "AGE-SECRET-KEY-1VJL2JKCHUDCR0EXH2UXGDVVFGK07XVE38W34U459YNHW5N67KJPSADSZHK";
export const HOOK = `https://relay.example/webhooks/meta/${env.RELAY_PATH_TOKEN}`;
export const BODY = '{"object":"whatsapp_business_account","entry":[]}';
export const SIG = "sha256=" + "ab".repeat(32);

export function post(url: string, body: BodyInit, headers: Record<string, string> = {}): Promise<Response> {
  return exports.default.fetch(
    new Request(url, {
      method: "POST",
      body,
      headers: { "content-type": "application/json", "x-hub-signature-256": SIG, ...headers },
    }),
  );
}

function hexToBytes(hex: string): Uint8Array {
  return Uint8Array.from(hex.match(/../g)!.map((h) => parseInt(h, 16)));
}

export async function control(
  path: "/pull" | "/ack",
  fields: Record<string, unknown>,
  opts: { key?: string; skew?: number; tamper?: boolean } = {},
): Promise<Response> {
  const body = new TextEncoder().encode(JSON.stringify(fields));
  const ts = String(Math.floor(Date.now() / 1000) + (opts.skew ?? 0));
  let signature = await sign(hexToBytes(opts.key ?? env.RELAY_PULL_KEY), "POST", path, ts, body);
  if (opts.tamper) signature = signature.slice(0, -1) + (signature.endsWith("0") ? "1" : "0");
  return exports.default.fetch(
    new Request(`https://relay.example${path}`, {
      method: "POST",
      body,
      headers: { "x-comms-timestamp": ts, "x-comms-signature": signature },
    }),
  );
}

export async function open(ciphertextB64: string): Promise<Record<string, unknown>> {
  const d = new age.Decrypter();
  d.addIdentity(TEST_IDENTITY);
  const bytes = Uint8Array.from(atob(ciphertextB64), (c) => c.charCodeAt(0));
  return JSON.parse(await d.decrypt(bytes, "text"));
}
