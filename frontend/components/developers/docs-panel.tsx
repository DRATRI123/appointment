"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { developersService } from "@/services/developers";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function Code({ children, label }: { children: string; label: string }) {
  const copy = async () => { try { await navigator.clipboard.writeText(children); toast.success("Copied"); } catch { toast.error("Copy failed"); } };
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-lg bg-muted/60 p-3 pr-12 text-xs leading-relaxed" aria-label={label}><code>{children}</code></pre>
      <Button size="icon" variant="ghost" className="absolute top-1.5 right-1.5 size-7" aria-label={`Copy ${label}`} onClick={copy}><Copy className="size-3.5" /></Button>
    </div>
  );
}

const PY = `import hashlib, hmac, time

def verify(secret: str, signature_header: str, raw_body: bytes, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in signature_header.split(","))
    ts = int(parts["t"])
    if abs(time.time() - ts) > tolerance:
        return False  # too old: possible replay
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))

# Flask example
# ok = verify(SECRET, request.headers["X-Webhook-Signature"], request.get_data())`;

const NODE = `import crypto from "node:crypto";

export function verify(secret, signatureHeader, rawBody, toleranceSec = 300) {
  const parts = Object.fromEntries(signatureHeader.split(",").map((p) => p.split("=")));
  const ts = Number(parts.t);
  if (Math.abs(Date.now() / 1000 - ts) > toleranceSec) return false; // replay protection
  const expected = crypto.createHmac("sha256", secret).update(\`\${ts}.\`).update(rawBody).digest("hex");
  const given = Buffer.from(parts.v1 ?? "", "hex");
  return given.length === 32 && crypto.timingSafeEqual(Buffer.from(expected, "hex"), given);
}
// Use the raw request body (e.g. express.raw({ type: "application/json" })), not re-serialised JSON.`;

export function DocsPanel() {
  const { currentOrganizationId } = useAuth();
  const events = useQuery({ queryKey: ["webhook-events"], queryFn: developersService.events });
  const [open, setOpen] = useState<string | null>(null);
  const base = typeof window !== "undefined" ? `${window.location.origin}/api/v1` : "/api/v1";
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Calling the API</CardTitle><CardDescription>Send your key as a Bearer token. The key already knows its organization.</CardDescription></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Code label="List today's appointments">{`curl ${base}/appointments \\\n  -H "Authorization: Bearer ak_live_…"`}</Code>
          <Code label="Book an appointment">{`curl -X POST ${base}/appointments \\\n  -H "Authorization: Bearer ak_live_…" -H "Content-Type: application/json" \\\n  -d '{"professional_id":"…","branch_id":"…","service_id":"…","start_at":"2026-11-20T10:00:00+05:30",\n       "customer":{"full_name":"Asha Patel","mobile":"9812345678"},"source":"api"}'`}</Code>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Reference: <a className="underline" href="/docs" target="_blank" rel="noreferrer">interactive API docs</a> (OpenAPI at <span className="font-mono text-xs">/api/v1/openapi.json</span>). Keys work on appointments, availability, customers, catalogue, payments (read only), booking forms, reports and analytics.</li>
            <li>Errors are JSON: <span className="font-mono text-xs">{`{"detail": "…", "code": "…", "request_id": "…"}`}</span>. Quote the request id when asking for help.</li>
            <li>Each key has a per-minute limit; a <span className="font-mono text-xs">429</span> response carries <span className="font-mono text-xs">Retry-After</span>.</li>
            <li>Money is always in paise (integers). Times are ISO 8601 with offsets.</li>
            <li>An API key can never record or verify a payment. Payments are confirmed only by staff who checked the bank.</li>
          </ul>
          <p className="text-xs text-muted-foreground">Organization id (only needed with a user token): <span className="font-mono">{currentOrganizationId}</span></p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Verifying webhooks</CardTitle><CardDescription>Every request carries <span className="font-mono">X-Webhook-Signature: t=&lt;unix time&gt;,v1=&lt;HMAC-SHA256 hex&gt;</span> over <span className="font-mono">&quot;&lt;t&gt;.&lt;raw body&gt;&quot;</span>, signed with the endpoint&apos;s secret. Reject requests older than five minutes, reply with any 2xx within 10 seconds, and use <span className="font-mono">X-Webhook-Id</span> to ignore duplicates.</CardDescription></CardHeader>
        <CardContent className="space-y-3"><Code label="Python verification">{PY}</Code><Code label="Node.js verification">{NODE}</Code></CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Events</CardTitle><CardDescription>Payloads contain public ids only, never clinical notes, form answers or documents.</CardDescription></CardHeader>
        <CardContent className="space-y-2">
          {events.data?.map((e) => (
            <div key={e.name} className="rounded-lg border">
              <button type="button" className="flex w-full flex-wrap items-baseline gap-x-3 px-3 py-2 text-left text-sm hover:bg-muted/40" onClick={() => setOpen(open === e.name ? null : e.name)} aria-expanded={open === e.name}>
                <span className="font-mono text-xs font-medium">{e.name}</span><span className="text-muted-foreground">{e.description}</span>
              </button>
              {open === e.name ? <div className="border-t p-3"><Code label={`${e.name} example`}>{JSON.stringify(e.sample, null, 2)}</Code></div> : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
