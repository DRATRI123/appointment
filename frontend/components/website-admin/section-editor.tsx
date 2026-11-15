"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { newButton, newId } from "@/lib/website-templates";
import { ButtonEditor } from "./button-editor";
import { ColorInput, ImageInput, MarkdownInput, Select, SortableList, TextInput, Toggle, UploadButton } from "./fields";
import { ICONS, type Section, type SiteImage, type Stat } from "@/types/website";

export function useAdminCatalog() {
  const { currentOrganizationId: orgId } = useAuth();
  const services = useQuery({ queryKey: ["services", orgId, "website"], queryFn: () => catalogService.services(), enabled: !!orgId });
  const pros = useQuery({ queryKey: ["professionals", orgId, "website"], queryFn: () => catalogService.professionals(), enabled: !!orgId });
  const branches = useQuery({ queryKey: ["branches", orgId, "website"], queryFn: () => catalogService.branches(false), enabled: !!orgId });
  const categories = useQuery({ queryKey: ["categories", orgId, "website"], queryFn: () => catalogService.categories(), enabled: !!orgId });
  return {
    services: (services.data ?? []).filter((s) => s.is_active && s.is_bookable_online !== false),
    pros: (pros.data ?? []).filter((p) => p.is_active && p.is_bookable_online !== false),
    branches: branches.data ?? [],
    categories: (categories.data ?? []).filter((c) => c.is_active),
  };
}

/** Pick which catalogue items a section shows; nothing ticked means "all". Order follows the ticks. */
function Picker({ label, items, value, onChange }: { label: string; items: { id: string; name: string }[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="space-y-2 rounded-xl border p-4">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      <p className="text-xs text-muted-foreground">{value.length ? `${value.length} selected, shown in the order ticked.` : "Nothing ticked: everything bookable online is shown."}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((i) => (
          <label key={i.id} className="flex items-center gap-2 text-sm">
            <Checkbox checked={value.includes(i.id)} onCheckedChange={(on) => onChange(on ? [...value, i.id] : value.filter((x) => x !== i.id))} />{i.name}
          </label>
        ))}
      </div>
      {!items.length ? <p className="text-sm text-muted-foreground">Nothing to choose yet.</p> : null}
    </fieldset>
  );
}

function StatsEditor({ label, value, onChange, max }: { label: string; value: Stat[]; onChange: (v: Stat[]) => void; max: number }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between"><span className="text-sm font-medium">{label}</span>
        <Button type="button" variant="outline" size="sm" disabled={value.length >= max} onClick={() => onChange([...value, { value: "", label: "" }])}><Plus /> Add</Button></div>
      <SortableList items={value} onChange={onChange} getKey={(_, i) => String(i)} render={(st, i) => (
        <div className="grid gap-2 sm:grid-cols-[120px_1fr]">
          <TextInput label="Number" value={st.value} maxLength={16} placeholder="15+" onChange={(v) => onChange(value.map((x, j) => (j === i ? { ...x, value: v } : x)))} />
          <TextInput label="Label" value={st.label} maxLength={48} placeholder="Years of care" onChange={(v) => onChange(value.map((x, j) => (j === i ? { ...x, label: v } : x)))} />
        </div>
      )} />
      <p className="text-xs text-muted-foreground">Use only facts you can stand behind (e.g. years since founding, number of doctors).</p>
    </div>
  );
}

export function SectionEditor({ section, onChange }: { section: Section; onChange: (s: Section) => void }) {
  const cat = useAdminCatalog();
  const set = <K extends keyof Section>(key: K, v: Section[K]) => onChange({ ...section, [key]: v } as Section);
  const common = (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextInput label="Heading" value={section.heading} maxLength={120} onChange={(v) => set("heading", v)} testId="section-heading" />
        <TextInput label="Section id (for menu links)" value={section.id} maxLength={40} onChange={(v) => set("id", v.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} hint="Letters, numbers and dashes." />
      </div>
      <TextInput label="Introduction" value={section.intro} maxLength={600} multiline rows={2} onChange={(v) => set("intro", v)} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Select label="Background" value={section.background} onChange={(v) => set("background", v)} options={[
          { value: "default", label: "Page background" }, { value: "muted", label: "Soft grey" }, { value: "brand", label: "Brand colour" }, { value: "dark", label: "Dark" }, { value: "custom", label: "Custom colour" },
        ]} />
        {section.background === "custom" ? <ColorInput label="Custom background" value={section.custom_background || "#f5f5f4"} onChange={(v) => set("custom_background", v)} purpose="background" /> : null}
      </div>
    </div>
  );

  const specific = (() => {
    switch (section.type) {
      case "hero":
        return (<>
          <TextInput label="Small label above the headline" value={section.eyebrow} maxLength={60} placeholder="Book online in a few steps" onChange={(v) => onChange({ ...section, eyebrow: v })} />
          <Select label="Layout" value={section.layout} onChange={(v) => onChange({ ...section, layout: v })} options={[{ value: "split", label: "Text beside photo" }, { value: "full", label: "Text over a full-width photo" }, { value: "centered", label: "Centered, no photo" }]} />
          {section.layout !== "centered" ? <ImageInput label="Banner image" value={section.image} onChange={(image) => onChange({ ...section, image })} withCaption /> : null}
          <StatsEditor label="Key numbers (optional)" value={section.stats} max={4} onChange={(stats) => onChange({ ...section, stats })} />
          <p className="text-xs text-muted-foreground">Hero buttons are managed under Website → Custom links &amp; buttons (position “Hero”).</p>
        </>);
      case "about":
        return (<>
          <MarkdownInput label="Text" value={section.body} onChange={(body) => onChange({ ...section, body })} />
          <Select label="Layout" value={section.layout} onChange={(v) => onChange({ ...section, layout: v })} options={[{ value: "image_right", label: "Photo on the right" }, { value: "image_left", label: "Photo on the left" }, { value: "text_only", label: "Text only" }]} />
          {section.layout !== "text_only" ? <ImageInput label="Photo" value={section.image} onChange={(image) => onChange({ ...section, image })} /> : null}
          <StatsEditor label="Highlights" value={section.highlights} max={6} onChange={(highlights) => onChange({ ...section, highlights })} />
        </>);
      case "doctors":
        return (<>
          <Picker label="Doctors to show" items={cat.pros.map((p) => ({ id: p.id, name: p.display_name }))} value={section.professional_ids} onChange={(v) => onChange({ ...section, professional_ids: v })} />
          <Select label="Layout" value={section.layout} onChange={(v) => onChange({ ...section, layout: v })} options={[{ value: "grid", label: "Grid of profile cards" }, { value: "list", label: "Two columns, compact" }]} />
          <Toggle label="Show consultation fee" checked={section.show_fees} onChange={(v) => onChange({ ...section, show_fees: v })} />
          <p className="text-xs text-muted-foreground">Photos, qualifications and experience come from Catalogue → Professionals.</p>
        </>);
      case "services":
        return (<>
          <Picker label="Services to show" items={cat.services.map((s) => ({ id: s.id, name: s.name }))} value={section.service_ids} onChange={(v) => onChange({ ...section, service_ids: v })} />
          <Picker label="Only these categories" items={cat.categories.map((c) => ({ id: c.id, name: c.name }))} value={section.category_ids} onChange={(v) => onChange({ ...section, category_ids: v })} />
          <Select label="Layout" value={section.layout} onChange={(v) => onChange({ ...section, layout: v })} options={[{ value: "cards", label: "Cards" }, { value: "list", label: "Price list" }]} />
          <Toggle label="Show prices" checked={section.show_prices} onChange={(v) => onChange({ ...section, show_prices: v })} />
          <Toggle label="Group by category" checked={section.group_by_category} onChange={(v) => onChange({ ...section, group_by_category: v })} />
        </>);
      case "categories":
        return <Picker label="Categories to show" items={cat.categories.map((c) => ({ id: c.id, name: c.name }))} value={section.category_ids} onChange={(v) => onChange({ ...section, category_ids: v })} />;
      case "features":
        return (<>
          <Select label="Columns on desktop" value={section.columns} onChange={(v) => onChange({ ...section, columns: v })} options={[{ value: 2, label: "2" }, { value: 3, label: "3" }, { value: 4, label: "4" }]} />
          <div className="flex items-center justify-between"><span className="text-sm font-medium">Items</span>
            <Button type="button" variant="outline" size="sm" disabled={section.items.length >= 12} onClick={() => onChange({ ...section, items: [...section.items, { icon: "sparkles", title: "", text: "" }] })}><Plus /> Add item</Button></div>
          <SortableList items={section.items} onChange={(items) => onChange({ ...section, items })} getKey={(_, i) => String(i)} emptyText="No items yet. Add your facilities, e.g. “In-house pharmacy”." render={(f, i) => (
            <div className="grid gap-2 sm:grid-cols-[140px_1fr]">
              <Select label="Icon" value={f.icon} onChange={(icon) => onChange({ ...section, items: section.items.map((x, j) => (j === i ? { ...x, icon } : x)) })} options={ICONS.map((n) => ({ value: n, label: n }))} />
              <TextInput label="Title" value={f.title} maxLength={80} onChange={(title) => onChange({ ...section, items: section.items.map((x, j) => (j === i ? { ...x, title } : x)) })} />
              <div className="sm:col-span-2"><TextInput label="Text" value={f.text} maxLength={400} multiline rows={2} onChange={(text) => onChange({ ...section, items: section.items.map((x, j) => (j === i ? { ...x, text } : x)) })} /></div>
            </div>
          )} />
        </>);
      case "gallery":
        return <GalleryEditor images={section.images} layout={section.layout} onChange={(images, layout) => onChange({ ...section, images, layout })} />;
      case "testimonials":
        return (<>
          <div className="flex items-center justify-between"><span className="text-sm font-medium">Reviews</span>
            <Button type="button" variant="outline" size="sm" disabled={section.items.length >= 40} onClick={() => onChange({ ...section, items: [...section.items, { id: newId("review", section.items.map((t) => t.id)), name: "", text: "", rating: 5, context: "", received_on: null, source: "in_clinic", consent: false, approved: false }] })}><Plus /> Add review</Button></div>
          <p className="text-xs text-muted-foreground">Enter only genuine feedback. A review is shown when the patient agreed to publication <b>and</b> you approved it.</p>
          <SortableList items={section.items} onChange={(items) => onChange({ ...section, items })} getKey={(t) => t.id} emptyText="No reviews yet." confirmRemove={(t) => `Delete the review from ${t.name || "this patient"}?`} render={(t, i) => {
            const upd = (patch: Partial<typeof t>) => onChange({ ...section, items: section.items.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
            return (
              <div className="grid gap-2 sm:grid-cols-2" data-testid="testimonial-editor">
                <TextInput label="Patient name (as they agreed)" value={t.name} maxLength={80} onChange={(name) => upd({ name })} placeholder="Ravi P." />
                <TextInput label="Context (optional)" value={t.context} maxLength={80} onChange={(context) => upd({ context })} placeholder="Panchakarma patient" />
                <div className="sm:col-span-2"><TextInput label="Review" value={t.text} maxLength={600} multiline rows={3} onChange={(text) => upd({ text })} /></div>
                <Select label="Rating" value={t.rating ?? 0} onChange={(r) => upd({ rating: r || null })} options={[{ value: 0, label: "No rating" }, ...[5, 4, 3, 2, 1].map((n) => ({ value: n, label: `${n} star${n > 1 ? "s" : ""}` }))]} />
                <Select label="Where it came from" value={t.source} onChange={(source) => upd({ source })} options={[{ value: "in_clinic", label: "In the clinic" }, { value: "google", label: "Google review" }, { value: "email", label: "Email" }, { value: "whatsapp", label: "WhatsApp" }, { value: "other", label: "Other" }]} />
                <TextInput label="Received on" type="date" value={t.received_on ?? ""} onChange={(v) => upd({ received_on: v || null })} />
                <div className="space-y-2 sm:col-span-2">
                  <Toggle label="Patient agreed to publication" checked={t.consent} onChange={(consent) => upd({ consent, approved: consent ? t.approved : false })} />
                  <Toggle label="Approved for the website" checked={t.approved} disabled={!t.consent} onChange={(approved) => upd({ approved })} hint={!t.consent ? "Record consent first." : undefined} />
                </div>
              </div>
            );
          }} />
        </>);
      case "faq":
        return (<>
          <div className="flex items-center justify-between"><span className="text-sm font-medium">Questions</span>
            <Button type="button" variant="outline" size="sm" disabled={section.items.length >= 40} onClick={() => onChange({ ...section, items: [...section.items, { question: "", answer: "" }] })}><Plus /> Add question</Button></div>
          <SortableList items={section.items} onChange={(items) => onChange({ ...section, items })} getKey={(_, i) => String(i)} emptyText="No questions yet." render={(f, i) => (
            <div className="space-y-2" data-testid="faq-editor">
              <TextInput label="Question" value={f.question} maxLength={200} onChange={(question) => onChange({ ...section, items: section.items.map((x, j) => (j === i ? { ...x, question } : x)) })} />
              <TextInput label="Answer" value={f.answer} maxLength={2000} multiline rows={3} onChange={(answer) => onChange({ ...section, items: section.items.map((x, j) => (j === i ? { ...x, answer } : x)) })} hint="Supports **bold**, lists and links." />
            </div>
          )} />
        </>);
      case "branches":
        return (<>
          <Picker label="Locations to show" items={cat.branches.map((b) => ({ id: b.id, name: b.name }))} value={section.branch_ids} onChange={(v) => onChange({ ...section, branch_ids: v })} />
          <Toggle label="Show opening hours" checked={section.show_hours} onChange={(v) => onChange({ ...section, show_hours: v })} hint="Hours come from Catalogue → Branches." />
          <Toggle label="Show directions link" checked={section.show_map} onChange={(v) => onChange({ ...section, show_map: v })} />
        </>);
      case "contact":
        return (<>
          <Toggle label="Phone" checked={section.show_phone} onChange={(v) => onChange({ ...section, show_phone: v })} />
          <Toggle label="WhatsApp" checked={section.show_whatsapp} onChange={(v) => onChange({ ...section, show_whatsapp: v })} />
          <Toggle label="Email" checked={section.show_email} onChange={(v) => onChange({ ...section, show_email: v })} />
          <Toggle label="Address with Google Maps link" checked={section.show_map} onChange={(v) => onChange({ ...section, show_map: v })} />
          <p className="text-xs text-muted-foreground">Contact details come from Website → Website settings. Extra buttons: position “Contact section”.</p>
        </>);
      case "cta":
        return (<>
          <div className="flex items-center justify-between"><span className="text-sm font-medium">Buttons</span>
            <Button type="button" variant="outline" size="sm" disabled={section.buttons.length >= 3} onClick={() => onChange({ ...section, buttons: [...section.buttons, newButton("book", newId("button", section.buttons.map((b) => b.id)), "Book appointment")] })}><Plus /> Add button</Button></div>
          <SortableList items={section.buttons} onChange={(buttons) => onChange({ ...section, buttons })} getKey={(b) => b.id} render={(b, i) => (
            <ButtonEditor button={b} withPositions={false} onChange={(nb) => onChange({ ...section, buttons: section.buttons.map((x, j) => (j === i ? nb : x)) })} />
          )} />
        </>);
      case "text":
        return (<>
          <MarkdownInput label="Text" value={section.body} onChange={(body) => onChange({ ...section, body })} />
          <Select label="Width" value={section.width} onChange={(v) => onChange({ ...section, width: v })} options={[{ value: "narrow", label: "Narrow (easier to read)" }, { value: "wide", label: "Wide" }]} />
        </>);
    }
  })();

  return <div className="space-y-6">{common}<div className="space-y-4 border-t pt-6">{specific}</div></div>;
}

function GalleryEditor({ images, layout, onChange }: { images: SiteImage[]; layout: "grid" | "mosaic"; onChange: (images: SiteImage[], layout: "grid" | "mosaic") => void }) {
  return (
    <div className="space-y-4">
      <Select label="Layout" value={layout} onChange={(v) => onChange(images, v)} options={[{ value: "grid", label: "Even grid" }, { value: "mosaic", label: "Mosaic (some photos larger)" }]} />
      <div className="flex items-center justify-between">
        <Label>Photos ({images.length}/40)</Label>
        <UploadButton label="Add photo" onUploaded={(url) => onChange([...images, { url, alt: "", caption: "" }], layout)} />
      </div>
      <SortableList items={images} onChange={(v) => onChange(v, layout)} getKey={(img, i) => `${img.url}-${i}`} emptyText="No photos yet. Upload clinic, room and facility photos (PNG, JPEG or WebP, up to 5 MB)." render={(img, i) => (
        <ImageInput label={`Photo ${i + 1}`} value={img} withCaption onChange={(v) => onChange(images.map((x, j) => (j === i ? v : x)), layout)} />
      )} />
    </div>
  );
}
