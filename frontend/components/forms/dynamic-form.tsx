"use client";

import { useRef, useState } from "react";
import { Loader2, Paperclip, X } from "lucide-react";
import { toast } from "sonner";
import { isFieldVisible } from "@/services/customers";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/ui/native-select";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import type { FormField } from "@/types/customer";

export type Answers = Record<string, unknown>;
type UploadedFile = { key: string; name: string; mime_type: string; size_bytes: number };

export function DynamicForm({ fields, answers, onChange, errors, uploadFile, disabled }: {
  fields: FormField[];
  answers: Answers;
  onChange: (next: Answers) => void;
  errors?: Record<string, string>;
  uploadFile?: (file: File) => Promise<UploadedFile>;
  disabled?: boolean;
}) {
  const set = (key: string, value: unknown) => onChange({ ...answers, [key]: value });
  const sorted = [...fields].sort((a, b) => a.sort_order - b.sort_order);
  return (
    <div className="grid gap-4 sm:grid-cols-2" data-testid="dynamic-form">
      {sorted.filter((f) => isFieldVisible(f, answers)).map((f) => {
        const id = `ff_${f.key}`;
        const label = f.is_required ? `${f.label} *` : f.label;
        const error = errors?.[f.key];
        const wide = ["textarea", "file", "multi_select", "checkbox"].includes(f.field_type);
        const value = answers[f.key];
        const common = { id, disabled, placeholder: f.placeholder ?? undefined, "aria-invalid": error ? true : undefined } as const;
        let control: React.ReactNode;
        switch (f.field_type) {
          case "text": case "email": case "mobile":
            control = <Input {...common} type={f.field_type === "email" ? "email" : "text"} inputMode={f.field_type === "mobile" ? "tel" : undefined} value={(value as string) ?? ""} onChange={(e) => set(f.key, e.target.value)} />; break;
          case "textarea":
            control = <Textarea {...common} value={(value as string) ?? ""} onChange={(e) => set(f.key, e.target.value)} />; break;
          case "number":
            control = <Input {...common} type="number" min={f.validation?.min ?? undefined} max={f.validation?.max ?? undefined} value={value === undefined || value === null ? "" : String(value)} onChange={(e) => set(f.key, e.target.value === "" ? undefined : Number(e.target.value))} />; break;
          case "date":
            control = <Input {...common} type="date" value={(value as string) ?? ""} onChange={(e) => set(f.key, e.target.value || undefined)} />; break;
          case "dropdown":
            control = <NativeSelect {...common} value={(value as string) ?? ""} onChange={(e) => set(f.key, e.target.value || undefined)}><option value="">Select…</option>{f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</NativeSelect>; break;
          case "radio":
            control = <div className="flex flex-wrap gap-2">{f.options?.map((o) => <label key={o.value} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${value === o.value ? "border-primary bg-accent" : ""}`}><input type="radio" className="sr-only" name={id} disabled={disabled} checked={value === o.value} onChange={() => set(f.key, o.value)} />{o.label}</label>)}</div>; break;
          case "multi_select": {
            const arr = Array.isArray(value) ? (value as string[]) : [];
            control = <div className="flex flex-wrap gap-2">{f.options?.map((o) => <label key={o.value} className="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm"><Checkbox disabled={disabled} checked={arr.includes(o.value)} onCheckedChange={(v) => set(f.key, v ? [...arr, o.value] : arr.filter((x) => x !== o.value))} />{o.label}</label>)}</div>; break;
          }
          case "checkbox":
            control = <label className="flex items-start gap-2 text-sm"><Checkbox id={id} disabled={disabled} checked={value === true} onCheckedChange={(v) => set(f.key, v === true)} /><span>{f.help_text ?? f.label}</span></label>; break;
          case "file":
            control = <FileField files={(value as UploadedFile[]) ?? []} maxFiles={f.validation?.max_files ?? 1} accept={f.validation?.accept ?? undefined} disabled={disabled} upload={uploadFile} onChange={(files) => set(f.key, files.length ? files : undefined)} />; break;
          default:
            control = null;
        }
        if (f.field_type === "checkbox") {
          return <div key={f.key} className={wide ? "sm:col-span-2" : ""}><p className="mb-1 text-sm font-medium">{label}</p>{control}{error ? <p className="mt-1 text-xs text-destructive">{error}</p> : null}</div>;
        }
        return <Field key={f.key} label={label} htmlFor={id} error={error} hint={f.help_text ?? undefined} className={wide ? "sm:col-span-2" : ""}>{control}</Field>;
      })}
    </div>
  );
}

function FileField({ files, maxFiles, accept, disabled, upload, onChange }: { files: UploadedFile[]; maxFiles: number; accept?: string[]; disabled?: boolean; upload?: (file: File) => Promise<UploadedFile>; onChange: (files: UploadedFile[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <ul className="space-y-1">{files.map((f) => <li key={f.key} className="flex items-center justify-between rounded-lg border px-3 py-1.5 text-sm"><span className="flex items-center gap-2 truncate"><Paperclip className="size-3.5" />{f.name}</span><Button type="button" size="icon" variant="ghost" disabled={disabled} onClick={() => onChange(files.filter((x) => x.key !== f.key))} aria-label="Remove file"><X /></Button></li>)}</ul>
      {files.length < maxFiles && upload ? <Button type="button" size="sm" variant="outline" disabled={disabled || busy} onClick={() => input.current?.click()}>{busy ? <Loader2 className="animate-spin" /> : <Paperclip />} Attach file</Button> : null}
      <input ref={input} type="file" className="hidden" accept={(accept ?? ["image/png", "image/jpeg", "image/webp", "application/pdf"]).join(",")} onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f || !upload) return; setBusy(true); try { onChange([...files, await upload(f)]); } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(false); } }} />
    </div>
  );
}

/** Map backend form_invalid errors to {field: message}. */
export function formErrorsFromApi(error: unknown): Record<string, string> | null {
  const e = error as { code?: string; errors?: { field: string; message: string }[] };
  if (e?.code !== "form_invalid" || !Array.isArray(e.errors)) return null;
  return Object.fromEntries(e.errors.map((x) => [x.field, x.message]));
}
