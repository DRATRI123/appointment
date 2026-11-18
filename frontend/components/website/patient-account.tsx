"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarCheck2, ChevronRight, CreditCard, LogOut, MapPin, Plus, Trash2, UserRound, Users, Video } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { customerBooking } from "@/services/booking";
import { customerSelfService } from "@/services/customers";
import { paymentsService } from "@/services/payments";
import type { Appointment } from "@/types/booking";
import type { Payment } from "@/types/payment";
import { useSite } from "./site-context";

const OPEN = new Set(["pending_payment", "pending_verification", "confirmed", "checked_in", "in_progress"]);
const STATUS: Record<string, { label: string; tone: string }> = {
  pending_payment: { label: "Payment due", tone: "bg-amber-100 text-amber-900" },
  pending_verification: { label: "Payment being checked", tone: "bg-sky-100 text-sky-900" },
  confirmed: { label: "Confirmed", tone: "bg-emerald-100 text-emerald-900" },
  checked_in: { label: "Checked in", tone: "bg-emerald-100 text-emerald-900" },
  in_progress: { label: "In progress", tone: "bg-emerald-100 text-emerald-900" },
  completed: { label: "Completed", tone: "bg-gray-100 text-gray-700" },
  cancelled: { label: "Cancelled", tone: "bg-rose-100 text-rose-900" },
  expired: { label: "Expired", tone: "bg-rose-100 text-rose-900" },
  no_show: { label: "Missed", tone: "bg-rose-100 text-rose-900" },
};
const PAYMENT: Record<string, { label: string; tone: string }> = {
  verified: { label: "Paid", tone: "bg-emerald-100 text-emerald-900" },
  submitted: { label: "Being checked", tone: "bg-sky-100 text-sky-900" },
  under_review: { label: "Being checked", tone: "bg-sky-100 text-sky-900" },
  awaiting_payment: { label: "To pay", tone: "bg-amber-100 text-amber-900" },
  initiated: { label: "To pay", tone: "bg-amber-100 text-amber-900" },
  rejected: { label: "Not accepted", tone: "bg-rose-100 text-rose-900" },
  expired: { label: "Expired", tone: "bg-gray-100 text-gray-700" },
  cancelled: { label: "Cancelled", tone: "bg-gray-100 text-gray-700" },
  refund_requested: { label: "Refund requested", tone: "bg-violet-100 text-violet-900" },
  refund_processed: { label: "Refunded", tone: "bg-violet-100 text-violet-900" },
};

const money = (paise: number, currency = "INR") => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: paise % 100 ? 2 : 0 }).format(paise / 100);
const when = (iso: string, tz: string) => new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: tz }).format(new Date(iso));
const dayParts = (iso: string, tz: string) => ({
  day: new Intl.DateTimeFormat("en-IN", { day: "numeric", timeZone: tz }).format(new Date(iso)),
  month: new Intl.DateTimeFormat("en-IN", { month: "short", timeZone: tz }).format(new Date(iso)),
});

/** +919876543210 → +91 98765 43210 (Indian numbers; others as stored). */
function prettyMobile(m: string): string {
  const x = /^\+91(\d{5})(\d{5})$/.exec(m);
  return x ? `+91 ${x[1]} ${x[2]}` : m;
}

/** What the patient still has to pay, or how it was settled, in one short line. */
function paymentLine(a: Appointment): { text: string; due: boolean } | null {
  const due = Math.max(0, a.advance_due_paise - a.paid_amount_paise);
  if (a.total_amount_paise <= 0) return { text: "Free", due: false };
  if (["cancelled", "expired"].includes(a.status)) return a.paid_amount_paise > 0 ? { text: `${money(a.paid_amount_paise, a.currency)} paid`, due: false } : null;
  if (a.status === "pending_payment" && due > 0) return { text: `${money(due, a.currency)} to pay online`, due: true };
  if (a.status === "pending_verification") return { text: "We are checking your payment", due: false };
  if (a.paid_amount_paise >= a.total_amount_paise) return { text: `${money(a.paid_amount_paise, a.currency)} paid`, due: false };
  if (a.paid_amount_paise > 0) return { text: `${money(a.paid_amount_paise, a.currency)} paid · ${money(a.total_amount_paise - a.paid_amount_paise, a.currency)} at the clinic`, due: false };
  return { text: `${money(a.total_amount_paise, a.currency)} · pay at the clinic`, due: false };
}

type Tab = "bookings" | "payments" | "family" | "preferences";

/** The patient's own area on the clinic's website: bookings, payments, family members and message preferences. */
export function PatientAccount() {
  const { base, slug, org } = useSite();
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("bookings");
  const orgId = org.organization.id;
  const appts = useQuery({ queryKey: ["my-appointments"], queryFn: customerBooking.mine });
  const mine = (appts.data ?? []).filter((a) => a.organization_slug === slug);
  const [now] = useState(() => Date.now());
  const upcoming = mine.filter((a) => OPEN.has(a.status) && new Date(a.end_at).getTime() >= now).sort((a, b) => a.start_at.localeCompare(b.start_at));
  const past = mine.filter((a) => !upcoming.includes(a)).sort((a, b) => b.start_at.localeCompare(a.start_at));
  const toPay = upcoming.filter((a) => paymentLine(a)?.due).length;
  const initials = (user?.full_name ?? "").split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "P";

  const tabs: { id: Tab; label: string; icon: React.ReactNode; badge?: number }[] = [
    { id: "bookings", label: "Bookings", icon: <CalendarCheck2 className="size-4" aria-hidden />, badge: toPay || undefined },
    { id: "payments", label: "Payments", icon: <CreditCard className="size-4" aria-hidden /> },
    { id: "family", label: "Family", icon: <Users className="size-4" aria-hidden /> },
    { id: "preferences", label: "Messages", icon: <UserRound className="size-4" aria-hidden /> },
  ];

  return (
    <div className="space-y-6" data-testid="patient-account">
      <div className="flex items-center gap-4 rounded-3xl bg-white p-5 shadow-[0_8px_30px_-14px_rgb(0_0_0/0.2)] ring-1 ring-black/5">
        <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-[var(--primary)] text-lg font-semibold text-[var(--primary-foreground)]">{initials}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-semibold text-gray-900" data-testid="patient-name">{user?.full_name}</p>
          <p className="truncate text-sm text-gray-600">{user?.mobile ? prettyMobile(user.mobile) : user?.email}</p>
        </div>
        <button type="button" className="inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-gray-700 hover:bg-black/5" data-testid="patient-sign-out"
          onClick={async () => { await logout(); await queryClient.invalidateQueries({ queryKey: ["device-bookings"] }); toast.success("Signed out"); }}>
          <LogOut className="size-4" aria-hidden /> <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>

      <div role="tablist" aria-label="My account" className="grid grid-cols-4 gap-1 rounded-3xl bg-white p-1 shadow-sm ring-1 ring-black/5 sm:rounded-full">
        {tabs.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} id={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={cn("relative flex flex-col items-center justify-center gap-0.5 rounded-2xl px-1 py-2 text-xs font-semibold transition sm:flex-row sm:gap-1.5 sm:rounded-full sm:py-2.5 sm:text-sm",
              tab === t.id ? "bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm" : "text-gray-600 hover:bg-black/5")}>
            {t.icon}<span>{t.label}</span>
            {t.badge ? <span className="absolute -right-0.5 -top-0.5 grid size-5 place-items-center rounded-full bg-amber-500 text-[11px] text-white" aria-label={`${t.badge} to pay`}>{t.badge}</span> : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "bookings" ? (
          appts.isLoading ? <Loading /> : (
            <div className="space-y-8">
              <section aria-labelledby="up-h" className="space-y-3">
                <h2 id="up-h" className="text-lg font-semibold">Upcoming</h2>
                {upcoming.length ? <ul className="space-y-3">{upcoming.map((a) => <BookingCard key={a.id} a={a} base={base} />)}</ul> : (
                  <div className="rounded-3xl border border-dashed bg-white p-8 text-center">
                    <p className="text-sm text-gray-600">No upcoming appointments.</p>
                    <Link href={`${base}/book`} className="mt-4 inline-flex h-11 items-center rounded-full bg-[var(--primary)] px-5 text-sm font-semibold text-[var(--primary-foreground)]">Book an appointment</Link>
                  </div>
                )}
              </section>
              {past.length ? (
                <section aria-labelledby="past-h" className="space-y-3">
                  <h2 id="past-h" className="text-lg font-semibold">Past and cancelled</h2>
                  <ul className="space-y-3">{past.map((a) => <BookingCard key={a.id} a={a} base={base} past />)}</ul>
                </section>
              ) : null}
            </div>
          )
        ) : tab === "payments" ? <Payments slug={slug} base={base} /> : tab === "family" ? <Family orgId={orgId} /> : <Preferences orgId={orgId} />}
      </div>
    </div>
  );
}

function Loading() {
  return <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="h-28 animate-pulse rounded-3xl bg-white" />)}</div>;
}

function BookingCard({ a, base, past }: { a: Appointment; base: string; past?: boolean }) {
  const s = STATUS[a.status] ?? { label: a.status, tone: "bg-gray-100 text-gray-700" };
  const pay = paymentLine(a);
  const d = dayParts(a.start_at, a.timezone);
  const href = `${base}/appointments/${a.reference}`;
  return (
    <li className={cn("rounded-3xl bg-white p-4 shadow-[0_8px_30px_-14px_rgb(0_0_0/0.2)] ring-1 ring-black/5 sm:p-5", past && "opacity-90")} data-testid="device-booking">
      <div className="flex gap-4">
        <span className="grid w-14 shrink-0 place-content-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_10%,#fff)] py-2 text-center text-[var(--primary)]">
          <span className="text-xl font-bold leading-none">{d.day}</span><span className="mt-1 text-xs font-semibold uppercase">{d.month}</span>
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="font-semibold text-gray-900">{a.professional_name}</p>
            <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", s.tone)} data-testid="booking-status-chip">{s.label}</span>
          </div>
          <p className="text-sm text-gray-700">{a.service_name}</p>
          <p className="text-sm text-gray-600">{when(a.start_at, a.timezone)}</p>
          <p className="flex items-center gap-1 text-sm text-gray-600">
            {a.consultation_mode === "online" ? <><Video className="size-3.5" aria-hidden /> Online consultation</> : <><MapPin className="size-3.5" aria-hidden /> {a.branch_name}</>}
          </p>
          {pay ? <p className={cn("text-sm font-medium", pay.due ? "text-amber-800" : "text-gray-800")} data-testid="booking-payment">{pay.text}</p> : null}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 border-t border-black/5 pt-3">
        {pay?.due && !past ? <Link href={href} className="inline-flex h-10 items-center rounded-full bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-foreground)]">Pay now</Link> : null}
        {!past && a.meeting_link ? <a href={a.meeting_link} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-full border border-black/10 px-4 text-sm font-semibold text-gray-800 hover:bg-black/5"><Video className="size-4" aria-hidden /> Join</a> : null}
        <Link href={href} className="inline-flex h-10 items-center gap-1 rounded-full border border-black/10 px-4 text-sm font-semibold text-gray-800 hover:bg-black/5" data-testid="booking-open">
          {past ? "Details" : a.can_reschedule || a.can_cancel ? "Details · change or cancel" : "Details"} <ChevronRight className="size-4" aria-hidden />
        </Link>
        <span className="ml-auto self-center font-mono text-xs text-gray-400">{a.reference.slice(0, 16)}</span>
      </div>
    </li>
  );
}

function Payments({ slug, base }: { slug: string; base: string }) {
  const q = useQuery({ queryKey: ["my-payments"], queryFn: () => paymentsService.mine() as Promise<(Payment & { organization_slug?: string })[]> });
  if (q.isLoading) return <Loading />;
  const rows = (q.data ?? []).filter((p) => p.organization_slug === slug);
  if (!rows.length) return <div className="rounded-3xl border border-dashed bg-white p-8 text-center text-sm text-gray-600">No payments yet.</div>;
  return (
    <ul className="divide-y divide-black/5 overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-black/5" data-testid="patient-payments">
      {rows.map((p) => {
        const s = PAYMENT[p.status] ?? { label: p.status, tone: "bg-gray-100 text-gray-700" };
        return (
          <li key={p.id} className="flex items-center gap-4 p-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_10%,#fff)] text-[var(--primary)]"><CreditCard className="size-5" aria-hidden /></span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-gray-900">{money(p.verified_amount_paise ?? p.amount_paise, p.currency)} <span className="font-normal text-gray-600">· {p.service_name ?? "Appointment"}</span></p>
              <p className="text-sm text-gray-600">{p.appointment_start_at ? when(p.appointment_start_at, p.appointment_timezone ?? "Asia/Kolkata") : null}{p.rejection_reason ? ` · ${p.rejection_reason}` : ""}</p>
            </div>
            <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold", s.tone)}>{s.label}</span>
            {p.appointment_reference ? <Link href={`${base}/appointments/${p.appointment_reference}`} aria-label="Open the booking" className="grid size-9 shrink-0 place-items-center rounded-full hover:bg-black/5"><ChevronRight className="size-4" aria-hidden /></Link> : null}
          </li>
        );
      })}
    </ul>
  );
}

function Family({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient();
  const deps = useQuery({ queryKey: ["my-dependents", orgId], queryFn: () => customerSelfService.dependents(orgId) });
  const [form, setForm] = useState({ full_name: "", relationship_label: "child", date_of_birth: "" });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-dependents", orgId] });
  const add = useMutation({
    mutationFn: () => customerSelfService.addDependent(orgId, { ...form, full_name: form.full_name.trim(), date_of_birth: form.date_of_birth || null }),
    onSuccess: () => { toast.success("Family member added"); setForm({ full_name: "", relationship_label: "child", date_of_birth: "" }); void refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({ mutationFn: (id: string) => customerSelfService.removeDependent(orgId, id), onSuccess: () => { toast.success("Removed"); void refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const input = "h-11 w-full rounded-xl border border-black/10 bg-white px-3 text-sm text-gray-900 outline-none focus:border-[var(--primary)]";
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">Add the people you book for. Choose them under &quot;Booking for&quot; when you book.</p>
      <ul className="divide-y divide-black/5 overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-black/5">
        {deps.isLoading ? <li className="p-4"><div className="h-10 animate-pulse rounded-xl bg-gray-100" /></li> : null}
        {deps.data?.map((d) => (
          <li key={d.id} className="flex items-center gap-3 p-4" data-testid="family-member">
            <span className="grid size-10 place-items-center rounded-full bg-gray-100 text-sm font-semibold text-gray-700">{d.full_name[0]?.toUpperCase()}</span>
            <span className="min-w-0 flex-1"><span className="block font-medium text-gray-900">{d.full_name}</span><span className="text-sm capitalize text-gray-600">{d.relationship_label}</span></span>
            <button type="button" aria-label={`Remove ${d.full_name}`} className="grid size-9 place-items-center rounded-full text-gray-500 hover:bg-rose-50 hover:text-rose-700" onClick={() => { if (confirm(`Remove ${d.full_name}?`)) remove.mutate(d.id); }}><Trash2 className="size-4" /></button>
          </li>
        ))}
        {deps.data?.length === 0 ? <li className="p-6 text-center text-sm text-gray-600">No family members yet.</li> : null}
      </ul>
      <form className="grid gap-3 rounded-3xl bg-white p-4 shadow-sm ring-1 ring-black/5 sm:grid-cols-[1fr_140px_160px_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); add.mutate(); }} data-testid="family-form">
        <label className="space-y-1 text-sm font-medium">Name<input className={input} required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
        <label className="space-y-1 text-sm font-medium">Relationship
          <select className={input} value={form.relationship_label} onChange={(e) => setForm({ ...form, relationship_label: e.target.value })}>
            {[["child", "Child"], ["spouse", "Spouse"], ["parent", "Parent"], ["sibling", "Sibling"], ["other", "Other"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-sm font-medium">Date of birth<input type="date" className={input} value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} /></label>
        <button type="submit" disabled={add.isPending} className="inline-flex h-11 items-center justify-center gap-1.5 rounded-full bg-[var(--primary)] px-5 text-sm font-semibold text-[var(--primary-foreground)] disabled:opacity-60"><Plus className="size-4" aria-hidden />Add</button>
      </form>
    </div>
  );
}

function Preferences({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["my-profile", orgId], queryFn: () => customerSelfService.profile(orgId) });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => customerSelfService.updateProfile(orgId, body),
    onSuccess: () => { toast.success("Saved"); void queryClient.invalidateQueries({ queryKey: ["my-profile", orgId] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (profile.isLoading) return <Loading />;
  if (!profile.data) return <div className="rounded-3xl bg-white p-6 text-sm text-gray-600">Your preferences appear here after your first booking at this clinic.</div>;
  const prefs = { sms: true, whatsapp: true, email: true, ...(profile.data.communication_preferences ?? {}) } as Record<string, boolean>;
  const consent = { marketing: false, ...(profile.data.consent ?? {}) } as Record<string, boolean>;
  return (
    <ul className="divide-y divide-black/5 overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-black/5">
      <Row id="sms" label="SMS" help="Booking confirmations and reminders" busy={save.isPending} on={prefs.sms !== false} onChange={(v) => save.mutate({ communication_preferences: { ...prefs, sms: v } })} />
      <Row id="whatsapp" label="WhatsApp" help="Confirmations, reminders and payment updates" busy={save.isPending} on={prefs.whatsapp !== false} onChange={(v) => save.mutate({ communication_preferences: { ...prefs, whatsapp: v } })} />
      <Row id="email" label="Email" help="Confirmations and receipts" busy={save.isPending} on={prefs.email !== false} onChange={(v) => save.mutate({ communication_preferences: { ...prefs, email: v } })} />
      <Row id="marketing" label="Offers and health tips" help="Occasional messages from the clinic" busy={save.isPending} on={consent.marketing === true} onChange={(v) => save.mutate({ consent: { ...consent, marketing: v } })} />
    </ul>
  );
}

function Row({ label, help, on, onChange, id, busy }: { label: string; help: string; on: boolean; onChange: (v: boolean) => void; id: string; busy: boolean }) {
  return (
    <li className="flex items-center gap-4 p-4">
      <span className="min-w-0 flex-1"><span className="block font-medium text-gray-900">{label}</span><span className="text-sm text-gray-600">{help}</span></span>
      <button type="button" role="switch" aria-checked={on} aria-label={label} data-testid={`pref-${id}`} onClick={() => onChange(!on)} disabled={busy}
        className={cn("relative h-7 w-12 shrink-0 rounded-full transition", on ? "bg-[var(--primary)]" : "bg-gray-300")}>
        <span className={cn("absolute top-1 size-5 rounded-full bg-white shadow transition-all", on ? "left-6" : "left-1")} />
      </button>
    </li>
  );
}
