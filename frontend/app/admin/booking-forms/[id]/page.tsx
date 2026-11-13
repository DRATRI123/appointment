"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { formsService } from "@/services/customers";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { DynamicForm } from "@/components/forms/dynamic-form";
import { errorMessage } from "@/lib/errors";
import { FIELD_TYPE_LABEL, type FieldType, type FormField } from "@/types/customer";

const OPTION_TYPES: FieldType[] = ["dropdown", "radio", "multi_select"];
const OPERATORS = ["equals", "not_equals", "in", "not_in", "is_true", "is_false", "is_empty", "is_not_empty", "gt", "lt"];

function blankField(n: number): FormField {
  return { key: `field_${n}`, label: "New question", field_type: "text", placeholder: null, help_text: null, is_required: false, sort_order: n, options: null, validation: null, conditions: null, default_value: null, is_sensitive: false };
}

export default function FormBuilderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { hasPermission } = useAuth();
  const router = useRouter();
  const canWrite = hasPermission("booking_forms:write");
  const queryClient = useQueryClient();
  const form = useQuery({ queryKey: ["form", id], queryFn: () => formsService.get(id) });
  if (form.isLoading) return <Skeleton className="h-64" />;
  if (!form.data) return <p>Form not found.</p>;
  return <Builder key={`${form.data.id}-${form.data.updated_at}`} initial={form.data} canWrite={canWrite} onChanged={(newId) => { if (newId !== id) router.push(`/admin/booking-forms/${newId}`); else queryClient.invalidateQueries({ queryKey: ["form", id] }); }} onDeleted={() => router.push("/admin/booking-forms")} />;
}

function Builder({ initial, canWrite, onChanged, onDeleted }: { initial: NonNullable<Awaited<ReturnType<typeof formsService.get>>>; canWrite: boolean; onChanged: (id: string) => void; onDeleted: () => void }) {
  const [meta, setMeta] = useState({ name: initial.name, description: initial.description ?? "", instructions: initial.instructions ?? "" });
  const [fields, setFields] = useState<FormField[]>(initial.fields.map((f, i) => ({ ...f, sort_order: i + 1 })));
  const [selected, setSelected] = useState<number>(0);
  const [preview, setPreview] = useState<Record<string, unknown>>({});
  const dirty = JSON.stringify(fields) !== JSON.stringify(initial.fields.map((f, i) => ({ ...f, sort_order: i + 1 }))) || meta.name !== initial.name || meta.description !== (initial.description ?? "") || meta.instructions !== (initial.instructions ?? "");

  const save = useMutation({
    mutationFn: () => formsService.update(initial.id, { name: meta.name, description: meta.description || null, instructions: meta.instructions || null, fields: fields.map((f, i) => ({ ...f, id: undefined, sort_order: i + 1 })) }),
    onSuccess: (f) => { toast.success(f.version !== initial.version ? `Saved as draft version ${f.version}` : "Saved"); onChanged(f.id); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const publish = useMutation({ mutationFn: () => formsService.publish(initial.id), onSuccess: () => { toast.success("Published. Customers now see this version."); onChanged(initial.id); }, onError: (e) => toast.error(errorMessage(e)) });
  const remove = useMutation({ mutationFn: () => formsService.remove(initial.id), onSuccess: () => { toast.success("Form deleted"); onDeleted(); }, onError: (e) => toast.error(errorMessage(e)) });

  const update = (i: number, patch: Partial<FormField>) => setFields(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const move = (i: number, dir: -1 | 1) => { const j = i + dir; if (j < 0 || j >= fields.length) return; const copy = [...fields]; [copy[i], copy[j]] = [copy[j], copy[i]]; setFields(copy); setSelected(j); };
  const f = fields[selected];

  return (
    <div className="mx-auto max-w-7xl">
      <Link href="/admin/booking-forms" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Booking forms</Link>
      <PageHeader title={initial.name} description={`Version ${initial.version} · ${initial.is_published ? "published" : "draft"}${initial.is_published ? " · saving field changes creates a new draft version" : ""}`} actions={canWrite ? <div className="flex gap-2"><Button variant="ghost" className="text-destructive" onClick={() => { if (confirm("Delete this form?")) remove.mutate(); }}>Delete</Button><Button variant="outline" onClick={() => save.mutate()} disabled={!dirty || save.isPending} data-testid="save-form">Save</Button>{!initial.is_published ? <Button onClick={() => publish.mutate()} disabled={dirty || publish.isPending || fields.length === 0} data-testid="publish-form">Publish</Button> : null}</div> : null} />
      <div className="grid gap-6 lg:grid-cols-[300px_1fr_360px]">
        <Card>
          <CardHeader><CardTitle className="text-base">Fields</CardTitle><CardDescription>Click to edit, use arrows to reorder.</CardDescription></CardHeader>
          <CardContent className="space-y-1">
            {fields.map((x, i) => <button key={i} type="button" onClick={() => setSelected(i)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${selected === i ? "bg-accent" : "hover:bg-muted"}`} data-testid="builder-field"><span className="truncate">{x.label}{x.is_required ? " *" : ""}</span><Badge variant="outline" className="shrink-0 text-[10px]">{FIELD_TYPE_LABEL[x.field_type]}</Badge></button>)}
            {canWrite ? <Button type="button" variant="outline" size="sm" className="mt-2 w-full" onClick={() => { setFields([...fields, blankField(fields.length + 1)]); setSelected(fields.length); }} data-testid="add-field"><Plus /> Add field</Button> : null}
          </CardContent>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-base">Form details</CardTitle></CardHeader>
            <CardContent className="grid gap-4">
              <Field label="Name" htmlFor="fm_name"><Input id="fm_name" value={meta.name} disabled={!canWrite} onChange={(e) => setMeta({ ...meta, name: e.target.value })} /></Field>
              <Field label="Description (internal)" htmlFor="fm_desc"><Input id="fm_desc" value={meta.description} disabled={!canWrite} onChange={(e) => setMeta({ ...meta, description: e.target.value })} /></Field>
              <Field label="Instructions shown to customers" htmlFor="fm_instr"><Textarea id="fm_instr" value={meta.instructions} disabled={!canWrite} onChange={(e) => setMeta({ ...meta, instructions: e.target.value })} /></Field>
            </CardContent>
          </Card>
          {f ? (
            <Card>
              <CardHeader className="flex flex-row items-start justify-between"><div><CardTitle className="text-base">Edit field</CardTitle><CardDescription>Key <code>{f.key}</code> is how the answer is stored.</CardDescription></div>{canWrite ? <div className="flex gap-1"><Button size="icon" variant="ghost" onClick={() => move(selected, -1)} aria-label="Move up"><ArrowUp /></Button><Button size="icon" variant="ghost" onClick={() => move(selected, 1)} aria-label="Move down"><ArrowDown /></Button><Button size="icon" variant="ghost" className="text-destructive" onClick={() => { setFields(fields.filter((_, j) => j !== selected)); setSelected(Math.max(0, selected - 1)); }} aria-label="Delete field"><Trash2 /></Button></div> : null}</CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <Field label="Label" htmlFor="fd_label"><Input id="fd_label" value={f.label} disabled={!canWrite} onChange={(e) => update(selected, { label: e.target.value, key: f.key.startsWith("field_") ? e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^(\d)/, "f$1") || f.key : f.key })} /></Field>
                <Field label="Key" htmlFor="fd_key" hint="lowercase, letters, digits, underscores"><Input id="fd_key" value={f.key} disabled={!canWrite} onChange={(e) => update(selected, { key: e.target.value })} /></Field>
                <Field label="Type" htmlFor="fd_type"><NativeSelect id="fd_type" value={f.field_type} disabled={!canWrite} onChange={(e) => { const t = e.target.value as FieldType; update(selected, { field_type: t, options: OPTION_TYPES.includes(t) ? (f.options ?? [{ value: "option_1", label: "Option 1" }]) : null }); }}>{(Object.keys(FIELD_TYPE_LABEL) as FieldType[]).map((t) => <option key={t} value={t}>{FIELD_TYPE_LABEL[t]}</option>)}</NativeSelect></Field>
                <Field label="Placeholder" htmlFor="fd_ph"><Input id="fd_ph" value={f.placeholder ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { placeholder: e.target.value || null })} /></Field>
                <Field label="Help text" htmlFor="fd_help" className="sm:col-span-2"><Input id="fd_help" value={f.help_text ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { help_text: e.target.value || null })} /></Field>
                <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Required</span><Switch checked={f.is_required} disabled={!canWrite} onCheckedChange={(v) => update(selected, { is_required: v })} /></label>
                <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Sensitive (clinical)</span><Switch checked={f.is_sensitive} disabled={!canWrite} onCheckedChange={(v) => update(selected, { is_sensitive: v })} /></label>
                {OPTION_TYPES.includes(f.field_type) ? (
                  <div className="space-y-2 sm:col-span-2">
                    <p className="text-sm font-medium">Options</p>
                    {(f.options ?? []).map((o, oi) => <div key={oi} className="flex gap-2"><Input placeholder="Label" value={o.label} disabled={!canWrite} onChange={(e) => update(selected, { options: f.options!.map((x, j) => (j === oi ? { label: e.target.value, value: x.value.startsWith("option_") || x.value === x.label.toLowerCase().replace(/[^a-z0-9]+/g, "_") ? e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_") || x.value : x.value } : x)) })} /><Input className="w-40 font-mono text-xs" placeholder="value" value={o.value} disabled={!canWrite} onChange={(e) => update(selected, { options: f.options!.map((x, j) => (j === oi ? { ...x, value: e.target.value } : x)) })} />{canWrite ? <Button size="icon" variant="ghost" onClick={() => update(selected, { options: f.options!.filter((_, j) => j !== oi) })} aria-label="Remove option"><Trash2 /></Button> : null}</div>)}
                    {canWrite ? <Button type="button" size="sm" variant="ghost" onClick={() => update(selected, { options: [...(f.options ?? []), { value: `option_${(f.options?.length ?? 0) + 1}`, label: `Option ${(f.options?.length ?? 0) + 1}` }] })}><Plus /> Add option</Button> : null}
                  </div>
                ) : null}
                {["text", "textarea"].includes(f.field_type) ? (<><Field label="Min length" htmlFor="fd_minl"><Input id="fd_minl" type="number" min={0} value={f.validation?.min_length ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { validation: { ...f.validation, min_length: e.target.value ? Number(e.target.value) : null } })} /></Field><Field label="Max length" htmlFor="fd_maxl"><Input id="fd_maxl" type="number" min={1} value={f.validation?.max_length ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { validation: { ...f.validation, max_length: e.target.value ? Number(e.target.value) : null } })} /></Field></>) : null}
                {f.field_type === "number" ? (<><Field label="Minimum" htmlFor="fd_min"><Input id="fd_min" type="number" value={f.validation?.min ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { validation: { ...f.validation, min: e.target.value ? Number(e.target.value) : null } })} /></Field><Field label="Maximum" htmlFor="fd_max"><Input id="fd_max" type="number" value={f.validation?.max ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { validation: { ...f.validation, max: e.target.value ? Number(e.target.value) : null } })} /></Field></>) : null}
                {f.field_type === "file" ? <Field label="Max files" htmlFor="fd_files"><Input id="fd_files" type="number" min={1} max={10} value={f.validation?.max_files ?? 1} disabled={!canWrite} onChange={(e) => update(selected, { validation: { ...f.validation, max_files: Number(e.target.value) } })} /></Field> : null}
                {f.field_type === "date" ? <Field label="Latest date" htmlFor="fd_maxd" hint="'today' or YYYY-MM-DD"><Input id="fd_maxd" value={f.validation?.max_date ?? ""} disabled={!canWrite} onChange={(e) => update(selected, { validation: { ...f.validation, max_date: e.target.value || null } })} /></Field> : null}
                <div className="space-y-2 sm:col-span-2">
                  <p className="text-sm font-medium">Show only when</p>
                  {(f.conditions ?? []).map((c, ci) => <div key={ci} className="flex flex-wrap gap-2"><NativeSelect className="w-44" value={c.field} disabled={!canWrite} onChange={(e) => update(selected, { conditions: f.conditions!.map((x, j) => (j === ci ? { ...x, field: e.target.value } : x)) })}>{fields.filter((x) => x.key !== f.key).map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</NativeSelect><NativeSelect className="w-40" value={c.operator} disabled={!canWrite} onChange={(e) => update(selected, { conditions: f.conditions!.map((x, j) => (j === ci ? { ...x, operator: e.target.value } : x)) })}>{OPERATORS.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}</NativeSelect>{!["is_true", "is_false", "is_empty", "is_not_empty"].includes(c.operator) ? <Input className="w-40" placeholder="value" value={String(c.value ?? "")} disabled={!canWrite} onChange={(e) => update(selected, { conditions: f.conditions!.map((x, j) => (j === ci ? { ...x, value: isNaN(Number(e.target.value)) || e.target.value === "" ? e.target.value : Number(e.target.value) } : x)) })} /> : null}{canWrite ? <Button size="icon" variant="ghost" onClick={() => update(selected, { conditions: f.conditions!.filter((_, j) => j !== ci) })} aria-label="Remove condition"><Trash2 /></Button> : null}</div>)}
                  {canWrite && fields.length > 1 ? <Button type="button" size="sm" variant="ghost" onClick={() => update(selected, { conditions: [...(f.conditions ?? []), { field: fields.find((x) => x.key !== f.key)!.key, operator: "equals", value: "" }] })}><Plus /> Add condition</Button> : null}
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
        <Card className="h-fit lg:sticky lg:top-24">
          <CardHeader><CardTitle className="text-base">Preview</CardTitle><CardDescription>Exactly what customers see at booking.</CardDescription></CardHeader>
          <CardContent>{meta.instructions ? <p className="mb-3 text-sm text-muted-foreground">{meta.instructions}</p> : null}<DynamicForm fields={fields} answers={preview} onChange={setPreview} /></CardContent>
        </Card>
      </div>
    </div>
  );
}
