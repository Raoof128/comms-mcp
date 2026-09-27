// The relay's bounds (spec A48). They live apart from src/index.ts because workerd accepts only
// handlers and classes as exports of the main module.
export const MAX_BODY_BYTES = 8 * 1024 * 1024; // Meta sets no limit and batches up to 1000 updates
export const PART_BYTES = 1024 * 1024; // a Durable Object row holds at most 2 MB
export const PAGE_ROWS = 50;
export const PAGE_BYTES = 256 * 1024;
export const RETENTION_MS = 30 * 24 * 60 * 60 * 1000;
