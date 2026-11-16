"use client";

import { AnalyticsConsent } from "@/components/public-booking/analytics-consent";
import type { AnalyticsIds } from "@/lib/analytics";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2, Mail, MapPin, Menu, Phone } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { publicWebsite } from "@/services/website";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { BookingContext, addressLine, initials } from "@/components/public-booking/booking-shell";
import { rememberCampaign } from "@/lib/campaign";
import { sendSiteEvent } from "@/lib/site-events";
import { navHref, phoneDigits, whatsappLink, type LinkContext } from "@/lib/site-links";
import { cn } from "@/lib/utils";
import { ButtonsAt } from "./site-button";
import { SocialIcon } from "./icons";
import { SiteContext, useSite } from "./site-context";
import { siteTheme } from "./theme";
import type { NavItem, WebsiteDocument } from "@/types/website";

export function SiteShell({ slug, children, previewDocument }: { slug: string; children: React.ReactNode; previewDocument?: WebsiteDocument }) {
  const params = useSearchParams();
  const pathname = usePathname();
  const org = useQuery({ queryKey: ["public-org", slug], queryFn: () => publicCatalog.organization(slug), retry: false, staleTime: 60_000 });
  const site = useQuery({ queryKey: ["public-website", slug], queryFn: () => publicWebsite.get(slug), retry: false, staleTime: 30_000, enabled: !previewDocument });
  const campaign = useMemo(() => (typeof window === "undefined" ? {} : rememberCampaign(params)), [params]);
  const doc = previewDocument ?? site.data?.document;

  const value = useMemo(() => {
    if (!org.data || !doc) return null;
    const base = `/${slug}`;
    const contact = doc.sections.find((s) => s.type === "contact" && s.enabled)?.id;
    const services = doc.sections.find((s) => s.type === "services" && s.enabled)?.id;
    const links: LinkContext = {
      base, settings: doc.settings, campaign, sectionIds: { contact, services },
      branchAddress: (b) => addressLine(org.data!.branches.find((x) => x.slug === b)?.address),
    };
    return { slug, base, org: org.data, doc, preview: !!previewDocument, campaign, links };
  }, [org.data, doc, slug, campaign, previewDocument]);

  // Count page views (not in the admin preview). Key: "home", "book", or the page / location name.
  const base = `/${slug}`;
  const pageKey = pathname === base ? "home" : pathname.startsWith(`${base}/book`) ? "book" : pathname.startsWith(`${base}/appointments`) ? null : pathname.slice(base.length + 1).split("/")[0];
  const loaded = !!value;
  useEffect(() => {
    if (previewDocument || !pageKey || !loaded) return;
    sendSiteEvent(slug, pageKey === "book" ? "booking_view" : "page_view", pageKey, campaign.utm_source ?? "");
  }, [slug, pageKey, previewDocument, campaign.utm_source, loaded]);

  if (org.isLoading || (!previewDocument && site.isLoading)) {
    return (
      <div className="min-h-dvh">
        <div className="h-16 border-b" />
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-16"><Skeleton className="h-12 w-2/3" /><Skeleton className="h-6 w-1/2" /><Skeleton className="h-72 rounded-3xl" /></div>
      </div>
    );
  }
  if (!value) {
    return (
      <div className="grid min-h-dvh place-items-center bg-muted/30 px-4">
        <div className="max-w-md space-y-3 rounded-3xl border bg-background p-8 text-center shadow-sm" role="status">
          <span className="mx-auto grid size-12 place-items-center rounded-full bg-muted"><Building2 className="size-6 text-muted-foreground" aria-hidden /></span>
          <h1 className="text-xl font-semibold tracking-tight">We couldn&apos;t find this booking page</h1>
          <p className="text-muted-foreground">Check the link you were given, or contact the clinic directly.</p>
        </div>
      </div>
    );
  }
  const inBooking = pathname.startsWith(`${value.base}/book`) || pathname.startsWith(`${value.base}/appointments`);  // includes /bookings
  return (
    <SiteContext.Provider value={value}>
      <BookingContext.Provider value={{ slug, data: value.org, base: value.base, bookPath: `${value.base}/book`, embedded: false }}>
        <div className="site flex min-h-dvh flex-col text-foreground" style={siteTheme(value.doc.settings)} data-testid="site-shell"
          onClickCapture={(e) => {
            if (previewDocument || !pageKey || pageKey === "book") return;
            const a = (e.target as HTMLElement).closest("a");
            if (a?.getAttribute("href")?.startsWith(`${value.base}/book`)) sendSiteEvent(slug, "book_click", pageKey, campaign.utm_source ?? "");
          }}>
          <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-background focus:px-4 focus:py-2 focus:shadow">Skip to content</a>
          <SiteHeader />
          <main id="main" className={cn("flex-1", !inBooking && "pb-20 md:pb-0")}>{children}</main>
          <SiteFooter />
          {!inBooking ? <FloatingBar /> : null}
        </div>
        {!previewDocument ? <AnalyticsConsent slug={slug} ids={value.org.settings.analytics as unknown as AnalyticsIds | null} /> : null}
      </BookingContext.Provider>
    </SiteContext.Provider>
  );
}

export function SiteLogo({ size = "md" }: { size?: "md" | "lg" }) {
  const { doc } = useSite();
  const name = doc.settings.site_name || doc.settings.clinic_name;
  const logo = doc.settings.logo_url;
  return (
    <span className={cn("grid shrink-0 place-items-center overflow-hidden font-semibold shadow-sm ring-1 ring-black/5", size === "lg" ? "size-16 rounded-2xl text-xl" : "size-10 rounded-xl text-sm")}
      style={logo ? { background: "#fff" } : { background: "var(--primary)", color: "var(--primary-foreground)" }}>
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(logo)} alt="" className="h-full w-full object-contain p-1" />
      ) : initials(name)}
    </span>
  );
}

function useNav(): NavItem[] {
  const { doc } = useSite();
  const fromPages = doc.pages.filter((p) => p.enabled && p.show_in_nav && !doc.header.nav.some((n) => n.kind === "page" && n.target === p.slug))
    .map<NavItem>((p) => ({ label: p.title, kind: "page", target: p.slug, new_tab: false }));
  return [...doc.header.nav, ...fromPages];
}

function NavLink({ item, className, onClick }: { item: NavItem; className?: string; onClick?: () => void }) {
  const { base, campaign } = useSite();
  const link = navHref(item, base, campaign);
  if (!link) return null;
  const props = link.newTab ? { target: "_blank", rel: "noopener noreferrer" } : {};
  return link.external
    ? <a href={link.href} className={className} onClick={onClick} {...props}>{item.label}</a>
    : <Link href={link.href} className={className} onClick={onClick} {...props}>{item.label}</Link>;
}

function SiteHeader() {
  const { doc, base } = useSite();
  const nav = useNav();
  const [open, setOpen] = useState(false);
  const name = doc.settings.site_name || doc.settings.clinic_name;
  const phone = doc.settings.phone;
  return (
    <header className={cn("z-40 border-b border-black/5 bg-[color-mix(in_oklab,var(--site-bg)_88%,transparent)] backdrop-blur-md", doc.header.sticky && "sticky top-0")}>
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
        <Link href={base} className="flex min-w-0 items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--primary)]">
          {doc.header.show_logo ? <SiteLogo /> : null}
          <span className="truncate text-base font-semibold tracking-tight [font-family:var(--site-heading-font)] sm:text-lg">{name}</span>
        </Link>
        <nav className="ml-6 hidden items-center gap-1 lg:flex" aria-label="Main">
          {nav.map((item, i) => <NavLink key={i} item={item} className="rounded-full px-3 py-2 text-sm font-medium text-foreground/75 transition-colors hover:bg-black/5 hover:text-foreground" />)}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {doc.header.show_phone && phone ? (
            <a href={`tel:${phoneDigits(phone)}`} className="hidden items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-foreground/75 hover:text-foreground md:inline-flex">
              <Phone className="size-4" aria-hidden />{phone}
            </a>
          ) : null}
          <ButtonsAt position="header" size="sm" className="hidden sm:flex" max={2} />
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger className="grid size-10 place-items-center rounded-full hover:bg-black/5 lg:hidden" aria-label="Open menu"><Menu className="size-5" /></SheetTrigger>
            <SheetContent className="max-w-sm" style={siteTheme(doc.settings)}>
              <SheetTitle className="flex items-center gap-3 text-lg">{doc.header.show_logo ? <SiteLogo /> : null}{name}</SheetTitle>
              <SheetDescription className="sr-only">Site menu</SheetDescription>
              <nav className="flex flex-col" aria-label="Mobile">
                <Link href={base} onClick={() => setOpen(false)} className="border-b py-3 text-base font-medium">Home</Link>
                {nav.map((item, i) => <NavLink key={i} item={item} onClick={() => setOpen(false)} className="border-b py-3 text-base font-medium" />)}
              </nav>
              <ButtonsAt position="header" size="lg" className="flex-col items-stretch" buttonClassName="w-full" />
              {phone ? <a href={`tel:${phoneDigits(phone)}`} className="flex items-center gap-2 text-sm text-muted-foreground"><Phone className="size-4" aria-hidden />{phone}</a> : null}
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}

const SOCIAL_LABELS: Record<string, string> = { facebook: "Facebook", instagram: "Instagram", youtube: "YouTube", x: "X (Twitter)", linkedin: "LinkedIn", google: "Google reviews" };

function SiteFooter() {
  const { doc, org, base } = useSite();
  const s = doc.settings;
  const social = Object.entries(s.social).filter(([, url]) => !!url);
  const legal = org.settings.legal ?? {};
  const policies = [
    { slug: "privacy", label: "Privacy policy", has: !!legal.privacy_policy },
    { slug: "terms", label: "Terms and conditions", has: !!legal.terms },
    { slug: "refund-policy", label: "Refund policy", has: !!legal.refund_policy },
  ].filter((p) => p.has || doc.pages.some((pg) => pg.enabled && pg.slug === p.slug));
  return (
    <footer className="border-t border-black/5 bg-[color-mix(in_oklab,var(--site-bg)_96%,#000)]">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-4 lg:col-span-1">
          <div className="flex items-center gap-3"><SiteLogo /><span className="font-semibold [font-family:var(--site-heading-font)]">{s.site_name || s.clinic_name}</span></div>
          {doc.footer.about ? <p className="text-sm leading-relaxed text-foreground/70">{doc.footer.about}</p> : null}
          {doc.footer.show_social && social.length ? (
            <ul className="flex gap-2">
              {social.map(([network, url]) => (
                <li key={network}><a href={url} target="_blank" rel="noopener noreferrer" aria-label={SOCIAL_LABELS[network] ?? network}
                  className="grid size-9 place-items-center rounded-full bg-black/5 text-foreground/70 transition-colors hover:bg-[var(--primary)] hover:text-[var(--primary-foreground)]"><SocialIcon network={network} className="size-4" /></a></li>
              ))}
            </ul>
          ) : null}
        </div>
        {doc.footer.show_branches && org.branches.length ? (
          <div className="space-y-3 text-sm">
            <p className="font-semibold">{org.branches.length > 1 ? "Locations" : "Visit us"}</p>
            <ul className="space-y-3 text-foreground/70">
              {org.branches.slice(0, 4).map((b) => (
                <li key={b.id}><Link href={`${base}/${b.slug}`} className="font-medium text-foreground hover:underline">{b.name}</Link>{addressLine(b.address) ? <span className="block">{addressLine(b.address)}</span> : null}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {doc.footer.columns.map((col, i) => (
          <div key={i} className="space-y-3 text-sm">
            {col.title ? <p className="font-semibold">{col.title}</p> : null}
            <ul className="space-y-2 text-foreground/70">{col.links.map((l, j) => <li key={j}><NavLink item={l} className="hover:text-foreground hover:underline" /></li>)}</ul>
          </div>
        ))}
        <div className="space-y-3 text-sm">
          <p className="font-semibold">Contact</p>
          <ul className="space-y-2 text-foreground/70">
            {s.phone ? <li><a className="flex items-center gap-2 hover:text-foreground" href={`tel:${phoneDigits(s.phone)}`}><Phone className="size-4" aria-hidden />{s.phone}</a></li> : null}
            {s.whatsapp ? <li><a className="flex items-center gap-2 hover:text-foreground" href={whatsappLink(s.whatsapp)} target="_blank" rel="noopener noreferrer"><SocialIcon network="whatsapp" className="size-4" /><span>WhatsApp {s.whatsapp}</span></a></li> : null}
            {s.email ? <li><a className="flex items-center gap-2 hover:text-foreground" href={`mailto:${s.email}`}><Mail className="size-4" aria-hidden />{s.email}</a></li> : null}
            {s.address ? <li className="flex gap-2"><MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />{s.address}</li> : null}
          </ul>
          <ButtonsAt position="footer" size="sm" className="pt-2" />
        </div>
      </div>
      <div className="border-t border-black/5">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-5 text-xs text-foreground/60 sm:flex-row sm:items-center sm:justify-between">
          <p>{doc.footer.copyright || `© ${new Date().getFullYear()} ${s.clinic_name}`}</p>
          {doc.footer.show_policies && policies.length ? (
            <ul className="flex flex-wrap gap-x-4 gap-y-1">{policies.map((p) => <li key={p.slug}><Link href={`${base}/${p.slug}`} className="hover:text-foreground hover:underline">{p.label}</Link></li>)}</ul>
          ) : null}
        </div>
      </div>
    </footer>
  );
}

/** Phones: the "floating" buttons (usually Book appointment) stay within thumb reach at the bottom. */
function FloatingBar() {
  const { doc } = useSite();
  if (!doc.buttons.some((b) => b.visible && b.positions.includes("floating"))) return null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-black/5 bg-[color-mix(in_oklab,var(--site-bg)_92%,transparent)] p-3 backdrop-blur-md md:hidden" data-testid="floating-book">
      <ButtonsAt position="floating" size="lg" className="flex-nowrap" buttonClassName="flex-1" max={2} />
    </div>
  );
}
