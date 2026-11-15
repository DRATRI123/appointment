"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Award, CalendarDays, Clock, Languages, MapPin, Search, Stethoscope, UsersRound, X } from "lucide-react";
import { mediaUrl } from "@/services/catalog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeviceBookings } from "@/lib/device-bookings";
import { cn, formatPaise } from "@/lib/utils";
import { initials } from "./booking-shell";
import type { Category, Professional, Service } from "@/types/catalog";

export function servicesOf(pro: Professional, services: Service[]): Service[] {
  const ids = new Set((pro.services ?? []).filter((l) => l.is_active !== false).map((l) => l.service_id));
  return services.filter((s) => ids.has(s.id));
}

function minFee(pro: Professional, services: Service[]): number | null {
  const fees = servicesOf(pro, services).filter((s) => s.payment_mode !== "free").map((s) => s.discounted_price_paise ?? s.price_paise).filter((p): p is number => typeof p === "number" && p > 0);
  return fees.length ? Math.min(...fees) : null;
}

/** Photo, or initials on a soft brand-coloured disc. Never a stock face. */
export function DoctorPhoto({ pro, className, rounded = "rounded-3xl" }: { pro: Pick<Professional, "display_name" | "profile_photo_url">; className?: string; rounded?: string }) {
  return (
    <span className={cn("relative grid shrink-0 place-items-center overflow-hidden bg-[radial-gradient(circle_at_50%_35%,color-mix(in_oklab,var(--primary)_22%,#fff),color-mix(in_oklab,var(--primary)_8%,#fff))]", rounded, className)}>
      {pro.profile_photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(pro.profile_photo_url)} alt="" className="h-full w-full object-cover object-top" />
      ) : (
        <span className="text-3xl font-semibold tracking-tight text-[var(--primary)]">{initials(pro.display_name)}</span>
      )}
    </span>
  );
}

export function DoctorBrowser({ slug, clinicName, base, professionals, services, categories, loading, allowAny, serviceFilter, onPick, onAny, bookingsHref }: {
  slug: string; clinicName: string; base: string; professionals: Professional[]; services: Service[]; categories: Category[]; loading: boolean;
  allowAny: boolean; serviceFilter: Service | null; onPick: (pro: Professional) => void; onAny: () => void; bookingsHref: string;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const device = useDeviceBookings(slug);
  const next = device.data?.upcoming[0];

  const usedCategories = useMemo(() => categories.filter((c) => services.some((s) => s.category_id === c.id)), [categories, services]);
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return professionals.filter((p) => {
      const theirs = servicesOf(p, services);
      if (serviceFilter && !theirs.some((s) => s.id === serviceFilter.id)) return false;
      if (category && !theirs.some((s) => s.category_id === category)) return false;
      if (!q) return true;
      const hay = [p.display_name, p.specialization, p.title, p.qualification, ...(p.languages ?? []), ...theirs.map((s) => s.name)].filter(Boolean).join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [professionals, services, query, category, serviceFilter]);

  return (
    <div className="space-y-7" data-testid="doctor-browser">
      {/* Brand header with search */}
      <section className="relative isolate overflow-hidden rounded-[2rem] bg-[var(--primary)] px-5 pb-6 pt-7 text-[var(--primary-foreground)] shadow-[0_20px_40px_-20px_color-mix(in_oklab,var(--primary)_70%,transparent)] sm:px-8 sm:pt-9">
        <div aria-hidden className="absolute -right-16 -top-20 -z-10 size-72 rounded-full bg-white/10" />
        <div aria-hidden className="absolute -bottom-24 right-24 -z-10 size-56 rounded-full bg-white/5" />
        <Stethoscope aria-hidden className="absolute right-6 top-6 -z-10 size-24 opacity-15 sm:right-10 sm:size-32" />
        <p className="text-sm font-medium">{clinicName}</p>
        <h1 className="mt-1 max-w-md text-2xl font-semibold leading-tight tracking-tight text-balance [font-family:var(--site-heading-font)] sm:text-3xl">
          {serviceFilter ? <>Book {serviceFilter.name}</> : <>Find your doctor and book in minutes</>}
        </h1>
        <label className="relative mt-5 block">
          <span className="sr-only">Search doctors, specialities or treatments</span>
          <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-gray-400" aria-hidden />
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search doctor, speciality or treatment"
            className="h-12 w-full rounded-2xl border-0 bg-white pl-12 pr-11 text-[15px] text-gray-900 shadow-sm outline-none placeholder:text-gray-500 focus-visible:ring-4 focus-visible:ring-white/40" data-testid="doctor-search" />
          {query ? <button type="button" onClick={() => setQuery("")} className="absolute right-3 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-full text-gray-500 hover:bg-gray-100" aria-label="Clear search"><X className="size-4" /></button> : null}
        </label>
      </section>

      {/* Specialities */}
      {usedCategories.length > 1 && !serviceFilter ? (
        <section aria-label="Specialities" className="-mx-4 overflow-x-auto px-4 [scrollbar-width:none]">
          <div className="flex gap-2.5">
            {[{ id: null as string | null, name: "All" }, ...usedCategories].map((c) => {
              const active = category === c.id;
              return (
                <button key={c.id ?? "all"} type="button" aria-pressed={active} onClick={() => setCategory(c.id)} data-testid="speciality-chip"
                  className={cn("shrink-0 rounded-full border px-4 py-2 text-sm font-semibold transition-all", active ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-md" : "border-black/10 bg-white text-gray-700 hover:border-[var(--primary)]")}>
                  {c.name}
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      {/* Upcoming appointment from this device */}
      {next ? (
        <section aria-labelledby="upcoming-title" className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 id="upcoming-title" className="text-lg font-semibold tracking-tight">Upcoming appointment</h2>
            <Link href={bookingsHref} className="text-sm font-medium text-gray-600 underline-offset-4 hover:underline">See all</Link>
          </div>
          <Link href={`${base}/appointments/${next.appointment.reference}?t=${encodeURIComponent(next.token)}`} data-testid="upcoming-card"
            className="flex items-center gap-4 rounded-3xl bg-[color-mix(in_oklab,var(--primary)_10%,#fff)] p-4 transition-shadow hover:shadow-lg">
            <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-[var(--primary)] text-[var(--primary-foreground)]"><CalendarDays className="size-6" aria-hidden /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold text-gray-900">{next.appointment.professional_name}</span>
              <span className="block truncate text-sm text-gray-600">{next.appointment.service_name}</span>
              <span className="mt-1 flex items-center gap-1.5 text-sm font-medium text-gray-800"><Clock className="size-3.5" aria-hidden />
                {new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: next.appointment.timezone }).format(new Date(next.appointment.start_at))}
              </span>
            </span>
            <ArrowRight className="size-5 shrink-0 text-gray-500" aria-hidden />
          </Link>
        </section>
      ) : null}

      {/* Doctors */}
      <section aria-labelledby="doctors-title" className="space-y-4">
        <div className="flex items-end justify-between gap-3">
          <h2 id="doctors-title" className="text-lg font-semibold tracking-tight">{query || category ? `${list.length} doctor${list.length === 1 ? "" : "s"} found` : "Our doctors"}</h2>
        </div>
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-72 rounded-3xl" />)}</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {allowAny && list.length > 1 && !query ? (
              <button type="button" onClick={onAny} data-testid="pick-any"
                className="group flex items-center gap-4 rounded-3xl border-2 border-dashed border-[color-mix(in_oklab,var(--primary)_40%,transparent)] bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:border-[var(--primary)] hover:shadow-lg motion-reduce:hover:translate-y-0 sm:flex-col sm:items-start sm:justify-between sm:gap-6 sm:p-6">
                <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_12%,#fff)] text-[var(--primary)] sm:size-14"><UsersRound className="size-6 sm:size-7" aria-hidden /></span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-gray-900 sm:text-lg">First available doctor</span>
                  <span className="mt-0.5 block text-sm text-gray-600">Earliest free times across {list.length} doctors</span>
                </span>
                <span className="inline-flex shrink-0 items-center gap-1.5 text-sm font-semibold text-[var(--primary)]"><span className="hidden sm:inline">Choose a time</span> <ArrowRight className="size-5 transition-transform group-hover:translate-x-0.5 sm:size-4" aria-hidden /></span>
              </button>
            ) : null}
            {list.map((p) => <DoctorCard key={p.id} pro={p} fee={minFee(p, services)} onPick={() => onPick(p)} />)}
          </div>
        )}
        {!loading && !list.length ? (
          <p className="rounded-3xl border border-dashed bg-white p-8 text-center text-sm text-gray-600" role="status">
            {query ? <>No doctor matches “{query}”. <button type="button" className="font-medium underline" onClick={() => setQuery("")}>Clear search</button></> : "No doctor is bookable online yet. Please call the clinic."}
          </p>
        ) : null}
      </section>
    </div>
  );
}

function DoctorCard({ pro, fee, onPick }: { pro: Professional; fee: number | null; onPick: () => void }) {
  const branches = (pro.branches ?? []).map((b) => b.branch_name).filter(Boolean);
  return (
    <article className="group flex flex-col overflow-hidden rounded-3xl bg-white shadow-[0_8px_30px_-12px_rgb(0_0_0/0.18)] ring-1 ring-black/5 transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_20px_40px_-16px_rgb(0_0_0/0.25)] motion-reduce:hover:translate-y-0">
      <button type="button" onClick={onPick} className="flex flex-1 flex-col text-left focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[var(--primary)]" data-testid="pick-professional" aria-label={`${pro.display_name}, view details and book`}>
        <div className="p-3 pb-0">
          <DoctorPhoto pro={pro} className="aspect-[5/4] w-full" rounded="rounded-[1.4rem]" />
        </div>
        <div className="flex flex-1 flex-col gap-2 p-5">
          <div>
            <h3 className="text-lg font-semibold leading-snug text-gray-900">{pro.display_name}</h3>
            {pro.specialization || pro.title ? <p className="text-sm font-medium text-[var(--primary)]">{pro.specialization ?? pro.title}</p> : null}
            {pro.qualification ? <p className="text-sm text-gray-500">{pro.qualification}</p> : null}
          </div>
          <ul className="flex flex-wrap gap-1.5 text-xs text-gray-600">
            {pro.experience_years ? <li className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1"><Award className="size-3.5" aria-hidden />{pro.experience_years}+ yrs</li> : null}
            {pro.languages?.length ? <li className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1"><Languages className="size-3.5" aria-hidden />{pro.languages.slice(0, 2).join(", ")}</li> : null}
            {branches.length ? <li className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1"><MapPin className="size-3.5" aria-hidden />{branches.length > 1 ? `${branches.length} locations` : branches[0]}</li> : null}
          </ul>
          <div className="mt-auto flex items-center justify-between gap-3 pt-3">
            {fee !== null ? <span className="text-sm text-gray-600">From <b className="text-base text-gray-900">{formatPaise(fee)}</b></span> : <span />}
            <span className="inline-flex h-10 items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-foreground)] transition-transform group-hover:translate-x-0.5">Book <ArrowRight className="size-4" aria-hidden /></span>
          </div>
        </div>
      </button>
    </article>
  );
}
