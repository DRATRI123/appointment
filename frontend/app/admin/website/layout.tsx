"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { EditorToolbar, WebsiteEditorProvider } from "@/components/website-admin/editor";
import { cn } from "@/lib/utils";

const NAV = [
  ["settings", "Website settings"], ["builder", "Homepage builder"], ["header", "Header & navigation"], ["hero", "Hero section"],
  ["about", "About section"], ["doctors", "Doctors section"], ["services", "Services section"], ["gallery", "Gallery & images"],
  ["testimonials", "Testimonials"], ["faq", "FAQ"], ["contact", "Contact & location"], ["footer", "Footer"], ["pages", "Custom pages"],
  ["buttons", "Custom links & buttons"], ["seo", "SEO settings"], ["publish", "Preview & publish"],
] as const;

export default function WebsiteLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Website management" description="Design your public clinic website. Edits stay in a draft until you publish." />
      <WebsiteEditorProvider>
        <EditorToolbar />
        <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav aria-label="Website sections" className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-2 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0 [scrollbar-width:none]">
            {NAV.map(([slug, label]) => {
              const href = `/admin/website/${slug}`;
              const active = pathname === href;
              return <Link key={slug} href={href} aria-current={active ? "page" : undefined} className={cn("shrink-0 rounded-lg px-3 py-2 text-sm transition-colors", active ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>{label}</Link>;
            })}
          </nav>
          <div className="min-w-0">{children}</div>
        </div>
      </WebsiteEditorProvider>
    </div>
  );
}
