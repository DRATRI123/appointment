import { z } from "zod";

// Zod v4 probes `new Function("")` to enable a JIT; our Content-Security-Policy forbids eval, so use the
// eval-free mode explicitly (same results, no CSP violation).
z.config({ jitless: true });

// Forms import `z` from here (never from "zod" directly), so the setting is applied before any schema exists, and zod
// is only downloaded by the pages that have such forms. It used to be imported for every page (root providers and
// instrumentation-client.ts), which put ~100 KB of JavaScript on the public booking pages that never use it.
export { z };
