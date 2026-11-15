import { Suspense } from "react";
import type { Metadata } from "next";
import { SiteShell } from "@/components/website/site-shell";
import { siteMetadata } from "@/lib/site-metadata";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return siteMetadata(slug);
}

export default async function ClinicSiteLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return (
    <Suspense>
      <SiteShell slug={slug}>{children}</SiteShell>
    </Suspense>
  );
}
