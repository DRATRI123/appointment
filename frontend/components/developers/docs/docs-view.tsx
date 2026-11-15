"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, ExternalLink, Search } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { cn } from "@/lib/utils";
import { DOC_GROUPS, DOC_PAGES, findDocPage } from "./registry";
import { DocsEnvContext, LangProvider, docHref } from "./ui";

const noop = () => () => {};

function useEnv() {
  const { currentMembership } = useAuth();
  const origin = useSyncExternalStore(noop, () => window.location.origin, () => "https://booking.example.com");
  return { base: `${origin}/api/v1`, slug: currentMembership?.organization.slug ?? "your-clinic", orgId: currentMembership?.organization.id ?? "" };
}

function Toc({ deps }: { deps: string }) {
  const [items, setItems] = useState<{ id: string; text: string }[]>([]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const hs = Array.from(document.querySelectorAll<HTMLElement>("[data-doc-heading]"));
      setItems(hs.map((h) => ({ id: h.id, text: h.textContent?.replace(/#$/, "") ?? "" })));
    });
    return () => cancelAnimationFrame(frame);
  }, [deps]);
  if (items.length < 2) return null;
  return (
    <nav aria-label="On this page" className="sticky top-20 hidden w-52 shrink-0 self-start xl:block">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">On this page</p>
      <ul className="mt-3 space-y-2 border-l text-sm">
        {items.map((i) => <li key={i.id}><a href={`#${i.id}`} className="-ml-px block border-l border-transparent pl-3 text-muted-foreground hover:border-foreground hover:text-foreground">{i.text}</a></li>)}
      </ul>
    </nav>
  );
}

export function DocsView({ slug }: { slug: string }) {
  const page = findDocPage(slug);
  const env = useEnv();
  const router = useRouter();
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? DOC_PAGES.filter((p) => `${p.title} ${p.summary} ${p.keywords ?? ""}`.toLowerCase().includes(t)) : DOC_PAGES;
  }, [q]);
  if (!page) notFound();
  const index = DOC_PAGES.indexOf(page);
  const prev = DOC_PAGES[index - 1];
  const next = DOC_PAGES[index + 1];
  const Body = page.Body;

  return (
    <DocsEnvContext.Provider value={env}>
      <LangProvider>
        <div className="mx-auto flex max-w-7xl gap-8" data-testid="developer-docs">
          <aside className="hidden w-60 shrink-0 lg:block">
            <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto pb-6">
              <label className="relative block">
                <span className="sr-only">Search the docs</span>
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search docs" data-testid="docs-search"
                  className="h-9 w-full rounded-lg border bg-background pr-3 pl-8 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
              </label>
              <nav aria-label="Developer docs" className="mt-5 space-y-5">
                {DOC_GROUPS.map((g) => {
                  const pages = filtered.filter((p) => p.group === g);
                  if (!pages.length) return null;
                  return (
                    <div key={g}>
                      <p className="px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{g}</p>
                      <ul className="mt-1.5 space-y-0.5">
                        {pages.map((p) => (
                          <li key={p.slug}>
                            <Link href={docHref(p.slug)} aria-current={p.slug === page.slug ? "page" : undefined}
                              className={cn("block rounded-md px-2 py-1.5 text-sm hover:bg-accent", p.slug === page.slug ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground")}>{p.title}</Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
                {!filtered.length ? <p className="px-2 text-sm text-muted-foreground">No page matches “{q}”.</p> : null}
              </nav>
              <a href="/docs" target="_blank" rel="noreferrer" className="mt-6 flex items-center gap-1.5 px-2 text-sm text-muted-foreground hover:text-foreground">Interactive API reference <ExternalLink className="size-3.5" aria-hidden /></a>
            </div>
          </aside>

          <article className="min-w-0 flex-1">
            <label className="mb-5 block lg:hidden">
              <span className="sr-only">Go to page</span>
              <select value={page.slug} onChange={(e) => router.push(docHref(e.target.value))} data-testid="docs-mobile-nav"
                className="h-10 w-full rounded-lg border bg-background px-3 text-sm">
                {DOC_GROUPS.map((g) => <optgroup key={g} label={g}>{DOC_PAGES.filter((p) => p.group === g).map((p) => <option key={p.slug} value={p.slug}>{p.title}</option>)}</optgroup>)}
              </select>
            </label>
            <p className="text-sm font-medium text-primary">{page.group}</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">{page.title}</h1>
            <div className="mt-4 max-w-3xl text-[15px]" key={page.slug}><Body /></div>
            <nav aria-label="Previous and next page" className="mt-14 grid max-w-3xl gap-3 border-t pt-6 sm:grid-cols-2">
              {prev ? (
                <Link href={docHref(prev.slug)} className="group rounded-xl border p-4 hover:border-primary">
                  <span className="flex items-center gap-1 text-xs text-muted-foreground"><ArrowLeft className="size-3.5" aria-hidden />Previous</span>
                  <span className="mt-1 block font-medium group-hover:text-primary">{prev.title}</span>
                </Link>
              ) : <span />}
              {next ? (
                <Link href={docHref(next.slug)} className="group rounded-xl border p-4 text-right hover:border-primary">
                  <span className="flex items-center justify-end gap-1 text-xs text-muted-foreground">Next<ArrowRight className="size-3.5" aria-hidden /></span>
                  <span className="mt-1 block font-medium group-hover:text-primary">{next.title}</span>
                </Link>
              ) : null}
            </nav>
          </article>
          <Toc deps={page.slug} />
        </div>
      </LangProvider>
    </DocsEnvContext.Provider>
  );
}
