"use client";

import Link from "next/link";
import { CalendarOff, ChevronRight, MapPin, Phone } from "lucide-react";
import { BookingFlow } from "@/components/public-booking/booking-flow";
import { addressLine } from "@/components/public-booking/booking-shell";
import { bookHref, phoneDigits } from "@/lib/site-links";
import { Markdown } from "./markdown";
import { BranchCard, DoctorCard, HoursTable, SectionView, ServiceCard, useCatalog } from "./sections";
import { useSite } from "./site-context";

export function SiteHome() {
  const { doc } = useSite();
  return <>{doc.sections.map((s) => <SectionView key={s.id} section={s} />)}</>;
}

function PageTitle({ title, crumbs, children }: { title: string; crumbs?: { label: string; href?: string }[]; children?: React.ReactNode }) {
  const { base, doc } = useSite();
  return (
    <div className="relative isolate overflow-hidden border-b border-black/5">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(800px_300px_at_90%_-20%,color-mix(in_oklab,var(--site-secondary)_25%,transparent),transparent_70%)]" />
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-12 sm:py-16">
        <nav aria-label="Breadcrumb"><ol className="flex flex-wrap items-center gap-1 text-sm opacity-70">
          <li><Link href={base} className="hover:underline">{doc.settings.site_name || doc.settings.clinic_name}</Link></li>
          {(crumbs ?? []).map((c) => <li key={c.label} className="flex items-center gap-1"><ChevronRight className="size-3.5" aria-hidden />{c.href ? <Link href={c.href} className="hover:underline">{c.label}</Link> : <span aria-current="page">{c.label}</span>}</li>)}
        </ol></nav>
        <h1 className="text-4xl font-semibold tracking-tight text-balance [font-family:var(--site-heading-font)] sm:text-5xl">{title}</h1>
        {children}
      </div>
    </div>
  );
}

export function BookPage() {
  const { org, doc } = useSite();
  if (org.settings.general?.booking_page_enabled === false) {
    return (
      <div className="mx-auto max-w-lg px-4 py-20 text-center">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-muted"><CalendarOff className="size-7 text-muted-foreground" aria-hidden /></span>
        <h1 className="mt-4 text-2xl font-semibold">{doc.settings.clinic_name} is not taking online bookings right now</h1>
        <p className="mt-2 text-muted-foreground">{doc.settings.phone ? <>Please call <a className="font-medium underline" href={`tel:${phoneDigits(doc.settings.phone)}`}>{doc.settings.phone}</a> to book.</> : "Please contact the clinic to book."}</p>
      </div>
    );
  }
  return (
    <div className="bg-[oklch(0.985_0.004_160)]/60">
      <div className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:pt-10">
        <h1 className="mb-6 text-sm font-semibold uppercase tracking-wider text-[var(--primary)]">Book an appointment</h1>
        <BookingFlow />
      </div>
    </div>
  );
}

/** /{clinic}/{name}: a custom page, a built-in policy page, or a location page — in that order. */
export function SegmentPage({ segment }: { segment: string }) {
  const { doc, org } = useSite();
  const page = doc.pages.find((p) => p.enabled && p.slug === segment);
  if (page) {
    return (
      <>
        <PageTitle title={page.title} crumbs={[{ label: page.title }]} />
        {page.body ? <div className="mx-auto max-w-3xl px-4 py-12"><Markdown source={page.body} className="text-lg" /></div> : null}
        {page.sections.map((s) => <SectionView key={s.id} section={s} />)}
      </>
    );
  }
  const legal = org.settings.legal ?? {};
  const policy = ({ privacy: ["Privacy policy", legal.privacy_policy], terms: ["Terms and conditions", legal.terms], "refund-policy": ["Refund policy", legal.refund_policy] } as Record<string, [string, unknown]>)[segment];
  if (policy && typeof policy[1] === "string" && policy[1]) {
    return (
      <>
        <PageTitle title={policy[0]} crumbs={[{ label: policy[0] }]} />
        <div className="mx-auto max-w-3xl px-4 py-12"><Markdown source={policy[1]} /></div>
      </>
    );
  }
  const branch = org.branches.find((b) => b.slug === segment);
  if (branch) return <BranchPage branchId={branch.id} />;
  return <NotFound />;
}

function BranchPage({ branchId }: { branchId: string }) {
  const { org, base, campaign } = useSite();
  const { services, pros } = useCatalog();
  const branch = org.branches.find((b) => b.id === branchId)!;
  const here = pros.filter((p) => (p.branches ?? []).some((b) => b.branch_id === branch.id));
  const line = addressLine(branch.address);
  return (
    <>
      <PageTitle title={branch.name} crumbs={[{ label: "Locations" }, { label: branch.name }]}>
        <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm opacity-80">
          {line ? <li className="flex items-center gap-1.5"><MapPin className="size-4" aria-hidden />{line}</li> : null}
          {branch.phone ? <li className="flex items-center gap-1.5"><Phone className="size-4" aria-hidden /><a href={`tel:${phoneDigits(branch.phone)}`} className="hover:underline">{branch.phone}</a></li> : null}
        </ul>
        <Link href={bookHref(base, { branch: branch.slug }, campaign)} className="inline-flex h-12 items-center rounded-full bg-[var(--primary)] px-6 text-base font-semibold text-[var(--primary-foreground)] shadow-sm hover:opacity-90" data-testid="branch-book">Book at {branch.name}</Link>
      </PageTitle>
      <div className="mx-auto grid max-w-6xl gap-12 px-4 py-14 lg:grid-cols-[1fr_340px]">
        <div className="space-y-12">
          {branch.description ? <Markdown source={branch.description} className="text-lg" /> : null}
          {here.length ? <section aria-labelledby="branch-doctors" className="space-y-5"><h2 id="branch-doctors" className="text-2xl font-semibold [font-family:var(--site-heading-font)]">Doctors at {branch.name}</h2><div className="grid gap-6 sm:grid-cols-2">{here.map((p) => <DoctorCard key={p.id} pro={p} compact />)}</div></section> : null}
          {services.length ? <section aria-labelledby="branch-services" className="space-y-5"><h2 id="branch-services" className="text-2xl font-semibold [font-family:var(--site-heading-font)]">Services</h2><div className="grid gap-6 sm:grid-cols-2">{services.slice(0, 8).map((s) => <ServiceCard key={s.id} service={s} showPrice />)}</div></section> : null}
        </div>
        <aside className="space-y-4">
          <BranchCard branch={branch} showHours={false} />
          {branch.business_hours ? <div className="rounded-3xl border border-black/5 bg-white p-6 text-gray-900 shadow-sm"><h2 className="mb-3 font-semibold">Opening hours</h2><HoursTable hours={branch.business_hours} /></div> : null}
        </aside>
      </div>
    </>
  );
}

function NotFound() {
  const { base } = useSite();
  return (
    <div className="mx-auto max-w-lg px-4 py-24 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-muted-foreground">This page may have been moved or removed.</p>
      <Link href={base} className="mt-6 inline-flex h-11 items-center rounded-full bg-[var(--primary)] px-5 text-sm font-semibold text-[var(--primary-foreground)]">Go to the home page</Link>
    </div>
  );
}
