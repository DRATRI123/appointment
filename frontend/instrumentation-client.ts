// Runs in the browser before any application code (Next.js instrumentation-client).
// Zod probes `new Function` when a schema is defined; under our nonce-based CSP that probe is reported as a violation.
// Switching Zod to jitless here, before any page module defines a schema, makes the order of chunk loading irrelevant.
import "./lib/zod-config";
