"use client";

import { createContext, useContext, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2, CalendarOff, Globe, Mail, MapPin, Phone } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { safeHex, textOn } from "./brand";
import type { PublicOrganization } from "@/types/catalog";

export interface BookingContextValue {
  slug: string;
  data: PublicOrganization;
  /** Base path for links inside the booking experience: "/akshar-clinic" or "/embed/akshar-clinic". */
  base: string;
  /** Where "Book" links go: "/akshar-clinic/book" on the clinic website, the frame's own page when embedded. */
  bookPath: string;
  embedded: boolean;
}

export const BookingContext = createContext<BookingContextValue | null>(null);

export function useBooking() {
  const ctx = useContext(BookingContext);
  if (!ctx) throw new Error("useBooking outside BookingShell");
  return ctx;
}

export function addressLine(address: Record<string, unknown> | null | undefined): string {
  const a = (address ?? {}) as Record<string, string>;
  return [a.line1, a.line2, a.city, a.state, a.postal_code].filter(Boolean).join(", ");
}

export function initials(name: string): string {
  return name.split(/\s+/).filter((x) => x && !x.endsWith(".")).slice(0, 2).map((x) => x[0]?.toUpperCase()).join("") || name[0]?.toUpperCase() || "?";
}

/** When shown inside another website's iframe, tell the parent page how tall we are so it can size the frame. */
function useEmbedResize(enabled: boolean) {
  useEffect(() => {
    if (!enabled || typeof window === "undefined" || window.parent === window) return;
    let last = 0;
    let frame = 0;
    // Measure the content, not the document: inside an iframe scrollHeight is never smaller than the frame itself,
    // so the frame could grow but never shrink back.
    const contentHeight = () => Array.from(document.body.children).reduce((max, el) => {
      if (getComputedStyle(el).position === "fixed") return max; // toasts and dialogs
      return Math.max(max, el.getBoundingClientRect().bottom + window.scrollY);
    }, 0);
    const post = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const height = Math.ceil(contentHeight());
        if (height < 1 || Math.abs(height - last) < 2) return;
        last = height;
        // Only a height is sent; never URLs, names or booking details.
        window.parent.postMessage({ type: "appointment-booking:resize", height }, "*");
      });
    };
    const resize = new ResizeObserver(post);
    const watch = () => { for (const el of Array.from(document.body.children)) resize.observe(el); post(); };
    const mutations = new MutationObserver(watch);
    mutations.observe(document.body, { childList: true });
    watch();
    return () => { cancelAnimationFrame(frame); resize.disconnect(); mutations.disconnect(); };
  }, [enabled]);
}

export function BookingShell({ slug, embedded = false, children }: { slug: string; embedded?: boolean; children: React.ReactNode }) {
  const query = useQuery({ queryKey: ["public-org", slug], queryFn: () => publicCatalog.organization(slug), retry: false, staleTime: 60_000 });
  const pathname = usePathname();
  useEmbedResize(embedded);

  if (query.isLoading) {
    return (
      <div className={cn("bg-muted/30", !embedded && "min-h-dvh")}>
        <div className="mx-auto max-w-6xl space-y-6 px-4 py-10">
          <Skeleton className="h-10 w-56" />
          {!embedded ? <Skeleton className="h-44 rounded-3xl" /> : null}
          <div className="grid gap-4 sm:grid-cols-2"><Skeleton className="h-28 rounded-2xl" /><Skeleton className="h-28 rounded-2xl" /></div>
        </div>
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Notice icon={Building2} title="We couldn't find this booking page" body="Check the link you were given, or contact the clinic directly." />
    );
  }
  const data = query.data;
  const general = data.settings.general ?? {};
  if (general.booking_page_enabled === false) {
    return <Notice icon={CalendarOff} title={`${data.organization.name} is not taking online bookings right now`} body={data.organization.phone ? `Please call ${data.organization.phone} to book.` : "Please contact the clinic to book."} />;
  }
  const base = embedded ? `/embed/${slug}` : `/${slug}`;
  const onBookingPage = pathname === base;
  return (
    <BookingContext.Provider value={{ slug, data, base, bookPath: base, embedded }}>
      <div className={cn("flex min-h-dvh flex-col bg-[oklch(0.985_0.004_160)] dark:bg-background", embedded && "min-h-0", onBookingPage && !embedded && "pb-20 lg:pb-0")} data-testid="booking-shell">
        <ClinicHeader />
        <main className={cn("mx-auto w-full max-w-6xl flex-1 px-4", embedded ? "py-4" : "py-8 sm:py-10")}>{children}</main>
        <ClinicFooter />
      </div>
    </BookingContext.Provider>
  );
}

function Logo({ size = "md", onBrand = false }: { size?: "md" | "lg"; onBrand?: boolean }) {
  const { data } = useBooking();
  const org = data.organization;
  const brand = safeHex(data.settings.branding?.primary_color);
  // On the brand-coloured hero, a plain initials tile would vanish: use a light glass tile there instead.
  const style = org.logo_url ? { background: "#fff" } : onBrand ? undefined : { background: brand, color: textOn(brand) };
  return (
    <span
      className={cn("grid shrink-0 place-items-center overflow-hidden font-semibold shadow-sm ring-1 ring-black/5", size === "lg" ? "size-16 rounded-2xl text-2xl sm:size-20" : "size-9 rounded-xl text-sm",
        onBrand && !org.logo_url && "bg-white/15 ring-white/35 backdrop-blur-sm")}
      style={style}
    >
      {org.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(org.logo_url)} alt="" className="h-full w-full object-contain p-1" />
      ) : initials(org.name)}
    </span>
  );
}

function ClinicHeader() {
  const { data, base, embedded } = useBooking();
  const org = data.organization;
  return (
    <header className={cn("z-30 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70", !embedded && "sticky top-0")}>
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
        <Link href={base} className="flex min-w-0 items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
          <Logo />
          <span className="truncate font-semibold tracking-tight">{org.name}</span>
        </Link>
        <div className="ml-auto flex items-center gap-1">
          {org.phone ? (
            <a href={`tel:${org.phone}`} className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              <Phone className="size-4" aria-hidden /> <span className="hidden sm:inline">{org.phone}</span><span className="sm:hidden">Call</span>
            </a>
          ) : null}
        </div>
      </div>
    </header>
  );
}

function ClinicFooter() {
  const { data, embedded } = useBooking();
  const org = data.organization;
  const address = addressLine(org.address) || addressLine(data.branches[0]?.address);
  if (embedded) {
    return <footer className="px-4 pb-4 text-center text-xs text-muted-foreground">Secure booking for {org.name}</footer>;
  }
  return (
    <footer className="mt-8 border-t bg-background">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm sm:grid-cols-[1fr_auto]">
        <div className="space-y-2">
          <p className="font-semibold">{org.name}</p>
          <ul className="space-y-1.5 text-muted-foreground">
            {address ? <li className="flex gap-2"><MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />{address}</li> : null}
            {org.phone ? <li className="flex gap-2"><Phone className="mt-0.5 size-4 shrink-0" aria-hidden /><a className="hover:text-foreground" href={`tel:${org.phone}`}>{org.phone}</a></li> : null}
            {org.email ? <li className="flex gap-2"><Mail className="mt-0.5 size-4 shrink-0" aria-hidden /><a className="hover:text-foreground" href={`mailto:${org.email}`}>{org.email}</a></li> : null}
            {org.website ? <li className="flex gap-2"><Globe className="mt-0.5 size-4 shrink-0" aria-hidden /><a className="hover:text-foreground" href={org.website} rel="noopener noreferrer" target="_blank">{org.website.replace(/^https?:\/\//, "")}</a></li> : null}
          </ul>
        </div>
        <div className="flex flex-col gap-1.5 text-muted-foreground sm:items-end">
          <Link href="/privacy" className="hover:text-foreground">Privacy</Link>
          <Link href="/terms" className="hover:text-foreground">Terms</Link>
          <Link href="/refund-policy" className="hover:text-foreground">Refund policy</Link>
        </div>
      </div>
    </footer>
  );
}

function Notice({ icon: Icon, title, body }: { icon: React.ComponentType<{ className?: string }>; title: string; body: string }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-muted/30 px-4">
      <div className="pb-enter max-w-md space-y-3 rounded-3xl border bg-background p-8 text-center shadow-sm" role="status">
        <span className="mx-auto grid size-12 place-items-center rounded-full bg-muted"><Icon className="size-6 text-muted-foreground" /></span>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}
