"use client";

import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { SECTION_LABELS, TEMPLATES, blankSection, newId } from "@/lib/website-templates";
import { SortableList } from "./fields";
import { SectionEditor } from "./section-editor";
import type { Section } from "@/types/website";

export function SectionsBuilder({ sections, onChange, allowHero = true }: { sections: Section[]; onChange: (s: Section[]) => void; allowHero?: boolean }) {
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const current = sections.find((s) => s.id === editing) ?? null;
  const ids = sections.map((s) => s.id);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Drag to reorder, or use the arrows. Switch a section off to hide it without losing its content.</p>
        <Button type="button" onClick={() => setAdding(true)} disabled={sections.length >= 40} data-testid="add-section"><Plus /> Add section</Button>
      </div>
      <SortableList items={sections} onChange={onChange} getKey={(s) => s.id} onRemove={(i) => setDeleting(i)} emptyText="No sections yet. Add one to start."
        onDuplicate={(s) => ({ ...JSON.parse(JSON.stringify(s)), id: newId(`${s.id}-copy`, ids) })}
        render={(s, i) => (
          <div className="flex flex-wrap items-center gap-3" data-testid={`section-row-${s.id}`}>
            <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium">{SECTION_LABELS[s.type]}</span>
            <span className="min-w-0 flex-1 truncate font-medium">{s.heading || <span className="text-muted-foreground">Untitled</span>}<span className="ml-2 font-mono text-xs text-muted-foreground">#{s.id}</span></span>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch checked={s.enabled} aria-label={`Show ${s.heading || SECTION_LABELS[s.type]}`} onCheckedChange={(enabled) => onChange(sections.map((x, j) => (j === i ? ({ ...x, enabled } as Section) : x)))} />{s.enabled ? "Shown" : "Hidden"}
            </label>
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(s.id)} data-testid="edit-section"><Pencil /> Edit</Button>
          </div>
        )} />

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>Add a section</DialogTitle><DialogDescription>Pick a layout. You can change everything afterwards.</DialogDescription></DialogHeader>
          <div className="grid max-h-[60dvh] gap-3 overflow-y-auto sm:grid-cols-2">
            {TEMPLATES.filter((t) => allowHero || t.type !== "hero").map((t) => (
              <button key={t.key} type="button" data-testid={`template-${t.key}`} className="rounded-xl border p-4 text-left transition-colors hover:border-primary hover:bg-primary/5 focus-visible:outline-2 focus-visible:outline-primary"
                onClick={() => {
                  const s = blankSection(t.type, newId(t.type, ids));
                  const section = t.apply ? t.apply(s) : s;
                  onChange([...sections, section]);
                  setAdding(false);
                  setEditing(section.id);
                }}>
                <span className="block font-medium">{t.label}</span><span className="mt-1 block text-sm text-muted-foreground">{t.description}</span>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Sheet open={!!current} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <SheetContent className="max-w-2xl">
          {current ? (
            <>
              <SheetHeader><SheetTitle>Edit {SECTION_LABELS[current.type].toLowerCase()} section</SheetTitle><SheetDescription>Changes appear in the preview straight away and go live when you publish.</SheetDescription></SheetHeader>
              <SectionEditor section={current} onChange={(next) => { onChange(sections.map((x) => (x.id === current.id ? next : x))); if (next.id !== current.id) setEditing(next.id); }} />
              <Button type="button" onClick={() => setEditing(null)}>Done</Button>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <Dialog open={deleting !== null} onOpenChange={(o) => { if (!o) setDeleting(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this section?</DialogTitle>
            <DialogDescription>“{deleting !== null ? sections[deleting]?.heading || SECTION_LABELS[sections[deleting]?.type] : ""}” and its content will be removed from the draft. Switching it off hides it instead and keeps the content.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>Keep it</Button>
            <Button variant="destructive" data-testid="confirm-delete-section" onClick={() => { onChange(sections.filter((_, j) => j !== deleting)); setDeleting(null); }}>Delete section</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
