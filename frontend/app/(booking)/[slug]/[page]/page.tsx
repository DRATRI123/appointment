import type { Metadata } from "next";
import { SegmentPage } from "@/components/website/pages";
import { fetchWebsite, siteMetadata } from "@/lib/site-metadata";

export async function generateMetadata({ params }: { params: Promise<{ slug: string; page: string }> }): Promise<Metadata> {
  const { slug, page } = await params;
  const site = await fetchWebsite(slug);
  const custom = site?.document.pages.find((p) => p.enabled && p.slug === page);
  const titles: Record<string, string> = { privacy: "Privacy policy", terms: "Terms and conditions", "refund-policy": "Refund policy" };
  return siteMetadata(slug, { title: custom ? custom.seo_title || custom.title : titles[page] ?? page.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()), description: custom?.seo_description });
}

export default async function ClinicSegmentPage({ params }: { params: Promise<{ page: string }> }) {
  const { page } = await params;
  return <SegmentPage segment={page} />;
}
