/**
 * Section templates for the homepage builder. Templates set the layout and a heading; they never invent clinic
 * content (no sample doctors, reviews or facilities): those come from the catalogue or are typed in by the clinic.
 */
import type { Section, SectionType, SiteButton } from "@/types/website";

const base = { enabled: true, heading: "", intro: "", background: "default" as const, custom_background: "" };
const image = { url: "", alt: "", caption: "" };

export function newId(prefix: string, taken: string[] = []): string {
  const clean = prefix.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 30) || "section";
  if (!taken.includes(clean)) return clean;
  for (let i = 2; ; i++) if (!taken.includes(`${clean}-${i}`)) return `${clean}-${i}`;
}

export function blankSection(type: SectionType, id: string): Section {
  switch (type) {
    case "hero": return { ...base, type, id, eyebrow: "", image, layout: "split", stats: [] };
    case "about": return { ...base, type, id, heading: "About us", body: "", image, layout: "image_right", highlights: [] };
    case "doctors": return { ...base, type, id, heading: "Our doctors", professional_ids: [], layout: "grid", show_fees: false };
    case "services": return { ...base, type, id, heading: "Services", service_ids: [], category_ids: [], layout: "cards", show_prices: true, group_by_category: true };
    case "categories": return { ...base, type, id, heading: "Treatments", category_ids: [] };
    case "features": return { ...base, type, id, heading: "Facilities", items: [], columns: 3 };
    case "gallery": return { ...base, type, id, heading: "Our clinic", images: [], layout: "grid" };
    case "testimonials": return { ...base, type, id, heading: "What our patients say", items: [] };
    case "faq": return { ...base, type, id, heading: "Frequently asked questions", items: [] };
    case "branches": return { ...base, type, id, heading: "Locations and opening hours", branch_ids: [], show_hours: true, show_map: true };
    case "contact": return { ...base, type, id, heading: "Contact us", show_phone: true, show_email: true, show_whatsapp: true, show_map: true };
    case "cta": return { ...base, type, id, heading: "Ready to book?", background: "brand", buttons: [newButton("book", "book-now", "Book appointment")] };
    case "text": return { ...base, type, id, body: "", width: "narrow" };
  }
}

export interface Template { key: string; type: SectionType; label: string; description: string; apply?: (s: Section) => Section }

export const TEMPLATES: Template[] = [
  { key: "hero-split", type: "hero", label: "Hero with photo", description: "Headline and buttons beside a large photo." },
  { key: "hero-full", type: "hero", label: "Full-width photo hero", description: "Text over a full-width banner image.", apply: (s) => ({ ...s, layout: "full" } as Section) },
  { key: "hero-centered", type: "hero", label: "Centered hero", description: "Large centered headline, no photo.", apply: (s) => ({ ...s, layout: "centered" } as Section) },
  { key: "about", type: "about", label: "About the clinic", description: "Your story with a photo and key numbers." },
  { key: "doctors", type: "doctors", label: "Doctor profiles", description: "Cards from your doctors list, with a Book button." },
  { key: "services-cards", type: "services", label: "Services (cards)", description: "Fees, duration and Book buttons, grouped by category." },
  { key: "services-list", type: "services", label: "Services (price list)", description: "A compact list, good for many services.", apply: (s) => ({ ...s, layout: "list" } as Section) },
  { key: "categories", type: "categories", label: "Treatment categories", description: "Tiles for each category." },
  { key: "features", type: "features", label: "Facilities / why choose us", description: "Icons with short text, 2–4 columns." },
  { key: "gallery", type: "gallery", label: "Photo gallery", description: "Clinic, rooms and facilities photos." },
  { key: "testimonials", type: "testimonials", label: "Patient reviews", description: "Only approved reviews with consent are shown." },
  { key: "faq", type: "faq", label: "FAQ", description: "Questions and answers that open on tap." },
  { key: "branches", type: "branches", label: "Locations and hours", description: "Address, opening hours, directions and booking per location." },
  { key: "contact", type: "contact", label: "Contact", description: "Phone, WhatsApp, email and map." },
  { key: "cta", type: "cta", label: "Call-to-action banner", description: "A coloured banner with buttons." },
  { key: "text", type: "text", label: "Text block", description: "Free text with headings and lists." },
];

export const SECTION_LABELS: Record<SectionType, string> = {
  hero: "Hero", about: "About", doctors: "Doctors", services: "Services", categories: "Treatment categories", features: "Facilities",
  gallery: "Gallery", testimonials: "Testimonials", faq: "FAQ", branches: "Locations", contact: "Contact", cta: "Call to action", text: "Text",
};

export function newButton(kind: SiteButton["kind"], id: string, label: string): SiteButton {
  return { id, label, kind, url: "", page: "", phone: "", service: "", branch: "", message: "", style: "solid", color: "primary", custom_color: "",
    icon: kind === "book" ? "calendar" : kind === "call" ? "phone" : kind === "whatsapp" ? "message-circle" : "none", new_tab: false, visible: true, positions: [] };
}
