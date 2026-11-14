import { z } from "zod";

// Zod v4 probes `new Function("")` to enable a JIT; our Content-Security-Policy forbids eval, so use the
// eval-free mode explicitly (same results, no CSP violation).
z.config({ jitless: true });
