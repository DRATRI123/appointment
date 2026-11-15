"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { AlertTriangle, Check, Copy, Info, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

/** Values substituted into examples: the API address this app is served from and the signed-in clinic. */
export interface DocsEnv { base: string; slug: string; orgId: string }
export const DocsEnvContext = createContext<DocsEnv>({ base: "https://booking.example.com/api/v1", slug: "your-clinic", orgId: "" });
export const useDocsEnv = () => useContext(DocsEnvContext);

export function docHref(page: string, anchor?: string) {
  return `/admin/developers/docs${page === "overview" ? "" : `/${page}`}${anchor ? `#${anchor}` : ""}`;
}

export function DocLink({ page, anchor, children }: { page: string; anchor?: string; children: ReactNode }) {
  return <Link href={docHref(page, anchor)} className="font-medium underline decoration-primary decoration-2 underline-offset-2 hover:text-primary">{children}</Link>;
}

export function Lead({ children }: { children: ReactNode }) {
  return <p className="text-base leading-7 text-muted-foreground">{children}</p>;
}

export function H2({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} data-doc-heading className="group mt-12 scroll-mt-24 border-t pt-8 text-xl font-semibold tracking-tight first:mt-0 first:border-0 first:pt-0">
      <a href={`#${id}`} className="no-underline">{children}<span className="ml-2 text-muted-foreground opacity-0 group-hover:opacity-100" aria-hidden>#</span></a>
    </h2>
  );
}

export function H3({ id, children }: { id?: string; children: ReactNode }) {
  return <h3 id={id} className="mt-8 scroll-mt-24 text-base font-semibold">{children}</h3>;
}

export function P({ children }: { children: ReactNode }) {
  return <p className="mt-3 leading-7">{children}</p>;
}

export function UL({ children }: { children: ReactNode }) {
  return <ul className="mt-3 list-disc space-y-1.5 pl-5 leading-7 marker:text-muted-foreground">{children}</ul>;
}

export function OL({ children }: { children: ReactNode }) {
  return <ol className="mt-3 list-decimal space-y-1.5 pl-5 leading-7 marker:text-muted-foreground">{children}</ol>;
}

export function C({ children }: { children: ReactNode }) {
  return <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>;
}

const CALLOUT = {
  info: { icon: Info, cls: "border-primary/30 bg-primary/5" },
  warning: { icon: AlertTriangle, cls: "border-warning/50 bg-warning/10" },
  security: { icon: ShieldCheck, cls: "border-success/40 bg-success/5" },
} as const;

export function Callout({ kind = "info", title, children }: { kind?: keyof typeof CALLOUT; title?: string; children: ReactNode }) {
  const { icon: Icon, cls } = CALLOUT[kind];
  return (
    <div className={cn("mt-5 flex gap-3 rounded-xl border p-4 text-sm leading-6", cls)} role="note">
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{title ? <p className="font-semibold">{title}</p> : null}<div className={cn(title && "mt-1")}>{children}</div></div>
    </div>
  );
}

async function copyText(text: string) {
  try { await navigator.clipboard.writeText(text); toast.success("Copied"); } catch { toast.error("Copy failed"); }
}

export function CodeBlock({ code, label, className }: { code: string; label: string; className?: string }) {
  return (
    <div className={cn("relative mt-4", className)}>
      <pre className="max-h-[32rem] overflow-auto rounded-xl bg-[#0f172a] p-4 pr-12 text-[12.5px] leading-relaxed text-slate-100" aria-label={label} tabIndex={0}><code>{code}</code></pre>
      <button type="button" onClick={() => copyText(code)} aria-label={`Copy ${label}`} className="absolute top-2 right-2 rounded-md p-1.5 text-slate-300 hover:bg-white/10 hover:text-white"><Copy className="size-3.5" /></button>
    </div>
  );
}

/** Several versions of one example (e.g. curl / Python / Node.js / PHP). The chosen language is shared by every block on the page. */
const LangContext = createContext<{ lang: string; setLang: (l: string) => void }>({ lang: "curl", setLang: () => {} });
export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem("ap.docs.lang") ?? "curl"; } catch { return "curl"; }
  });
  const set = (l: string) => { setLang(l); try { localStorage.setItem("ap.docs.lang", l); } catch { /* private mode */ } };
  return <LangContext.Provider value={{ lang, setLang: set }}>{children}</LangContext.Provider>;
}

export function CodeTabs({ label, samples }: { label: string; samples: { lang: string; title: string; code: string }[] }) {
  const { lang, setLang } = useContext(LangContext);
  const current = samples.find((s) => s.lang === lang) ?? samples[0];
  return (
    <div className="mt-4 overflow-hidden rounded-xl bg-[#0f172a]" data-testid="code-tabs">
      <div className="flex items-center gap-1 border-b border-white/10 px-2 pt-2" role="tablist" aria-label={`${label}: language`}>
        {samples.map((s) => (
          <button key={s.lang} type="button" role="tab" aria-selected={s.lang === current.lang} onClick={() => setLang(s.lang)}
            className={cn("rounded-t-md px-3 py-1.5 text-xs font-medium", s.lang === current.lang ? "bg-white/10 text-white" : "text-slate-300 hover:text-white")}>{s.title}</button>
        ))}
      </div>
      <div className="relative">
        <pre className="max-h-[32rem] overflow-auto p-4 pr-12 text-[12.5px] leading-relaxed text-slate-100" aria-label={`${label} (${current.title})`} tabIndex={0}><code>{current.code}</code></pre>
        <button type="button" onClick={() => copyText(current.code)} aria-label={`Copy ${label}`} className="absolute top-2 right-2 rounded-md p-1.5 text-slate-300 hover:bg-white/10 hover:text-white"><Copy className="size-3.5" /></button>
      </div>
    </div>
  );
}

type Json = unknown;
const KEY = "$API_KEY";

function qs(query?: Record<string, string>) {
  const entries = Object.entries(query ?? {});
  return entries.length ? "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&") : "";
}

/** Builds the same request in four languages, so every example stays consistent. */
export function requestSamples({ method, path, query, body, auth = "key", base }: { method: string; path: string; query?: Record<string, string>; body?: Json; auth?: "key" | "none"; base: string }) {
  const url = `${base}${path}${qs(query)}`;
  const json = body === undefined ? null : JSON.stringify(body, null, 2);
  const curl = [`curl${method === "GET" ? "" : ` -X ${method}`} "${url}"`, auth === "key" ? `  -H "Authorization: Bearer ${KEY}"` : null,
    json ? `  -H "Content-Type: application/json"` : null, json ? `  -d '${json.replace(/'/g, "'\\''")}'` : null].filter(Boolean).join(" \\\n");
  const pyBody = json ? json.replace(/\bnull\b/g, "None").replace(/\btrue\b/g, "True").replace(/\bfalse\b/g, "False") : null;
  const py = [
    "import os, requests", "",
    `resp = requests.${method.toLowerCase()}(`,
    `    "${base}${path}",`,
    query ? `    params=${JSON.stringify(query, null, 4).replace(/\n/g, "\n    ")},` : null,
    auth === "key" ? `    headers={"Authorization": f"Bearer {os.environ['API_KEY']}"},` : null,
    pyBody ? `    json=${pyBody.replace(/\n/g, "\n    ")},` : null,
    "    timeout=15,", ")",
    "resp.raise_for_status()  # 4xx/5xx: see resp.json()['code']", "print(resp.json())",
  ].filter((l) => l !== null).join("\n");
  const node = [
    `const resp = await fetch("${url}", {`,
    `  method: "${method}",`,
    auth === "key" || json ? `  headers: { ${[auth === "key" ? "Authorization: `Bearer ${process.env.API_KEY}`" : null, json ? '"Content-Type": "application/json"' : null].filter(Boolean).join(", ")} },` : null,
    json ? `  body: JSON.stringify(${json.replace(/\n/g, "\n  ")}),` : null,
    "});",
    "const data = await resp.json();",
    "if (!resp.ok) throw new Error(`${resp.status} ${data.code}: ${data.detail}`);",
    "console.log(data);",
  ].filter(Boolean).join("\n");
  const php = [
    "<?php",
    `$ch = curl_init("${url}");`,
    "curl_setopt_array($ch, [",
    "    CURLOPT_RETURNTRANSFER => true,",
    method !== "GET" ? `    CURLOPT_CUSTOMREQUEST => "${method}",` : null,
    `    CURLOPT_HTTPHEADER => [${auth === "key" ? `"Authorization: Bearer " . getenv("API_KEY")` : ""}${auth === "key" && json ? ", " : ""}${json ? `"Content-Type: application/json"` : ""}],`,
    json ? `    CURLOPT_POSTFIELDS => json_encode(${phpArray(body, 1)}),` : null,
    "]);",
    "$data = json_decode(curl_exec($ch), true);",
    "$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);",
    "if ($status >= 400) { throw new Exception($data['code'] . ': ' . $data['detail']); }",
  ].filter(Boolean).join("\n");
  return [
    { lang: "curl", title: "curl", code: curl },
    { lang: "python", title: "Python", code: py },
    { lang: "node", title: "Node.js", code: node },
    { lang: "php", title: "PHP", code: php },
  ];
}

function phpArray(v: Json, depth: number): string {
  const pad = "    ".repeat(depth + 1), end = "    ".repeat(depth);
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return `[${v.map((x) => phpArray(x, depth)).join(", ")}]`;
  if (typeof v === "object") return `[\n${Object.entries(v as Record<string, Json>).map(([k, x]) => `${pad}"${k}" => ${phpArray(x, depth + 1)}`).join(",\n")},\n${end}]`;
  if (typeof v === "string") return JSON.stringify(v);
  return String(v);
}

const METHOD_TONE: Record<string, string> = {
  GET: "bg-sky-100 text-sky-900", POST: "bg-emerald-100 text-emerald-900", PUT: "bg-amber-100 text-amber-900",
  PATCH: "bg-amber-100 text-amber-900", DELETE: "bg-rose-100 text-rose-900",
};

export function Method({ m }: { m: string }) {
  return <span className={cn("inline-flex min-w-[3.6rem] justify-center rounded-md px-1.5 py-0.5 font-mono text-[11px] font-semibold", METHOD_TONE[m] ?? "bg-muted")}>{m}</span>;
}

/** A request example in four languages, headed by the method and path. */
export function Request({ title, method, path, query, body, auth }: { title: string; method: string; path: string; query?: Record<string, string>; body?: Json; auth?: "key" | "none" }) {
  const { base } = useDocsEnv();
  return (
    <div className="mt-5">
      <p className="flex flex-wrap items-center gap-2 text-sm font-medium"><Method m={method} /><span className="font-mono text-[13px]">{path}</span><span className="text-muted-foreground">· {title}</span></p>
      <CodeTabs label={title} samples={requestSamples({ method, path, query, body, auth, base })} />
    </div>
  );
}

export function Response({ status, body, note }: { status: number; body: Json; note?: string }) {
  const ok = status < 300;
  return (
    <div className="mt-3">
      <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span className={cn("rounded-md px-1.5 py-0.5 font-mono font-semibold", ok ? "bg-emerald-100 text-emerald-900" : "bg-rose-100 text-rose-900")}>{status}</span>
        Response{note ? ` · ${note}` : ""}
      </p>
      <CodeBlock code={JSON.stringify(body, null, 2)} label={`Response ${status}`} className="mt-2" />
    </div>
  );
}

/** Endpoint table: method, path, required scope, what it does. */
export function Endpoints({ rows }: { rows: [string, string, string, ReactNode][] }) {
  return (
    <>
    <ul className="mt-4 divide-y rounded-xl border md:hidden">
      {rows.map(([m, p, s, d]) => (
        <li key={m + p} className="space-y-1.5 p-3 text-sm">
          <p className="flex flex-wrap items-center gap-2"><Method m={m} /><span className="font-mono text-[12.5px] break-all">{p}</span></p>
          <p className="font-mono text-[11.5px] text-muted-foreground">{s}</p>
          <div className="leading-6">{d}</div>
        </li>
      ))}
    </ul>
    <div className="mt-4 hidden overflow-x-auto rounded-xl border md:block" tabIndex={0} role="region" aria-label="Endpoints">
      <table className="w-full min-w-[40rem] text-sm">
        <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr><th scope="col" className="px-3 py-2">Method</th><th scope="col" className="px-3 py-2">Path</th><th scope="col" className="px-3 py-2">Scope</th><th scope="col" className="px-3 py-2">What it does</th></tr>
        </thead>
        <tbody className="divide-y">
          {rows.map(([m, p, s, d]) => (
            <tr key={m + p} className="align-top">
              <td className="px-3 py-2"><Method m={m} /></td>
              <td className="px-3 py-2 font-mono text-[12.5px] break-all">{p}</td>
              <td className="px-3 py-2 font-mono text-[12px] whitespace-nowrap text-muted-foreground">{s}</td>
              <td className="px-3 py-2 leading-6">{d}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  );
}

/** Generic table with a header row. */
export function Table({ head, rows, mono = [0] }: { head: string[]; rows: ReactNode[][]; mono?: number[] }) {
  return (
    <div className="mt-4 overflow-x-auto rounded-xl border" tabIndex={0} role="region" aria-label={head.join(", ")}>
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>{head.map((h) => <th key={h} scope="col" className="px-3 py-2">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((r, i) => (
            <tr key={i} className="align-top">{r.map((c, j) => <td key={j} className={cn("px-3 py-2 leading-6", mono.includes(j) && "font-mono text-[12.5px] whitespace-nowrap")}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Steps({ items }: { items: { title: string; body: ReactNode }[] }) {
  return (
    <ol className="mt-5 space-y-5">
      {items.map((s, i) => (
        <li key={s.title} className="flex gap-4">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">{i + 1}</span>
          <div className="min-w-0 flex-1"><p className="font-semibold">{s.title}</p><div className="mt-1 leading-7">{s.body}</div></div>
        </li>
      ))}
    </ol>
  );
}

export function Checklist({ items }: { items: ReactNode[] }) {
  return (
    <ul className="mt-4 space-y-2">
      {items.map((it, i) => <li key={i} className="flex gap-2.5 leading-7"><Check className="mt-1.5 size-4 shrink-0 text-success-ink" aria-hidden /><span>{it}</span></li>)}
    </ul>
  );
}
