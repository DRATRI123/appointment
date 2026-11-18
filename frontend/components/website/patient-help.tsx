"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2, ChevronRight, FileText, LifeBuoy, Loader2, Paperclip, Plus, Send, Star, X } from "lucide-react";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { CATEGORY_LABELS, STATUS_LABELS, openAttachment, patientHelp, type Ticket, type TicketDetail } from "@/services/helpdesk";
import type { Appointment } from "@/types/booking";

const STATUS_TONE: Record<string, string> = {
  open: "bg-sky-100 text-sky-900", pending_customer: "bg-amber-100 text-amber-900", resolved: "bg-emerald-100 text-emerald-900", closed: "bg-gray-100 text-gray-700",
};
const MAX_FILE_MB = 5;
const ACCEPT = "image/png,image/jpeg,image/webp,application/pdf";

const stamp = (iso: string) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso));
const field = "w-full rounded-2xl border border-black/10 bg-white px-4 text-base text-gray-900 outline-none transition focus:border-[var(--primary)] focus:ring-4 focus:ring-[color-mix(in_oklab,var(--primary)_18%,transparent)]";
const primaryBtn = "inline-flex h-11 items-center justify-center gap-2 rounded-full bg-[var(--primary)] px-5 text-sm font-semibold text-[var(--primary-foreground)] shadow-sm disabled:opacity-60";

/** The patient's questions to the clinic: list, new request, and the conversation. */
export function PatientHelp({ orgId, slug, appointments, initialRequest, initialBooking }: {
  orgId: string; slug: string; appointments: Appointment[]; initialRequest?: string | null; initialBooking?: string | null;
}) {
  type View = { kind: "list" } | { kind: "new"; booking?: string | null } | { kind: "thread"; id: string };
  const [view, setViewState] = useState<View>(
    initialRequest ? { kind: "thread", id: initialRequest } : initialBooking ? { kind: "new", booking: initialBooking } : { kind: "list" });
  // Keep the address in step, so a reload or a shared link shows the same thing (a sent question, not the empty form).
  const setView = (v: View) => {
    setViewState(v);
    const q = v.kind === "thread" ? `?tab=help&request=${encodeURIComponent(v.id)}` : "?tab=help";
    try { window.history.replaceState(window.history.state, "", `${window.location.pathname}${q}`); } catch { /* ignore */ }
  };
  const options = useQuery({ queryKey: ["help-options", slug], queryFn: () => patientHelp.options(slug), staleTime: 5 * 60_000 });
  const list = useQuery({ queryKey: ["help-requests", orgId], queryFn: () => patientHelp.list(orgId) });

  if (options.data && !options.data.enabled) {
    return <div className="rounded-3xl bg-white p-6 text-sm text-gray-700 shadow-sm ring-1 ring-black/5">This clinic does not take questions online. Please call or visit the clinic.</div>;
  }
  if (view.kind === "new") {
    return <NewRequest orgId={orgId} appointments={appointments} booking={view.booking ?? null} onCancel={() => setView({ kind: "list" })} onCreated={(id) => setView({ kind: "thread", id })} />;
  }
  if (view.kind === "thread") return <Thread orgId={orgId} id={view.id} onBack={() => setView({ kind: "list" })} />;

  const rows = list.data ?? [];
  return (
    <div className="space-y-4" data-testid="help-list">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-600">Ask about a booking, payment, refund or report. The clinic answers here; we let you know when they do.</p>
        <button type="button" className={primaryBtn} onClick={() => setView({ kind: "new" })} data-testid="help-new"><Plus className="size-4" aria-hidden /> Ask a question</button>
      </div>
      {list.isLoading ? <div className="h-24 animate-pulse rounded-3xl bg-white" /> : rows.length === 0 ? (
        <div className="rounded-3xl border border-dashed bg-white p-8 text-center">
          <LifeBuoy className="mx-auto size-8 text-[var(--primary)]" aria-hidden />
          <p className="mt-3 font-medium text-gray-900">No questions yet</p>
          <p className="text-sm text-gray-600">Need something? Ask the clinic and keep the whole conversation in one place.</p>
        </div>
      ) : (
        <ul className="divide-y divide-black/5 overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-black/5">
          {rows.map((t) => <Row key={t.id} t={t} onOpen={() => setView({ kind: "thread", id: t.id })} />)}
        </ul>
      )}
    </div>
  );
}

function Row({ t, onOpen }: { t: Ticket; onOpen: () => void }) {
  return (
    <li>
      <button type="button" onClick={onOpen} className="flex w-full items-center gap-3 p-4 text-left hover:bg-black/[0.02]" data-testid="help-request">
        <span className={cn("size-2.5 shrink-0 rounded-full", t.unread ? "bg-[var(--primary)]" : "bg-transparent")} aria-label={t.unread ? "New reply" : undefined} />
        <span className="min-w-0 flex-1">
          <span className={cn("block truncate text-gray-900", t.unread ? "font-semibold" : "font-medium")}>{t.subject}</span>
          <span className="block truncate text-sm text-gray-600">#{t.number} · {t.category_label} · {stamp(t.last_activity_at)}</span>
        </span>
        <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold", STATUS_TONE[t.status])}>{STATUS_LABELS[t.status]}</span>
        <ChevronRight className="size-4 shrink-0 text-gray-400" aria-hidden />
      </button>
    </li>
  );
}

function FilePick({ file, onChange }: { file: File | null; onChange: (f: File | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex items-center gap-2">
      <input ref={input} type="file" accept={ACCEPT} className="sr-only" aria-label="Attach a photo or PDF" data-testid="help-file"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          if (f && f.size > MAX_FILE_MB * 1024 * 1024) { toast.error(`The file is larger than ${MAX_FILE_MB} MB.`); e.target.value = ""; return; }
          onChange(f);
        }} />
      {file ? (
        <span className="inline-flex max-w-full items-center gap-2 rounded-full bg-gray-100 px-3 py-1.5 text-sm text-gray-800">
          <Paperclip className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{file.name}</span>
          <button type="button" aria-label="Remove the attachment" onClick={() => { onChange(null); if (input.current) input.current.value = ""; }}><X className="size-3.5" /></button>
        </span>
      ) : (
        <button type="button" onClick={() => input.current?.click()} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-black/5">
          <Paperclip className="size-4" aria-hidden /> Attach photo or PDF
        </button>
      )}
    </div>
  );
}

function NewRequest({ orgId, appointments, booking, onCancel, onCreated }: {
  orgId: string; appointments: Appointment[]; booking: string | null; onCancel: () => void; onCreated: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState(booking ? "booking" : "");
  const [reference, setReference] = useState(booking ?? "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => patientHelp.create(orgId, { category, subject: subject.trim(), body: body.trim(), appointment_reference: reference || undefined }, file),
    onSuccess: (t) => { toast.success(`Sent. Your request number is #${t.number}.`); void queryClient.invalidateQueries({ queryKey: ["help-requests", orgId] }); onCreated(t.id); },
    onError: (e) => setError(errorMessage(e)),
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!category) return setError("Choose what your question is about.");
    if (subject.trim().length < 3) return setError("Add a short title.");
    if (body.trim().length < 2) return setError("Write your question.");
    setError(null);
    create.mutate();
  };
  return (
    <form onSubmit={submit} className="space-y-5 rounded-3xl bg-white p-5 shadow-sm ring-1 ring-black/5 sm:p-6" data-testid="help-form" noValidate>
      <div className="flex items-center gap-2">
        <button type="button" onClick={onCancel} className="grid size-9 place-items-center rounded-full hover:bg-black/5" aria-label="Back"><ArrowLeft className="size-4" /></button>
        <h3 className="text-lg font-semibold text-gray-900">Ask the clinic</h3>
      </div>
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-gray-900">What is it about?</legend>
        <div className="flex flex-wrap gap-2">
          {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
            <label key={value} className={cn("cursor-pointer rounded-full border px-4 py-2 text-sm font-medium transition has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--primary)]",
              category === value ? "border-[var(--primary)] bg-[color-mix(in_oklab,var(--primary)_10%,#fff)] text-[var(--primary)]" : "border-black/10 text-gray-700 hover:border-black/20")}>
              <input type="radio" name="help-category" value={value} className="sr-only" checked={category === value} onChange={() => setCategory(value)} />{label}
            </label>
          ))}
        </div>
      </fieldset>
      {appointments.length ? (
        <div className="space-y-1.5">
          <label htmlFor="help_booking" className="block text-sm font-medium text-gray-900">Booking (optional)</label>
          <select id="help_booking" className={cn(field, "h-12")} value={reference} onChange={(e) => setReference(e.target.value)}>
            <option value="">Not about one booking</option>
            {appointments.map((a) => (
              <option key={a.reference} value={a.reference}>
                {new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: a.timezone }).format(new Date(a.start_at))} · {a.service_name} · {a.professional_name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="space-y-1.5">
        <label htmlFor="help_subject" className="block text-sm font-medium text-gray-900">Title</label>
        <input id="help_subject" className={cn(field, "h-12")} maxLength={160} placeholder="e.g. Payment done but booking not confirmed" value={subject} onChange={(e) => setSubject(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="help_body" className="block text-sm font-medium text-gray-900">Your question</label>
        <textarea id="help_body" className={cn(field, "min-h-32 py-3")} maxLength={4000} value={body} onChange={(e) => setBody(e.target.value)}
          placeholder="Tell the clinic what happened and what you need." />
        <p className="text-xs text-gray-500">Please do not write card numbers or passwords. Health details are kept private and encrypted.</p>
      </div>
      <FilePick file={file} onChange={setFile} />
      {error ? <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">{error}</p> : null}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={onCancel} className="inline-flex h-11 items-center rounded-full px-5 text-sm font-semibold text-gray-700 hover:bg-black/5">Cancel</button>
        <button type="submit" className={primaryBtn} disabled={create.isPending} data-testid="help-send">{create.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" aria-hidden />} Send to clinic</button>
      </div>
    </form>
  );
}

function Thread({ orgId, id, onBack }: { orgId: string; id: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const q = useQuery({
    queryKey: ["help-request", orgId, id],
    // Opening it marks the clinic's reply as read: refresh the list (and its "new reply" badge) too.
    queryFn: async () => { const t = await patientHelp.get(orgId, id); void queryClient.invalidateQueries({ queryKey: ["help-requests", orgId] }); return t; },
    refetchInterval: 30_000,
  });
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [rating, setRating] = useState(0);
  const set = (t: TicketDetail) => { queryClient.setQueryData(["help-request", orgId, id], t); void queryClient.invalidateQueries({ queryKey: ["help-requests", orgId] }); };
  const reply = useMutation({
    mutationFn: () => patientHelp.reply(orgId, id, body.trim(), file),
    onSuccess: (t) => { set(t); setBody(""); setFile(null); toast.success("Sent"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const resolve = useMutation({ mutationFn: (r: number | null) => patientHelp.resolve(orgId, id, r), onSuccess: (t) => { set(t); toast.success("Thank you!"); }, onError: (e) => toast.error(errorMessage(e)) });

  if (q.isLoading) return <div className="h-64 animate-pulse rounded-3xl bg-white" />;
  if (!q.data) return <div className="rounded-3xl bg-white p-6 text-sm text-gray-700">This request was not found. <button className="underline" onClick={onBack}>Back</button></div>;
  const t = q.data;
  const closed = t.status === "closed";
  return (
    <div className="space-y-4" data-testid="help-thread">
      <div className="flex items-start gap-2">
        <button type="button" onClick={onBack} className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-full hover:bg-black/5" aria-label="Back to my questions"><ArrowLeft className="size-4" /></button>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-gray-900">{t.subject}</h3>
          <p className="text-sm text-gray-600">#{t.number} · {t.category_label}{t.appointment ? ` · ${t.appointment.service_name}` : ""}</p>
        </div>
        <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold", STATUS_TONE[t.status])} data-testid="help-status">{STATUS_LABELS[t.status]}</span>
      </div>

      <ol className="space-y-3">
        {t.messages.map((m) => m.author_kind === "system" ? (
          <li key={m.id} className="text-center text-xs text-gray-500">{m.body} · {stamp(m.created_at)}</li>
        ) : (
          <li key={m.id} className={cn("flex", m.author_kind === "customer" ? "justify-end" : "justify-start")} data-testid="help-message">
            <div className={cn("max-w-[85%] rounded-3xl px-4 py-3 shadow-sm", m.author_kind === "customer" ? "rounded-br-lg bg-[var(--primary)] text-[var(--primary-foreground)]" : "rounded-bl-lg bg-white text-gray-900 ring-1 ring-black/5")}>
              <p className={cn("mb-1 text-xs font-semibold", m.author_kind === "customer" ? "opacity-80" : "text-[var(--primary)]")}>{m.author_kind === "customer" ? "You" : `${m.author_name} · clinic`}</p>
              <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{m.body}</p>
              {m.attachment ? (
                <button type="button" onClick={() => openAttachment(patientHelp.attachmentUrl(orgId, t.id, m.id)).catch((e) => toast.error(errorMessage(e)))}
                  className={cn("mt-2 inline-flex max-w-full items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium", m.author_kind === "customer" ? "bg-white/20" : "bg-gray-100")}>
                  <FileText className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{m.attachment.name ?? "Attachment"}</span>
                </button>
              ) : null}
              <p className="mt-1 text-[11px] opacity-70">{stamp(m.created_at)}</p>
            </div>
          </li>
        ))}
      </ol>

      {closed ? (
        <p className="rounded-2xl bg-gray-50 p-4 text-sm text-gray-700">This request is closed. If you need more help, ask a new question.</p>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); if (body.trim()) reply.mutate(); }} className="space-y-2 rounded-3xl bg-white p-4 shadow-sm ring-1 ring-black/5">
          <label htmlFor="help_reply" className="sr-only">Your reply</label>
          <textarea id="help_reply" className={cn(field, "min-h-24 py-3")} maxLength={4000} placeholder={t.status === "resolved" ? "Still need help? Reply to reopen." : "Write a reply"}
            value={body} onChange={(e) => setBody(e.target.value)} data-testid="help-reply" />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FilePick file={file} onChange={setFile} />
            <button type="submit" className={primaryBtn} disabled={!body.trim() || reply.isPending} data-testid="help-reply-send">{reply.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" aria-hidden />} Send</button>
          </div>
        </form>
      )}

      {t.status === "resolved" || t.status === "closed" ? (
        t.rating ? <p className="flex items-center justify-center gap-1 text-sm text-gray-600">You rated this help {t.rating}/5 <Star className="size-4 fill-amber-400 text-amber-400" aria-hidden /></p> : (
          <div className="rounded-3xl bg-white p-4 text-center shadow-sm ring-1 ring-black/5">
            <p className="text-sm font-medium text-gray-900">How helpful was the clinic?</p>
            <div className="mt-2 flex justify-center gap-1" role="radiogroup" aria-label="Rating">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} out of 5`} onClick={() => { setRating(n); resolve.mutate(n); }} data-testid={`help-rate-${n}`}>
                  <Star className={cn("size-7", n <= rating ? "fill-amber-400 text-amber-400" : "text-gray-300")} />
                </button>
              ))}
            </div>
          </div>
        )
      ) : (
        <button type="button" onClick={() => resolve.mutate(null)} disabled={resolve.isPending} data-testid="help-solved"
          className="mx-auto flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium text-gray-700 hover:bg-black/5">
          <CheckCircle2 className="size-4 text-emerald-600" aria-hidden /> My question is answered
        </button>
      )}
    </div>
  );
}
