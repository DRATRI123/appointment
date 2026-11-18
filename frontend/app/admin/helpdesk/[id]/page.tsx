"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, CalendarDays, FileText, Lock, Paperclip, Send, Star, UserRound, X } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { PriorityBadge, StatusBadge } from "@/components/helpdesk/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CATEGORY_LABELS, STAFF_STATUS_LABELS, helpdesk, openAttachment, type StaffTicketDetail } from "@/services/helpdesk";

/** One patient request: the conversation, the reply box (or an internal note), and who handles it. */
export default function HelpdeskTicketPage() {
  const { id } = useParams<{ id: string }>();
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canWrite = hasPermission("helpdesk:write");
  const q = useQuery({ queryKey: ["desk-ticket", orgId, id], queryFn: () => helpdesk.get(id), enabled: !!orgId, refetchInterval: 30_000 });
  const agents = useQuery({ queryKey: ["desk-agents", orgId], queryFn: helpdesk.agents, enabled: !!orgId && canWrite });
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const apply = (t: StaffTicketDetail) => {
    queryClient.setQueryData(["desk-ticket", orgId, id], t);
    void queryClient.invalidateQueries({ queryKey: ["desk-tickets", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["desk-summary", orgId] });
  };
  const reply = useMutation({
    mutationFn: (next: "resolved" | null) => helpdesk.reply(id, body.trim(), { internal, next_status: next }, file),
    onSuccess: (t, next) => {
      apply(t);
      setBody(""); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      toast.success(internal ? "Note added" : next ? "Sent and marked solved" : "Reply sent. The patient is told.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const update = useMutation({ mutationFn: (b: Parameters<typeof helpdesk.update>[1]) => helpdesk.update(id, b), onSuccess: (t) => { apply(t); toast.success("Updated"); }, onError: (e) => toast.error(errorMessage(e)) });

  if (q.isLoading) return <Skeleton className="mx-auto h-96 max-w-6xl" />;
  if (!q.data) return <p className="text-sm text-muted-foreground">Request not found. <Link className="underline" href="/admin/helpdesk">Back to the help desk</Link></p>;
  const t = q.data;
  const closed = t.status === "closed";

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <Link href="/admin/helpdesk" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Help desk</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight md:text-2xl" data-testid="ticket-subject">{t.subject}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className="font-mono">#{t.number}</span><StatusBadge status={t.status} /><PriorityBadge priority={t.priority} /><span>{t.category_label}</span>
            {t.overdue ? <span className="inline-flex items-center gap-1 font-medium text-destructive"><AlertTriangle className="size-3.5" aria-hidden />First reply overdue</span> : null}
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <ol className="space-y-3" data-testid="ticket-messages">
            {t.messages.map((m) => m.author_kind === "system" ? (
              <li key={m.id} className="text-center text-xs text-muted-foreground">{m.body} · {formatDateTime(m.created_at)}</li>
            ) : (
              <li key={m.id} className={cn("flex", m.author_kind === "staff" ? "justify-end" : "justify-start")} data-testid={m.internal ? "ticket-note" : "ticket-message"}>
                <div className={cn("max-w-[85%] rounded-2xl border px-4 py-3",
                  m.internal ? "border-amber-200 bg-amber-50" : m.author_kind === "staff" ? "border-primary/20 bg-primary/5" : "bg-card")}>
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                    {m.internal ? <><Lock className="size-3" aria-hidden />Internal note · {m.author_name}</> : m.author_kind === "staff" ? m.author_name : `${m.author_name} (patient)`}
                  </p>
                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{m.body}</p>
                  {m.attachment ? (
                    <button type="button" className="mt-2 inline-flex max-w-full items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs font-medium"
                      onClick={() => openAttachment(helpdesk.attachmentUrl(t.id, m.id), orgId).catch((e) => toast.error(errorMessage(e)))}>
                      <FileText className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{m.attachment.name ?? "Attachment"}</span>
                    </button>
                  ) : null}
                  <p className="mt-1 text-[11px] text-muted-foreground">{formatDateTime(m.created_at)}</p>
                </div>
              </li>
            ))}
          </ol>

          {canWrite ? (
            <Card className={cn(internal && "border-amber-300")}>
              <CardContent className="space-y-3 pt-6">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="desk_reply" className="text-sm font-medium">{internal ? "Internal note (only staff see it)" : "Reply to the patient"}</Label>
                  <label className="flex items-center gap-2 text-sm"><Lock className="size-3.5 text-muted-foreground" aria-hidden />Internal note
                    <Switch checked={internal} onCheckedChange={setInternal} data-testid="desk-internal" /></label>
                </div>
                <Textarea id="desk_reply" rows={5} maxLength={4000} value={body} onChange={(e) => setBody(e.target.value)} data-testid="desk-reply"
                  placeholder={closed && !internal ? "This request is closed. You can still add an internal note." : internal ? "What colleagues should know" : "Write your answer. The patient gets a message to read it."}
                  className={cn(internal && "bg-amber-50/50")} />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <input ref={fileInput} type="file" className="sr-only" accept="image/png,image/jpeg,image/webp,application/pdf" aria-label="Attach a file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                    {file ? <Badge variant="outline" className="gap-1"><Paperclip className="size-3" />{file.name}<button type="button" aria-label="Remove the attachment" onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = ""; }}><X className="size-3" /></button></Badge>
                      : <Button type="button" variant="ghost" size="sm" onClick={() => fileInput.current?.click()}><Paperclip /> Attach</Button>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {!internal && !closed && t.status !== "resolved" ? (
                      <Button variant="outline" disabled={!body.trim() || reply.isPending} onClick={() => reply.mutate("resolved")} data-testid="desk-send-resolve">Send and mark solved</Button>
                    ) : null}
                    <Button disabled={!body.trim() || reply.isPending || (closed && !internal)} onClick={() => reply.mutate(null)} data-testid="desk-send"><Send /> {internal ? "Add note" : "Send reply"}</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Details</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="space-y-1"><Label htmlFor="desk_status">Status</Label>
                <NativeSelect id="desk_status" value={t.status} disabled={!canWrite || update.isPending} onChange={(e) => update.mutate({ status: e.target.value })} data-testid="desk-status">
                  {Object.entries(STAFF_STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </NativeSelect></div>
              <div className="space-y-1"><Label htmlFor="desk_priority">Priority</Label>
                <NativeSelect id="desk_priority" value={t.priority} disabled={!canWrite || update.isPending} onChange={(e) => update.mutate({ priority: e.target.value })}>
                  {["low", "normal", "high", "urgent"].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
                </NativeSelect></div>
              <div className="space-y-1"><Label htmlFor="desk_assignee">Assigned to</Label>
                <NativeSelect id="desk_assignee" value={t.assigned_to?.id ?? ""} disabled={!canWrite || update.isPending} data-testid="desk-assignee"
                  onChange={(e) => update.mutate(e.target.value ? { assigned_to: e.target.value } : { unassign: true })}>
                  <option value="">Unassigned</option>
                  {(agents.data ?? (t.assigned_to ? [t.assigned_to] : [])).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </NativeSelect></div>
              <div className="space-y-1"><Label htmlFor="desk_category">Topic</Label>
                <NativeSelect id="desk_category" value={t.category} disabled={!canWrite || update.isPending} onChange={(e) => update.mutate({ category: e.target.value })}>
                  {Object.entries(CATEGORY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </NativeSelect></div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-3 pt-6 text-sm">
              {t.customer ? <p className="flex items-center gap-2"><UserRound className="size-4 text-muted-foreground" aria-hidden />
                {hasPermission("customers:read") ? <Link className="font-medium hover:underline" href={`/admin/customers/${t.customer.id}`}>{t.customer.name}</Link> : <span className="font-medium">{t.customer.name}</span>}</p> : null}
              {t.appointment ? <p className="flex items-start gap-2"><CalendarDays className="mt-0.5 size-4 text-muted-foreground" aria-hidden />
                <span><Link className="font-medium hover:underline" href={`/admin/appointments?search=${encodeURIComponent(t.appointment.reference)}`}>{t.appointment.service_name}</Link>
                  <span className="block text-muted-foreground">{formatDateTime(t.appointment.start_at, t.appointment.timezone)}</span></span></p> : <p className="text-muted-foreground">Not about one booking</p>}
              {t.branch_name ? <p className="text-muted-foreground">Branch: {t.branch_name}</p> : null}
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-t pt-3 text-xs">
                <dt className="text-muted-foreground">Asked</dt><dd>{formatDateTime(t.created_at)}</dd>
                <dt className="text-muted-foreground">Reply due</dt><dd className={cn(t.overdue && "font-medium text-destructive")}>{t.first_response_due_at ? formatDateTime(t.first_response_due_at) : "—"}</dd>
                <dt className="text-muted-foreground">First reply</dt><dd>{t.first_response_at ? formatDateTime(t.first_response_at) : "Not yet"}</dd>
                {t.resolved_at ? <><dt className="text-muted-foreground">Solved</dt><dd>{formatDateTime(t.resolved_at)}</dd></> : null}
                {t.rating ? <><dt className="text-muted-foreground">Rating</dt><dd className="inline-flex items-center gap-1">{t.rating}/5<Star className="size-3 fill-amber-400 text-amber-400" aria-hidden /></dd></> : null}
              </dl>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
