import type { Metadata } from "next";
import type { PublicWebsite } from "@/types/website";

/** Fetch the published website on the server for <title>, description, social previews and favicon. */
export async function fetchWebsite(slug: string): Promise<PublicWebsite | null> {
  if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(slug)) return null;
  const api = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const r = await fetch(`${api}/api/v1/public/organizations/${slug}/website`, { signal: AbortSignal.timeout(2500), next: { revalidate: 30 } });
    return r.ok ? ((await r.json()) as PublicWebsite) : null;
  } catch {
    return null;
  }
}

function absolute(url: string): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("https://")) return url;
  const site = process.env.NEXT_PUBLIC_SITE_URL ?? process.env.FRONTEND_URL;
  return url.startsWith("/media/") && site ? `${site.replace(/\/$/, "")}${url}` : undefined;
}

export async function siteMetadata(slug: string, page?: { title?: string; description?: string }): Promise<Metadata> {
  const site = await fetchWebsite(slug);
  if (!site) return { title: "Book an appointment", robots: { index: false } };
  const { settings, seo } = site.document;
  const name = settings.site_name || settings.clinic_name;
  const title = page?.title ? `${page.title} · ${name}` : seo.title || name;
  const description = page?.description || seo.description || settings.description || `Book an appointment at ${name} online.`;
  const image = absolute(seo.image_url) ?? absolute(settings.logo_url);
  const favicon = absolute(settings.favicon_url) ?? (settings.favicon_url.startsWith("/media/") ? settings.favicon_url : undefined);
  return {
    title,
    description,
    robots: seo.noindex ? { index: false, follow: false } : undefined,
    openGraph: { title, description, siteName: name, type: "website", images: image ? [image] : undefined },
    twitter: { card: image ? "summary_large_image" : "summary", title, description },
    icons: favicon ? { icon: favicon } : undefined,
  };
}
