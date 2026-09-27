import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

// Test-only values, derived from fixed strings: never a real key. The age identity that opens
// these rows appears only in test/fixtures.ts.
export const TEST_BINDINGS = {
  RELAY_PATH_TOKEN: "UdHbmbO6NMnG7CIFI9HReOO9OdEWB7LQlX4Bk_ncv5Y",
  META_VERIFY_TOKEN: "test-verify-token",
  RELAY_PULL_KEY: "88ec73b8f5e83f55bec46ef07a2f9093634915447b1d1575da6cd9dadd6707e0",
  RELAY_AGE_RECIPIENT: "age1d0xuuajlkr0mmm25xh4hwtk488gtl8guye9f85wdfafcdyux7q5q6c978g",
};

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.jsonc" },
      miniflare: { bindings: TEST_BINDINGS },
    }),
  ],
});
