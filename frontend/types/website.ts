/** Mirrors backend/app/schemas/website.py. The server validates everything; these types keep the editor honest. */

export const FONTS = ["modern", "classic", "friendly", "system"] as const;
export const ICONS = [
  "none", "calendar", "phone", "message-circle", "mail", "map-pin", "external-link", "file-text", "arrow-right",
  "stethoscope", "heart-pulse", "leaf", "shield-check", "clock", "star", "award", "users", "sparkles", "home",
] as const;
export const BUTTON_KINDS = ["book", "call", "whatsapp", "contact", "services", "external", "url", "maps", "pdf", "page"] as const;
export const BUTTON_POSITIONS = ["header", "hero", "footer", "service_cards", "floating", "contact"] as const;

export type Font = (typeof FONTS)[number];
export type IconName = (typeof ICONS)[number];
export type ButtonKind = (typeof BUTTON_KINDS)[number];
export type ButtonPosition = (typeof BUTTON_POSITIONS)[number];

export interface SiteImage { url: string; alt: string; caption: string }

export interface SiteButton {
  id: string;
  label: string;
  kind: ButtonKind;
  url: string;
  page: string;
  phone: string;
  service: string;
  branch: string;
  message: string;
  style: "solid" | "outline" | "soft" | "link";
  color: "primary" | "secondary" | "dark" | "light" | "custom";
  custom_color: string;
  icon: IconName;
  new_tab: boolean;
  visible: boolean;
  positions: ButtonPosition[];
}

export interface NavItem { label: string; kind: "section" | "page" | "url" | "book"; target: string; new_tab: boolean }

export interface SiteSettings {
  site_name: string;
  clinic_name: string;
  tagline: string;
  description: string;
  logo_url: string;
  favicon_url: string;
  primary_color: string;
  secondary_color: string;
  background_color: string;
  font: Font;
  phone: string;
  email: string;
  whatsapp: string;
  address: string;
  social: { facebook: string; instagram: string; youtube: string; x: string; linkedin: string; google: string };
}

export interface Stat { value: string; label: string }
export type Background = "default" | "muted" | "brand" | "dark" | "custom";

interface SectionBase {
  id: string;
  enabled: boolean;
  heading: string;
  intro: string;
  background: Background;
  custom_background: string;
}

export interface HeroSection extends SectionBase { type: "hero"; eyebrow: string; image: SiteImage; layout: "split" | "full" | "centered"; stats: Stat[] }
export interface AboutSection extends SectionBase { type: "about"; body: string; image: SiteImage; layout: "image_left" | "image_right" | "text_only"; highlights: Stat[] }
export interface DoctorsSection extends SectionBase { type: "doctors"; professional_ids: string[]; layout: "grid" | "list"; show_fees: boolean }
export interface ServicesSection extends SectionBase { type: "services"; service_ids: string[]; category_ids: string[]; layout: "cards" | "list"; show_prices: boolean; group_by_category: boolean }
export interface CategoriesSection extends SectionBase { type: "categories"; category_ids: string[] }
export interface Feature { icon: IconName; title: string; text: string }
export interface FeaturesSection extends SectionBase { type: "features"; items: Feature[]; columns: 2 | 3 | 4 }
export interface GallerySection extends SectionBase { type: "gallery"; images: SiteImage[]; layout: "grid" | "mosaic" }
export interface Testimonial {
  id: string; name: string; text: string; rating: number | null; context: string; received_on: string | null;
  source: "in_clinic" | "google" | "email" | "whatsapp" | "other"; consent: boolean; approved: boolean;
}
export interface TestimonialsSection extends SectionBase { type: "testimonials"; items: Testimonial[] }
export interface FAQItem { question: string; answer: string }
export interface FAQSection extends SectionBase { type: "faq"; items: FAQItem[] }
export interface BranchesSection extends SectionBase { type: "branches"; branch_ids: string[]; show_hours: boolean; show_map: boolean }
export interface ContactSection extends SectionBase { type: "contact"; show_phone: boolean; show_email: boolean; show_whatsapp: boolean; show_map: boolean }
export interface CTASection extends SectionBase { type: "cta"; buttons: SiteButton[] }
export interface TextSection extends SectionBase { type: "text"; body: string; width: "narrow" | "wide" }

export type Section =
  | HeroSection | AboutSection | DoctorsSection | ServicesSection | CategoriesSection | FeaturesSection | GallerySection
  | TestimonialsSection | FAQSection | BranchesSection | ContactSection | CTASection | TextSection;
export type SectionType = Section["type"];

export interface SitePage {
  slug: string; title: string; body: string; sections: Section[]; enabled: boolean; show_in_nav: boolean;
  seo_title: string; seo_description: string;
}

export interface WebsiteDocument {
  version: 1;
  settings: SiteSettings;
  header: { sticky: boolean; show_logo: boolean; show_phone: boolean; nav: NavItem[] };
  sections: Section[];
  buttons: SiteButton[];
  footer: { about: string; columns: { title: string; links: NavItem[] }[]; show_social: boolean; show_policies: boolean; show_branches: boolean; copyright: string };
  pages: SitePage[];
  seo: { title: string; description: string; image_url: string; noindex: boolean };
}

export interface WebsiteState {
  draft: WebsiteDocument;
  published: WebsiteDocument | null;
  lock_version: number;
  published_version: number;
  published_at: string | null;
  draft_updated_at: string | null;
  has_unpublished_changes: boolean;
  public_url_path: string;
}

export interface WebsiteVersion { version: number; published_at: string; published_by: string | null; note: string | null }
export interface PublicWebsite { document: WebsiteDocument; published: boolean; version: number }
