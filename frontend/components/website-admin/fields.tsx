"use client";

import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Copy, GripVertical, ImagePlus, Loader2, Trash2 } from "lucide-react";
import { catalogService, mediaUrl } from "@/services/catalog";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { NativeSelect } from "@/components/ui/native-select";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/website/markdown";
import { contrast, safeHex } from "@/components/public-booking/brand";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { SiteImage } from "@/types/website";

export function TextInput({ label, value, onChange, hint, maxLength, placeholder, multiline, rows = 3, disabled, type = "text", testId }: {
  label: string; value: string; onChange: (v: string) => void; hint?: string; maxLength?: number; placeholder?: string; multiline?: boolean; rows?: number; disabled?: boolean; type?: string; testId?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {maxLength && value.length > maxLength * 0.8 ? <span className={cn("text-xs", value.length > maxLength ? "text-destructive" : "text-muted-foreground")}>{value.length}/{maxLength}</span> : null}
      </div>
      {multiline
        ? <Textarea id={id} value={value} rows={rows} maxLength={maxLength} placeholder={placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)} data-testid={testId} />
        : <Input id={id} type={type} value={value} maxLength={maxLength} placeholder={placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)} data-testid={testId} />}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function Toggle({ label, checked, onChange, hint, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string; disabled?: boolean }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border px-4 py-3">
      <div><Label htmlFor={id}>{label}</Label>{hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}</div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </div>
  );
}

export function Select<T extends string | number>({ label, value, onChange, options, hint }: { label: string; value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; hint?: string }) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <NativeSelect id={id} value={String(value)} onChange={(e) => onChange((typeof value === "number" ? Number(e.target.value) : e.target.value) as T)}>
        {options.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
      </NativeSelect>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/** Colour picker with a hex box and a readability check against white and the page background. */
export function ColorInput({ label, value, onChange, against = "#ffffff", purpose = "text" }: { label: string; value: string; onChange: (v: string) => void; against?: string; purpose?: "text" | "background" }) {
  const id = useId();
  const valid = /^#[0-9a-fA-F]{6}$/.test(value);
  const ratio = valid ? contrast(safeHex(value), safeHex(against, "#ffffff")) : 0;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <input type="color" aria-label={`${label} picker`} value={valid ? value : "#000000"} onChange={(e) => onChange(e.target.value)} className="h-10 w-12 cursor-pointer rounded-lg border bg-transparent p-1" />
        <Input id={id} value={value} onChange={(e) => onChange(e.target.value.trim())} maxLength={7} className="font-mono uppercase" aria-invalid={!valid} />
      </div>
      {!valid ? <p className="text-xs text-destructive">Use a colour like #0F766E.</p>
        : purpose === "text" && ratio < 3 ? <p className="text-xs text-amber-700">Low contrast ({ratio.toFixed(1)}:1) against the page. Buttons and links in this colour may be hard to read.</p> : null}
    </div>
  );
}

async function uploadPdf(file: File) {
  const form = new FormData();
  form.append("file", file);
  return api.post<{ url: string }>("/uploads/documents", form);
}

export function UploadButton({ accept = "image/png,image/jpeg,image/webp", onUploaded, label = "Upload", kind = "image" }: { accept?: string; onUploaded: (url: string) => void; label?: string; kind?: "image" | "pdf" }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <input ref={ref} type="file" accept={kind === "pdf" ? "application/pdf" : accept} className="sr-only" tabIndex={-1} aria-hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setBusy(true);
          try { onUploaded((kind === "pdf" ? await uploadPdf(file) : await catalogService.uploadImage(file)).url); }
          catch (err) { toast.error(errorMessage(err)); }
          finally { setBusy(false); }
        }} />
      <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => ref.current?.click()}>{busy ? <Loader2 className="animate-spin" /> : <ImagePlus />} {label}</Button>
    </>
  );
}

export function ImageInput({ label, value, onChange, hint, withCaption = false }: { label: string; value: SiteImage; onChange: (v: SiteImage) => void; hint?: string; withCaption?: boolean }) {
  return (
    <div className="space-y-2 rounded-xl border p-4">
      <p className="text-sm font-medium">{label}</p>
      <div className="flex flex-wrap items-center gap-4">
        <div className="grid size-24 shrink-0 place-items-center overflow-hidden rounded-xl bg-muted text-xs text-muted-foreground">
          {value.url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mediaUrl(value.url)} alt="" className="h-full w-full object-cover" />
          ) : "No image"}
        </div>
        <div className="flex flex-wrap gap-2">
          <UploadButton onUploaded={(url) => onChange({ ...value, url })} label={value.url ? "Replace" : "Upload image"} />
          {value.url ? <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...value, url: "" })}><Trash2 /> Remove</Button> : null}
        </div>
      </div>
      <TextInput label="Description for screen readers (alt text)" value={value.alt} onChange={(alt) => onChange({ ...value, alt })} maxLength={160} hint={hint ?? "Describe the photo, e.g. “Reception area with seating”."} />
      {withCaption ? <TextInput label="Caption (optional)" value={value.caption} onChange={(caption) => onChange({ ...value, caption })} maxLength={160} /> : null}
    </div>
  );
}

export function MarkdownInput({ label, value, onChange, maxLength = 20000, rows = 8 }: { label: string; value: string; onChange: (v: string) => void; maxLength?: number; rows?: number }) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <div className="flex rounded-lg border p-0.5 text-xs" role="tablist">
          <button type="button" role="tab" aria-selected={!preview} className={cn("rounded-md px-2 py-1", !preview && "bg-muted font-medium")} onClick={() => setPreview(false)}>Write</button>
          <button type="button" role="tab" aria-selected={preview} className={cn("rounded-md px-2 py-1", preview && "bg-muted font-medium")} onClick={() => setPreview(true)}>Preview</button>
        </div>
      </div>
      {preview
        ? <div className="min-h-32 rounded-lg border p-4 text-sm"><Markdown source={value || "_Nothing written yet._"} /></div>
        : <Textarea aria-label={label} value={value} rows={rows} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} className="font-mono text-sm" />}
      <p className="text-xs text-muted-foreground">## Heading · **bold** · *italic* · - list item · [link text](https://…)</p>
    </div>
  );
}

/** Reorderable list with drag handles (mouse) and up/down buttons (keyboard and touch). */
export function SortableList<T>({ items, onChange, render, getKey, onDuplicate, onRemove, confirmRemove, emptyText }: {
  items: T[]; onChange: (items: T[]) => void; render: (item: T, index: number) => React.ReactNode; getKey: (item: T, index: number) => string;
  onDuplicate?: (item: T) => T; onRemove?: (index: number) => void; confirmRemove?: (item: T) => string | null; emptyText?: string;
}) {
  const [drag, setDrag] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    const [x] = next.splice(from, 1);
    next.splice(to, 0, x);
    onChange(next);
  };
  if (!items.length) return emptyText ? <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">{emptyText}</p> : null;
  return (
    <ol className="space-y-2">
      {items.map((item, i) => (
        <li key={getKey(item, i)} draggable onDragStart={(e) => { setDrag(i); e.dataTransfer.effectAllowed = "move"; }} onDragEnd={() => { setDrag(null); setOver(null); }}
          onDragOver={(e) => { e.preventDefault(); setOver(i); }} onDrop={(e) => { e.preventDefault(); if (drag !== null) move(drag, i); setDrag(null); setOver(null); }}
          className={cn("flex items-start gap-2 rounded-xl border bg-card p-3 transition-colors", drag === i && "opacity-50", over === i && drag !== null && drag !== i && "border-primary ring-2 ring-primary/20")}
          data-testid="sortable-item">
          <GripVertical className="mt-2 size-4 shrink-0 cursor-grab text-muted-foreground" aria-hidden />
          <div className="min-w-0 flex-1">{render(item, i)}</div>
          <div className="flex shrink-0 flex-col gap-1 sm:flex-row">
            <Button type="button" size="icon" variant="ghost" className="size-8" aria-label="Move up" disabled={i === 0} onClick={() => move(i, i - 1)}><ArrowUp /></Button>
            <Button type="button" size="icon" variant="ghost" className="size-8" aria-label="Move down" disabled={i === items.length - 1} onClick={() => move(i, i + 1)}><ArrowDown /></Button>
            {onDuplicate ? <Button type="button" size="icon" variant="ghost" className="size-8" aria-label="Duplicate" onClick={() => onChange([...items.slice(0, i + 1), onDuplicate(item), ...items.slice(i + 1)])}><Copy /></Button> : null}
            <Button type="button" size="icon" variant="ghost" className="size-8 text-destructive" aria-label="Delete"
              onClick={() => {
                const question = confirmRemove?.(item);
                if (question && !window.confirm(question)) return;
                if (onRemove) onRemove(i); else onChange(items.filter((_, j) => j !== i));
              }}><Trash2 /></Button>
          </div>
        </li>
      ))}
    </ol>
  );
}
