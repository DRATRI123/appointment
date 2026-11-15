"use client";

import Link from "next/link";
import { CalendarCheck2, CalendarOff, ChevronRight, MapPin, Phone } from "lucide-react";
import { BottomNav } from "./bottom-nav";
import { useDeviceBookings, type DeviceBooking } from "@/lib/device-bookings";
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
    <div className="bg-[color-mix(in_oklab,var(--primary)_5%,var(--site-bg))]">
      <div className="mx-auto max-w-6xl px-4 pb-16 pt-6 sm:pt-10">
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

/** /{clinic}/bookings: appointments booked in this browser, upcoming first. */
export function DeviceBookingsPage() {
  const { slug, base } = useSite();
  const q = useDeviceBookings(slug);
  const tzFmt = (iso: string, tz: string) => new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: tz }).format(new Date(iso));
  const Item = ({ b }: { b: DeviceBooking }) => {
    const a = b.appointment;
    const tone = STATUS_TONE[a.status] ?? "bg-gray-100 text-gray-700";
    return (
      <li>
        <Link href={`${base}/appointments/${a.reference}?t=${encodeURIComponent(b.token)}`} data-testid="device-booking"
          className="flex items-center gap-4 rounded-3xl bg-white p-4 shadow-[0_8px_30px_-14px_rgb(0_0_0/0.2)] ring-1 ring-black/5 transition-shadow hover:shadow-lg">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_12%,#fff)] text-[var(--primary)]"><CalendarCheck2 className="size-6" aria-hidden /></span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-semibold text-gray-900">{a.professional_name}</span>
            <span className="block truncate text-sm text-gray-600">{a.service_name} · {a.branch_name}</span>
            <span className="block text-sm text-gray-800">{tzFmt(a.start_at, a.timezone)}</span>
          </span>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{STATUS_LABEL[a.status] ?? a.status}</span>
        </Link>
      </li>
    );
  };
  return (
    <div className="bg-[color-mix(in_oklab,var(--primary)_5%,var(--site-bg))] pb-24 md:pb-0">
      <div className="mx-auto max-w-3xl space-y-8 px-4 py-8 sm:py-12">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight [font-family:var(--site-heading-font)] sm:text-3xl">My bookings</h1>
          <p className="mt-1 text-sm text-gray-600">Appointments booked on this device. Signed-in patients see every booking in their account.</p>
        </div>
        {q.isLoading ? <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="h-24 animate-pulse rounded-3xl bg-white" />)}</div> : (
          <>
            <section aria-labelledby="upcoming-h" className="space-y-3">
              <h2 id="upcoming-h" className="text-lg font-semibold">Upcoming</h2>
              {q.data?.upcoming.length ? <ul className="space-y-3">{q.data.upcoming.map((b) => <Item key={b.appointment.reference} b={b} />)}</ul>
                : <div className="rounded-3xl border border-dashed bg-white p-8 text-center"><p className="text-sm text-gray-600">No upcoming appointments on this device.</p>
                  <Link href={`${base}/book`} className="mt-4 inline-flex h-11 items-center rounded-full bg-[var(--primary)] px-5 text-sm font-semibold text-[var(--primary-foreground)]">Book an appointment</Link></div>}
            </section>
            {q.data?.past.length ? (
              <section aria-labelledby="past-h" className="space-y-3">
                <h2 id="past-h" className="text-lg font-semibold">Past and cancelled</h2>
                <ul className="space-y-3">{q.data.past.map((b) => <Item key={b.appointment.reference} b={b} />)}</ul>
              </section>
            ) : null}
            <p className="text-center text-sm"><Link href="/login" className="font-medium text-gray-700 underline underline-offset-4">Sign in to see all your bookings</Link></p>
          </>
        )}
      </div>
      <BottomNav />
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  pending_payment: "Payment due", pending_verification: "Payment check", confirmed: "Confirmed", checked_in: "Checked in", in_progress: "In progress",
  completed: "Completed", cancelled: "Cancelled", expired: "Expired", no_show: "Missed",
};
const STATUS_TONE: Record<string, string> = {
  pending_payment: "bg-amber-100 text-amber-900", pending_verification: "bg-sky-100 text-sky-900", confirmed: "bg-emerald-100 text-emerald-900",
  completed: "bg-gray-100 text-gray-700", cancelled: "bg-rose-100 text-rose-900", expired: "bg-rose-100 text-rose-900", no_show: "bg-rose-100 text-rose-900",
};

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
