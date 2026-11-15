"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useEditor } from "./editor";
import { Select, SortableList, TextInput, Toggle } from "./fields";
import type { NavItem } from "@/types/website";

export function NavItemsEditor({ items, onChange, max = 10, addLabel = "Add link" }: { items: NavItem[]; onChange: (v: NavItem[]) => void; max?: number; addLabel?: string }) {
  const { doc } = useEditor();
  const sectionOptions = doc.sections.map((s) => ({ value: s.id, label: `${s.heading || s.type} (#${s.id})` }));
  const pageOptions = doc.pages.map((p) => ({ value: p.slug, label: p.title }));
  return (
    <div className="space-y-3">
      <Button type="button" variant="outline" size="sm" disabled={items.length >= max} onClick={() => onChange([...items, { label: "", kind: "section", target: sectionOptions[0]?.value ?? "", new_tab: false }])}><Plus /> {addLabel}</Button>
      <SortableList items={items} onChange={onChange} getKey={(_, i) => String(i)} emptyText="No links yet." render={(item, i) => {
        const upd = (patch: Partial<NavItem>) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x)));
        return (
          <div className="grid gap-2 sm:grid-cols-3" data-testid="nav-item">
            <TextInput label="Label" value={item.label} maxLength={40} onChange={(label) => upd({ label })} />
            <Select label="Goes to" value={item.kind} onChange={(kind) => upd({ kind, target: kind === "section" ? sectionOptions[0]?.value ?? "" : kind === "page" ? pageOptions[0]?.value ?? "" : "" })}
              options={[{ value: "section", label: "Home page section" }, { value: "page", label: "Custom page" }, { value: "book", label: "Booking page" }, { value: "url", label: "Web address" }]} />
            {item.kind === "section" ? <Select label="Section" value={item.target} onChange={(target) => upd({ target })} options={sectionOptions} /> : null}
            {item.kind === "page" ? <Select label="Page" value={item.target} onChange={(target) => upd({ target })} options={pageOptions.length ? pageOptions : [{ value: "", label: "No pages yet" }]} /> : null}
            {item.kind === "url" ? <TextInput label="Web address" value={item.target} maxLength={500} onChange={(target) => upd({ target })} placeholder="https://" /> : null}
            {item.kind === "url" || item.kind === "page" ? <div className="sm:col-span-3"><Toggle label="Open in a new tab" checked={item.new_tab} onChange={(new_tab) => upd({ new_tab })} /></div> : null}
          </div>
        );
      }} />
    </div>
  );
}
