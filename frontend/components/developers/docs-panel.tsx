"use client";

import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DOC_GROUPS, DOC_PAGES } from "@/components/developers/docs/registry";
import { docHref } from "@/components/developers/docs/ui";

/** The "Docs" tab of the Developers screen: an index into the full developer documentation. */
export function DocsPanel() {
  return (
    <div className="space-y-6" data-testid="docs-index">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-start gap-3">
          <BookOpen className="mt-0.5 size-5 text-primary" aria-hidden />
          <div>
            <p className="font-semibold">Developer documentation</p>
            <p className="text-sm text-muted-foreground">Guides, the full API reference, webhooks with signature examples in Python, Node.js and PHP, and a go-live checklist.</p>
          </div>
        </div>
        <Button asChild><Link href={docHref("quickstart")}>Start with the quickstart<ArrowRight /></Link></Button>
      </div>
      {DOC_GROUPS.map((g) => (
        <section key={g}>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{g}</h2>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {DOC_PAGES.filter((p) => p.group === g).map((p) => (
              <Link key={p.slug} href={docHref(p.slug)} className="group rounded-xl border bg-card p-4 transition-colors hover:border-primary">
                <p className="font-medium group-hover:text-primary">{p.title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{p.summary}</p>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
