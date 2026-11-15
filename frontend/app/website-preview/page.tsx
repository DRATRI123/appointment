"use client";

import { Suspense, useEffect, useState } from "react";
import { SegmentPage, SiteHome } from "@/components/website/pages";
import { SiteShell } from "@/components/website/site-shell";
import { PREVIEW_DOCUMENT, PREVIEW_READY } from "@/components/website-admin/publish";
import type { WebsiteDocument } from "@/types/website";

/**
 * Rendered inside the admin's preview frame. It shows whatever document the parent page (same origin only) sends,
 * so unsaved edits can be previewed; on its own it shows nothing. Links are kept inside the preview.
 */
export default function WebsitePreviewPage() {
  const [data, setData] = useState<{ document: WebsiteDocument; slug: string; page: string } | null>(null);
  const [page, setPage] = useState<string | null>(null);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || e.source !== window.parent || e.data?.type !== PREVIEW_DOCUMENT) return;
      const { document, slug, page: p } = e.data as { document: WebsiteDocument; slug: string; page: string };
      if (!document || typeof slug !== "string" || !/^[a-z0-9][a-z0-9-]{0,79}$/.test(slug)) return;
      setData({ document, slug, page: p ?? "" });
      setPage(null);
    };
    window.addEventListener("message", onMessage);
    if (window.parent !== window) window.parent.postMessage({ type: PREVIEW_READY }, window.location.origin);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  if (!data) return <p className="p-8 text-center text-sm text-muted-foreground">Open the preview from Website → Preview &amp; publish.</p>;
  const current = page ?? data.page;
  const base = `/${data.slug}`;
  return (
    <div
      onClickCapture={(e) => {
        const a = (e.target as HTMLElement).closest("a");
        if (!a) return;
        const href = a.getAttribute("href") ?? "";
        if (href.startsWith("#")) return; // in-page jump
        e.preventDefault();
        if (href === base) setPage("");
        else if (href.startsWith(`${base}#`)) { setPage(""); setTimeout(() => document.getElementById(href.split("#")[1])?.scrollIntoView({ behavior: "smooth" }), 50); }
        else if (href.startsWith(`${base}/`) && !href.startsWith(`${base}/book`)) setPage(href.slice(base.length + 1).split(/[?#]/)[0]);
      }}
    >
      <Suspense>
        <SiteShell slug={data.slug} previewDocument={data.document}>
          {current ? <SegmentPage segment={current} /> : <SiteHome />}
        </SiteShell>
      </Suspense>
    </div>
  );
}
