"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { useEditor } from "./editor";
import { ColorInput, Select, TextInput, Toggle, UploadButton } from "./fields";
import { useAdminCatalog } from "./section-editor";
import { BUTTON_POSITIONS, ICONS, type ButtonKind, type ButtonPosition, type SiteButton } from "@/types/website";

export const KIND_LABELS: Record<ButtonKind, string> = {
  book: "Book appointment", call: "Call now", whatsapp: "WhatsApp", contact: "Contact us", services: "View services", external: "External website",
  url: "Custom URL", maps: "Google Maps", pdf: "Download PDF", page: "Custom page",
};
export const POSITION_LABELS: Record<ButtonPosition, string> = {
  header: "Header", hero: "Hero", footer: "Footer", service_cards: "Service cards", floating: "Sticky bar on phones", contact: "Contact section",
};

export function ButtonEditor({ button, onChange, withPositions = true }: { button: SiteButton; onChange: (b: SiteButton) => void; withPositions?: boolean }) {
  const { doc } = useEditor();
  const cat = useAdminCatalog();
  const set = (patch: Partial<SiteButton>) => onChange({ ...button, ...patch });
  return (
    <div className="space-y-3" data-testid="button-editor">
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput label="Button text" value={button.label} maxLength={60} onChange={(label) => set({ label })} testId="button-label" />
        <Select label="Button type" value={button.kind} onChange={(kind) => set({ kind })} options={Object.entries(KIND_LABELS).map(([value, label]) => ({ value: value as ButtonKind, label }))} />
      </div>
      {button.kind === "book" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Preselect service (optional)" value={button.service} onChange={(service) => set({ service })} options={[{ value: "", label: "Visitor chooses" }, ...cat.services.map((s) => ({ value: s.slug, label: s.name }))]} />
          <Select label="Preselect location (optional)" value={button.branch} onChange={(branch) => set({ branch })} options={[{ value: "", label: "Visitor chooses" }, ...cat.branches.map((b) => ({ value: b.slug, label: b.name }))]} />
        </div>
      ) : null}
      {button.kind === "call" || button.kind === "whatsapp" ? (
        <TextInput label={button.kind === "call" ? "Phone number (empty = clinic number)" : "WhatsApp number (empty = clinic WhatsApp)"} value={button.phone} maxLength={24} onChange={(phone) => set({ phone })} placeholder="+91 98250 12345" />
      ) : null}
      {button.kind === "whatsapp" ? <TextInput label="Pre-filled message" value={button.message} maxLength={300} onChange={(message) => set({ message })} placeholder="Hello, I'd like to book an appointment." /> : null}
      {button.kind === "maps" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Location" value={button.branch} onChange={(branch) => set({ branch })} options={[{ value: "", label: "Clinic address" }, ...cat.branches.map((b) => ({ value: b.slug, label: b.name }))]} />
          <TextInput label="Or a Google Maps link (https://…)" value={button.url} maxLength={500} onChange={(url) => set({ url })} />
        </div>
      ) : null}
      {button.kind === "external" || button.kind === "url" ? <TextInput label="Web address" value={button.url} maxLength={500} onChange={(url) => set({ url })} placeholder="https://" hint="Must start with https://" testId="button-url" /> : null}
      {button.kind === "pdf" ? (
        <div className="space-y-2">
          <TextInput label="PDF address" value={button.url} maxLength={500} onChange={(url) => set({ url })} placeholder="https://…/brochure.pdf or upload" />
          <UploadButton kind="pdf" label="Upload PDF" onUploaded={(url) => set({ url })} />
        </div>
      ) : null}
      {button.kind === "page" ? (
        <Select label="Page" value={button.page} onChange={(page) => set({ page })} options={[{ value: "", label: "Choose a page" }, ...doc.pages.map((p) => ({ value: p.slug, label: p.title }))]} hint={doc.pages.length ? undefined : "Create a page under Website → Custom pages first."} />
      ) : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <Select label="Style" value={button.style} onChange={(style) => set({ style })} options={[{ value: "solid", label: "Solid" }, { value: "outline", label: "Outline" }, { value: "soft", label: "Soft" }, { value: "link", label: "Text link" }]} />
        <Select label="Colour" value={button.color} onChange={(color) => set({ color })} options={[{ value: "primary", label: "Brand" }, { value: "secondary", label: "Secondary" }, { value: "dark", label: "Dark" }, { value: "light", label: "Light" }, { value: "custom", label: "Custom" }]} />
        <Select label="Icon" value={button.icon} onChange={(icon) => set({ icon })} options={ICONS.map((i) => ({ value: i, label: i }))} />
      </div>
      {button.color === "custom" ? <ColorInput label="Custom colour" value={button.custom_color || "#0f766e"} onChange={(custom_color) => set({ custom_color })} /> : null}
      <div className="grid gap-2 sm:grid-cols-2">
        <Toggle label="Open in a new tab" checked={button.new_tab} onChange={(new_tab) => set({ new_tab })} />
        <Toggle label="Visible" checked={button.visible} onChange={(visible) => set({ visible })} />
      </div>
      {withPositions ? (
        <fieldset className="rounded-xl border p-3">
          <legend className="px-1 text-sm font-medium">Show in</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {BUTTON_POSITIONS.map((p) => (
              <label key={p} className="flex items-center gap-2 text-sm">
                <Checkbox checked={button.positions.includes(p)} onCheckedChange={(on) => set({ positions: on ? [...button.positions, p] : button.positions.filter((x) => x !== p) })} />{POSITION_LABELS[p]}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
    </div>
  );
}
