"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FONT_STACKS } from "@/components/website/theme";
import { SECTION_LABELS, blankSection, newButton, newId } from "@/lib/website-templates";
import { SectionsBuilder } from "./builder";
import { ButtonEditor, KIND_LABELS, POSITION_LABELS } from "./button-editor";
import { useEditor } from "./editor";
import { ColorInput, ImageInput, MarkdownInput, Select, SortableList, TextInput, Toggle } from "./fields";
import { NavItemsEditor } from "./nav-editor";
import { SectionEditor } from "./section-editor";
import { FONTS, type SectionType, type SitePage, type WebsiteDocument } from "@/types/website";

function Panel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle>{description ? <CardDescription>{description}</CardDescription> : null}</CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------------------------------- settings
export function SettingsPage() {
  const { doc, update } = useEditor();
  const s = doc.settings;
  const set = (patch: Partial<WebsiteDocument["settings"]>) => update((d) => ({ ...d, settings: { ...d.settings, ...patch } }));
  const setSocial = (patch: Partial<WebsiteDocument["settings"]["social"]>) => set({ social: { ...s.social, ...patch } });
  return (
    <div className="space-y-6">
      <Panel title="Identity" description="Shown in the header, footer, browser tab and search results.">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Website name" value={s.site_name} maxLength={120} onChange={(site_name) => set({ site_name })} testId="site-name" />
          <TextInput label="Clinic name" value={s.clinic_name} maxLength={160} onChange={(clinic_name) => set({ clinic_name })} />
        </div>
        <TextInput label="Tagline" value={s.tagline} maxLength={160} onChange={(tagline) => set({ tagline })} />
        <TextInput label="Website description" value={s.description} maxLength={600} multiline onChange={(description) => set({ description })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <ImageInput label="Logo" value={{ url: s.logo_url, alt: "", caption: "" }} onChange={(v) => set({ logo_url: v.url })} hint="Square or wide PNG/WebP with a transparent background works best." />
          <ImageInput label="Favicon (browser tab icon)" value={{ url: s.favicon_url, alt: "", caption: "" }} onChange={(v) => set({ favicon_url: v.url })} hint="A square PNG, at least 64×64 pixels." />
        </div>
      </Panel>
      <Panel title="Colours and font">
        <div className="grid gap-4 sm:grid-cols-3">
          <ColorInput label="Brand colour" value={s.primary_color} against={s.background_color} onChange={(primary_color) => set({ primary_color })} />
          <ColorInput label="Secondary colour" value={s.secondary_color} against={s.background_color} purpose="background" onChange={(secondary_color) => set({ secondary_color })} />
          <ColorInput label="Page background" value={s.background_color} purpose="background" onChange={(background_color) => set({ background_color })} />
        </div>
        <Select label="Font" value={s.font} onChange={(font) => set({ font })} options={FONTS.map((f) => ({ value: f, label: FONT_STACKS[f].label }))} hint="Fonts are served from your site or the visitor's device; nothing is loaded from other websites." />
      </Panel>
      <Panel title="Contact details">
        <div className="grid gap-4 sm:grid-cols-3">
          <TextInput label="Phone" value={s.phone} maxLength={24} onChange={(phone) => set({ phone })} placeholder="+91 98250 12345" />
          <TextInput label="WhatsApp number" value={s.whatsapp} maxLength={24} onChange={(whatsapp) => set({ whatsapp })} placeholder="+91 98250 12345" />
          <TextInput label="Email" value={s.email} maxLength={160} type="email" onChange={(email) => set({ email })} />
        </div>
        <TextInput label="Address" value={s.address} maxLength={300} multiline rows={2} onChange={(address) => set({ address })} />
      </Panel>
      <Panel title="Social media" description="Full https:// addresses of your profiles.">
        <div className="grid gap-4 sm:grid-cols-2">
          {(["facebook", "instagram", "youtube", "x", "linkedin", "google"] as const).map((n) => (
            <TextInput key={n} label={n === "google" ? "Google Business Profile" : n === "x" ? "X (Twitter)" : n[0].toUpperCase() + n.slice(1)} value={s.social[n]} maxLength={500} placeholder="https://" onChange={(v) => setSocial({ [n]: v })} />
          ))}
        </div>
      </Panel>
    </div>
  );
}

// ----------------------------------------------------------------------------------------------------- builder
export function BuilderPage() {
  const { doc, update } = useEditor();
  return (
    <Panel title="Homepage builder" description="The sections of your home page, top to bottom.">
      <SectionsBuilder sections={doc.sections} onChange={(sections) => update((d) => ({ ...d, sections }))} />
    </Panel>
  );
}

// ------------------------------------------------------------------------------------------- single section
const SECTION_HELP: Partial<Record<SectionType, string>> = {
  hero: "The first thing visitors see: headline, photo and your main buttons.",
  about: "Your clinic's story, approach and experience.",
  doctors: "Doctor cards are built from Catalogue → Professionals.",
  services: "Service cards come from Catalogue → Services, with live fees and durations.",
  gallery: "Photos of your clinic and facilities.",
  testimonials: "Genuine patient reviews. Only reviews with consent that you approve are shown.",
  faq: "Answers to common questions.",
  contact: "How patients can reach you.",
};

export function SingleSectionPage({ type }: { type: SectionType }) {
  const { doc, update } = useEditor();
  const index = doc.sections.findIndex((s) => s.type === type);
  const section = index >= 0 ? doc.sections[index] : null;
  const others = doc.sections.filter((s) => s.type === type).length;
  return (
    <Panel title={`${SECTION_LABELS[type]} section`} description={SECTION_HELP[type]}>
      {section ? (
        <>
          <Toggle label="Show this section on the home page" checked={section.enabled} onChange={(enabled) => update((d) => ({ ...d, sections: d.sections.map((s, i) => (i === index ? { ...s, enabled } : s)) }))} />
          <SectionEditor section={section} onChange={(next) => update((d) => ({ ...d, sections: d.sections.map((s, i) => (i === index ? next : s)) }))} />
          {others > 1 ? <p className="text-xs text-muted-foreground">There are {others} {SECTION_LABELS[type].toLowerCase()} sections; this edits the first. Use the homepage builder for the others.</p> : null}
        </>
      ) : (
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>Your home page has no {SECTION_LABELS[type].toLowerCase()} section yet.</p>
          <Button type="button" data-testid="add-single-section" onClick={() => update((d) => {
            const s = blankSection(type, newId(type, d.sections.map((x) => x.id)));
            return { ...d, sections: type === "hero" ? [s, ...d.sections] : [...d.sections, s] };
          })}><Plus /> Add a {SECTION_LABELS[type].toLowerCase()} section</Button>
        </div>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------------------------------------ header/footer
export function HeaderPage() {
  const { doc, update } = useEditor();
  const h = doc.header;
  const set = (patch: Partial<WebsiteDocument["header"]>) => update((d) => ({ ...d, header: { ...d.header, ...patch } }));
  return (
    <div className="space-y-6">
      <Panel title="Header">
        <Toggle label="Keep the header visible while scrolling" checked={h.sticky} onChange={(sticky) => set({ sticky })} />
        <Toggle label="Show the logo" checked={h.show_logo} onChange={(show_logo) => set({ show_logo })} />
        <Toggle label="Show the phone number" checked={h.show_phone} onChange={(show_phone) => set({ show_phone })} />
        <p className="text-xs text-muted-foreground">Header buttons (e.g. Book appointment) are set under Custom links &amp; buttons, position “Header”.</p>
      </Panel>
      <Panel title="Navigation menu" description="Up to 10 links. Custom pages marked “Show in menu” are added after these.">
        <NavItemsEditor items={h.nav} onChange={(nav) => set({ nav })} />
      </Panel>
    </div>
  );
}

export function FooterPage() {
  const { doc, update } = useEditor();
  const f = doc.footer;
  const set = (patch: Partial<WebsiteDocument["footer"]>) => update((d) => ({ ...d, footer: { ...d.footer, ...patch } }));
  return (
    <div className="space-y-6">
      <Panel title="Footer">
        <TextInput label="About text" value={f.about} maxLength={600} multiline onChange={(about) => set({ about })} />
        <TextInput label="Copyright line" value={f.copyright} maxLength={160} onChange={(copyright) => set({ copyright })} placeholder="© 2026 Akshar Ayurveda Clinic" />
        <Toggle label="Social media icons" checked={f.show_social} onChange={(show_social) => set({ show_social })} />
        <Toggle label="Locations" checked={f.show_branches} onChange={(show_branches) => set({ show_branches })} />
        <Toggle label="Policy links" checked={f.show_policies} onChange={(show_policies) => set({ show_policies })} hint="Privacy, terms and refund pages from Organization settings → Legal, or your own custom pages with those addresses." />
      </Panel>
      <Panel title="Link columns" description="Up to 4 columns of links.">
        <Button type="button" variant="outline" size="sm" disabled={f.columns.length >= 4} onClick={() => set({ columns: [...f.columns, { title: "", links: [] }] })}><Plus /> Add column</Button>
        <SortableList items={f.columns} onChange={(columns) => set({ columns })} getKey={(_, i) => String(i)} render={(col, i) => (
          <div className="space-y-3">
            <TextInput label="Column title" value={col.title} maxLength={60} onChange={(title) => set({ columns: f.columns.map((c, j) => (j === i ? { ...c, title } : c)) })} />
            <NavItemsEditor items={col.links} onChange={(links) => set({ columns: f.columns.map((c, j) => (j === i ? { ...c, links } : c)) })} />
          </div>
        )} />
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------- pages
function slugify(v: string) {
  return v.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}

export function CustomPagesPage() {
  const { doc, update, state } = useEditor();
  const [open, setOpen] = useState<string | null>(null);
  const setPages = (pages: SitePage[]) => update((d) => ({ ...d, pages }));
  return (
    <Panel title="Custom pages" description={`Extra pages at ${state.public_url_path}/your-page, e.g. About us, a treatment, or your privacy policy.`}>
      <Button type="button" data-testid="add-page" disabled={doc.pages.length >= 30} onClick={() => {
        const slug = newId("new-page", doc.pages.map((p) => p.slug));
        setPages([...doc.pages, { slug, title: "New page", body: "", sections: [], enabled: true, show_in_nav: false, seo_title: "", seo_description: "" }]);
        setOpen(slug);
      }}><Plus /> New page</Button>
      <SortableList items={doc.pages} onChange={setPages} getKey={(p, i) => `${i}`} emptyText="No custom pages yet." confirmRemove={(p) => `Delete the page “${p.title}”? Links to it will stop working.`}
        render={(p, i) => {
          const upd = (patch: Partial<SitePage>) => setPages(doc.pages.map((x, j) => (j === i ? { ...x, ...patch } : x)));
          const expanded = open === p.slug;
          return (
            <div className="space-y-4" data-testid="page-editor">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium">{p.title}</span><span className="font-mono text-xs text-muted-foreground">{state.public_url_path}/{p.slug}</span>
                {!p.enabled ? <span className="rounded bg-muted px-2 py-0.5 text-xs">Hidden</span> : null}
                <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={() => setOpen(expanded ? null : p.slug)}>{expanded ? "Close" : "Edit"}</Button>
              </div>
              {expanded ? (
                <div className="space-y-4 border-t pt-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <TextInput label="Page title" value={p.title} maxLength={120} onChange={(title) => upd({ title })} testId="page-title" />
                    <TextInput label="Page address" value={p.slug} maxLength={64} onChange={(v) => { const slug = slugify(v); upd({ slug }); setOpen(slug); }} hint="Lower-case letters, numbers and dashes." testId="page-slug" />
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Toggle label="Published" checked={p.enabled} onChange={(enabled) => upd({ enabled })} />
                    <Toggle label="Show in the menu" checked={p.show_in_nav} onChange={(show_in_nav) => upd({ show_in_nav })} />
                  </div>
                  <MarkdownInput label="Content" value={p.body} onChange={(body) => upd({ body })} rows={10} />
                  <details className="rounded-xl border p-4"><summary className="cursor-pointer text-sm font-medium">Sections on this page ({p.sections.length})</summary>
                    <div className="pt-4"><SectionsBuilder sections={p.sections} allowHero={false} onChange={(sections) => upd({ sections })} /></div>
                  </details>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <TextInput label="Search title" value={p.seo_title} maxLength={70} onChange={(seo_title) => upd({ seo_title })} hint="Defaults to the page title." />
                    <TextInput label="Search description" value={p.seo_description} maxLength={170} multiline rows={2} onChange={(seo_description) => upd({ seo_description })} />
                  </div>
                </div>
              ) : null}
            </div>
          );
        }} />
    </Panel>
  );
}

// ----------------------------------------------------------------------------------------------------- buttons
export function ButtonsPage() {
  const { doc, update } = useEditor();
  const [open, setOpen] = useState<string | null>(null);
  const setButtons = (buttons: WebsiteDocument["buttons"]) => update((d) => ({ ...d, buttons }));
  return (
    <Panel title="Custom links & buttons" description="Buttons you can show in the header, hero, service cards, contact section, footer, and the sticky bar on phones.">
      <Button type="button" data-testid="add-button" disabled={doc.buttons.length >= 20} onClick={() => {
        const id = newId("button", doc.buttons.map((b) => b.id));
        setButtons([...doc.buttons, { ...newButton("book", id, "Book appointment"), positions: ["hero"] }]);
        setOpen(id);
      }}><Plus /> New button</Button>
      <SortableList items={doc.buttons} onChange={setButtons} getKey={(b) => b.id} emptyText="No buttons yet." confirmRemove={(b) => `Delete the “${b.label}” button?`} render={(b, i) => (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{b.label}</span>
            <span className="rounded bg-muted px-2 py-0.5 text-xs">{KIND_LABELS[b.kind]}</span>
            <span className="text-xs text-muted-foreground">{b.positions.map((p) => POSITION_LABELS[p]).join(", ") || "Not placed"}</span>
            {!b.visible ? <span className="rounded bg-muted px-2 py-0.5 text-xs">Hidden</span> : null}
            <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={() => setOpen(open === b.id ? null : b.id)}>{open === b.id ? "Close" : "Edit"}</Button>
          </div>
          {open === b.id ? <div className="border-t pt-3"><ButtonEditor button={b} onChange={(nb) => setButtons(doc.buttons.map((x, j) => (j === i ? nb : x)))} /></div> : null}
        </div>
      )} />
    </Panel>
  );
}

// --------------------------------------------------------------------------------------------------------- SEO
export function SeoPage() {
  const { doc, update, state } = useEditor();
  const seo = doc.seo;
  const set = (patch: Partial<WebsiteDocument["seo"]>) => update((d) => ({ ...d, seo: { ...d.seo, ...patch } }));
  return (
    <div className="space-y-6">
      <Panel title="Search engines and social previews">
        <TextInput label="Title" value={seo.title} maxLength={70} onChange={(title) => set({ title })} hint="About 50–60 characters, e.g. “Akshar Ayurveda Clinic, Ahmedabad | Book online”." />
        <TextInput label="Description" value={seo.description} maxLength={170} multiline rows={3} onChange={(description) => set({ description })} hint="About 150 characters describing the clinic and its services." />
        <ImageInput label="Social sharing image" value={{ url: seo.image_url, alt: "", caption: "" }} onChange={(v) => set({ image_url: v.url })} hint="1200×630 pixels works best for WhatsApp, Facebook and LinkedIn previews." />
        <Toggle label="Hide from search engines" checked={seo.noindex} onChange={(noindex) => set({ noindex })} hint="Use while you are still building the site." />
      </Panel>
      <Panel title="How it may look in Google">
        <div className="max-w-xl space-y-1 rounded-xl border p-4">
          <p className="truncate text-xs text-emerald-800">{typeof window !== "undefined" ? window.location.host : ""}{state.public_url_path}</p>
          <p className="truncate text-lg text-blue-800">{seo.title || doc.settings.site_name || doc.settings.clinic_name}</p>
          <p className="line-clamp-2 text-sm text-muted-foreground">{seo.description || doc.settings.description || "Add a description so search results explain what you offer."}</p>
        </div>
        <p className="text-xs text-muted-foreground">Each custom page has its own search title and description under Custom pages.</p>
      </Panel>
    </div>
  );
}
