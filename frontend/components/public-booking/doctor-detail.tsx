"use client";

import { useState } from "react";
import { ArrowLeft, Award, BadgeCheck, CalendarCheck2, Clock, Languages, Loader2, MapPin, Stethoscope, UsersRound, Video } from "lucide-react";
import { cn, formatPaise } from "@/lib/utils";
import { addressLine } from "./booking-shell";
import { DoctorPhoto } from "./doctor-browser";
import { servicePrice } from "./steps";
import { TimePicker } from "./time-picker";
import type { Branch, Professional, Service } from "@/types/catalog";
import type { PriceQuote, Slot } from "@/types/booking";

export function DoctorDetail({ slug, pro, doctorCount, services, serviceId, onService, branches, branchId, onBranch, initialDate, picked, onPick,
  onBook, booking, quote, tz, onBack }: {
  slug: string; pro: Professional | null; doctorCount: number; services: Service[]; serviceId: string | null; onService: (id: string) => void;
  branches: Branch[]; branchId: string | null; onBranch: (id: string) => void; initialDate?: string; picked: Slot | null; onPick: (s: Slot) => void;
  onBook: () => void; booking: boolean; quote: PriceQuote | undefined; tz: string; onBack: (() => void) | null;
}) {
  const [more, setMore] = useState(false);
  const service = services.find((s) => s.id === serviceId) ?? null;
  const name = pro?.display_name ?? "First available doctor";
  const stats = pro
    ? [
      pro.experience_years ? { icon: Award, value: `${pro.experience_years}+`, label: "Years exp." } : null,
      { icon: Stethoscope, value: String(services.length), label: services.length === 1 ? "Service" : "Services" },
      { icon: MapPin, value: String((pro.branches ?? []).length || branches.length), label: (pro.branches ?? []).length === 1 ? "Location" : "Locations" },
      pro.languages?.length ? { icon: Languages, value: String(pro.languages.length), label: pro.languages.length === 1 ? "Language" : "Languages" } : null,
    ].filter((x): x is NonNullable<typeof x> => !!x).slice(0, 3)
    : [
      { icon: UsersRound, value: String(doctorCount), label: "Doctors" },
      { icon: Stethoscope, value: String(services.length), label: "Services" },
      { icon: MapPin, value: String(branches.length), label: branches.length === 1 ? "Location" : "Locations" },
    ];
  const when = picked ? new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: tz }).format(new Date(picked.start_at)) : null;
  const fee = quote ? quote.total_amount_paise : service ? servicePrice(service, branchId).shown : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]" data-testid="doctor-detail">
      <div className="min-w-0 space-y-7 pb-32 lg:pb-0">
        {/* Header */}
        <section className="relative isolate overflow-hidden rounded-[2rem] bg-[var(--primary)] p-5 text-[var(--primary-foreground)] shadow-[0_20px_40px_-20px_color-mix(in_oklab,var(--primary)_70%,transparent)] sm:p-7">
          <div aria-hidden className="absolute -right-20 -top-24 -z-10 size-80 rounded-full bg-white/10" />
          <div className="flex items-center justify-between gap-3">
            {onBack ? <button type="button" onClick={onBack} aria-label="Back to doctors" className="grid size-10 place-items-center rounded-full bg-white/15 backdrop-blur transition-colors hover:bg-white/25"><ArrowLeft className="size-5" /></button> : <span />}
            <span className="text-sm font-medium">{pro ? "Doctor details" : "Earliest appointment"}</span>
            <span className="size-10" aria-hidden />
          </div>
          <div className="mt-5 flex items-end gap-4">
            <div className="min-w-0 flex-1 space-y-2 pb-1">
              {pro?.specialization || pro?.title ? <span className="inline-block rounded-full bg-white/20 px-3 py-1 text-xs font-semibold backdrop-blur">{pro.specialization ?? pro.title}</span> : null}
              <h1 className="text-2xl font-semibold leading-tight tracking-tight [font-family:var(--site-heading-font)] sm:text-3xl" data-testid="doctor-name">{name}</h1>
              {pro?.qualification ? <p className="text-sm">{pro.qualification}</p> : !pro ? <p className="text-sm">We show every free time; the doctor is confirmed with your slot.</p> : null}
            </div>
            {pro ? <DoctorPhoto pro={pro} className="size-28 shrink-0 ring-4 ring-white/30 sm:size-36" rounded="rounded-[1.6rem]" />
              : <span className="grid size-24 shrink-0 place-items-center rounded-[1.6rem] bg-white/15"><UsersRound className="size-12" aria-hidden /></span>}
          </div>
          <dl className="mt-6 grid grid-cols-3 gap-2.5">
            {stats.map((s) => (
              <div key={s.label} className="flex flex-col items-center rounded-2xl bg-white px-2 py-3 text-center text-gray-900 shadow-sm">
                <dt className="order-2 mt-1 text-xs font-semibold uppercase tracking-wide text-gray-600">{s.label}</dt>
                <dd className="order-1 text-xl font-semibold leading-none tabular-nums">{s.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* About */}
        {pro && (pro.biography || pro.registration_number || pro.consultation_modes?.includes("online")) ? (
          <section aria-labelledby="about-doctor" className="space-y-2">
            <h2 id="about-doctor" className="text-lg font-semibold tracking-tight">About</h2>
            {pro.biography ? (
              <p className={cn("whitespace-pre-line text-[15px] leading-relaxed text-gray-600", !more && "line-clamp-3")}>{pro.biography}</p>
            ) : null}
            {pro.biography && pro.biography.length > 180 ? <button type="button" className="text-sm font-semibold text-[var(--primary)] underline-offset-4 hover:underline" onClick={() => setMore((v) => !v)}>{more ? "Show less" : "Read more"}</button> : null}
            <ul className="flex flex-wrap gap-2 pt-1 text-xs text-gray-600">
              {pro.registration_number ? <li className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1"><BadgeCheck className="size-3.5" aria-hidden />Reg. {pro.registration_number}{pro.registration_council ? `, ${pro.registration_council}` : ""}</li> : null}
              {pro.consultation_modes?.includes("online") ? <li className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1"><Video className="size-3.5" aria-hidden />Video consultations</li> : null}
              {pro.languages?.length ? <li className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1"><Languages className="size-3.5" aria-hidden />{pro.languages.join(", ")}</li> : null}
            </ul>
          </section>
        ) : null}

        {/* Service */}
        {services.length > 1 || !service ? (
          <section aria-labelledby="choose-service" className="space-y-3">
            <h2 id="choose-service" className="text-lg font-semibold tracking-tight">Choose a service</h2>
            <div className="grid gap-2.5 sm:grid-cols-2" role="radiogroup" aria-label="Service">
              {services.map((s) => {
                const active = s.id === serviceId;
                const price = servicePrice(s, branchId);
                return (
                  <button key={s.id} type="button" role="radio" aria-checked={active} onClick={() => onService(s.id)} data-testid="pick-service"
                    className={cn("flex items-center gap-3 rounded-2xl border bg-white p-4 text-left transition-all", active ? "border-[var(--primary)] ring-2 ring-[color-mix(in_oklab,var(--primary)_25%,transparent)]" : "border-black/10 hover:border-[var(--primary)]")}>
                    <span className={cn("grid size-5 shrink-0 place-items-center rounded-full border-2", active ? "border-[var(--primary)]" : "border-gray-300")}>{active ? <span className="size-2.5 rounded-full bg-[var(--primary)]" /> : null}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-gray-900">{s.name}</span>
                      <span className="flex items-center gap-1 text-sm text-gray-500"><Clock className="size-3.5" aria-hidden />{s.duration_minutes} min{s.consultation_mode === "online" ? " · Online" : ""}</span>
                    </span>
                    <span className="shrink-0 text-right font-semibold text-gray-900">
                      {s.payment_mode === "free" ? "Free" : formatPaise(price.shown)}
                      {price.was !== null ? <span className="block text-xs font-normal text-gray-400 line-through">{formatPaise(price.was)}</span> : null}
                    </span>
                  </button>
                );
              })}
            </div>
            {!services.length ? <p className="text-sm text-gray-600">No service is bookable online with this doctor yet.</p> : null}
          </section>
        ) : null}

        {/* Location */}
        {service && branches.length > 1 ? (
          <section aria-labelledby="choose-location" className="space-y-3">
            <h2 id="choose-location" className="text-lg font-semibold tracking-tight">Location</h2>
            <div className="-mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none]" role="radiogroup" aria-label="Location">
              {branches.map((b) => {
                const active = b.id === branchId;
                return (
                  <button key={b.id} type="button" role="radio" aria-checked={active} onClick={() => onBranch(b.id)} data-testid="pick-branch"
                    className={cn("flex w-[15rem] shrink-0 items-start gap-2.5 rounded-2xl border p-3.5 text-left transition-all sm:w-auto sm:max-w-[22rem]", active ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-md" : "border-black/10 bg-white text-gray-900 hover:border-[var(--primary)]")}>
                    <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />
                    <span className="min-w-0"><span className="block font-semibold">{b.name}</span><span className={cn("line-clamp-1 text-xs", active ? "" : "text-gray-500")}>{addressLine(b.address) || "Address after booking"}</span></span>
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {/* Date and time */}
        {service && branchId ? (
          <section aria-labelledby="choose-time" className="space-y-3">
            <h2 id="choose-time" className="text-lg font-semibold tracking-tight">Choose date and time</h2>
            <TimePicker slug={slug} serviceId={service.id} branchId={branchId} professionalId={pro?.id} initialDate={initialDate} selected={picked} onSelect={(s) => onPick(s)} busy={booking} />
          </section>
        ) : service && !branchId && branches.length === 0 ? (
          <p className="rounded-3xl border border-dashed bg-white p-6 text-center text-sm text-gray-600">This service is not offered at any location with this doctor yet.</p>
        ) : null}
      </div>

      {/* Book bar: fixed at the bottom on phones, a sticky card beside the page on desktop */}
      <aside aria-label="Your selection" className="lg:sticky lg:top-24 lg:h-fit">
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-black/5 bg-white/95 px-4 pb-[max(env(safe-area-inset-bottom),0.75rem)] pt-3 shadow-[0_-10px_30px_-12px_rgb(0_0_0/0.25)] backdrop-blur lg:static lg:rounded-3xl lg:border lg:p-6 lg:shadow-sm">
          <div className="hidden space-y-3 pb-4 lg:block">
            <p className="text-sm font-semibold uppercase tracking-wide text-gray-500">Your appointment</p>
            <p className="font-semibold text-gray-900">{name}</p>
            <ul className="space-y-1.5 text-sm text-gray-600">
              <li className="flex items-center gap-2"><Stethoscope className="size-4" aria-hidden />{service?.name ?? "Choose a service"}</li>
              <li className="flex items-center gap-2"><MapPin className="size-4" aria-hidden />{branches.find((b) => b.id === branchId)?.name ?? "Choose a location"}</li>
              <li className="flex items-center gap-2"><CalendarCheck2 className="size-4" aria-hidden />{when ?? "Choose a time"}</li>
            </ul>
          </div>
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1 lg:hidden">
              <p className="truncate text-xs text-gray-500">{when ?? (service ? "Pick a time" : "Pick a service")}</p>
              <p className="text-lg font-semibold tabular-nums text-gray-900">{fee === null ? "—" : fee === 0 ? "Free" : formatPaise(fee)}</p>
            </div>
            <div className="hidden flex-1 items-baseline justify-between lg:flex"><span className="text-sm text-gray-500">Fee</span><span className="text-xl font-semibold tabular-nums">{fee === null ? "—" : fee === 0 ? "Free" : formatPaise(fee)}</span></div>
          </div>
          <button type="button" onClick={onBook} disabled={!picked || booking} data-testid="book-slot"
            className="mt-0 inline-flex h-13 w-auto items-center justify-center gap-2 rounded-full bg-[var(--primary)] px-6 text-base font-semibold text-[var(--primary-foreground)] shadow-[0_10px_24px_-10px_color-mix(in_oklab,var(--primary)_80%,transparent)] transition-all hover:brightness-110 disabled:opacity-45 disabled:shadow-none max-lg:absolute max-lg:right-4 max-lg:top-1/2 max-lg:-translate-y-1/2 max-lg:pb-0 lg:mt-4 lg:w-full">
            {booking ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <CalendarCheck2 className="size-5" aria-hidden />} Book appointment
          </button>
        </div>
      </aside>
    </div>
  );
}
