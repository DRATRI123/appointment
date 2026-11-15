"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Award, CalendarDays, Clock, ExternalLink, Languages, Mail, MapPin, Phone, Quote, Star, Video } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { addressLine, initials } from "@/components/public-booking/booking-shell";
import { PriceTag } from "@/components/public-booking/steps";
import { bookHref, mapsLink, phoneDigits, whatsappLink } from "@/lib/site-links";
import { cn } from "@/lib/utils";
import { safeHex, textOn } from "@/components/public-booking/brand";
import { Markdown } from "./markdown";
import { ButtonsAt, SiteButtonLink } from "./site-button";
import { SiteIcon, SocialIcon } from "./icons";
import { SiteLogo } from "./site-shell";
import { useSite } from "./site-context";
import type { Branch, BusinessHours, Professional, Service } from "@/types/catalog";
import type {
  AboutSection, Background, BranchesSection, CategoriesSection, ContactSection, CTASection, DoctorsSection, FAQSection,
  FeaturesSection, GallerySection, HeroSection, Section, ServicesSection, TestimonialsSection, TextSection,
} from "@/types/website";

// ------------------------------------------------------------------------------------------------ shared data
export function useCatalog() {
  const { slug } = useSite();
  const services = useQuery({ queryKey: ["pb-services", slug, null], queryFn: () => publicCatalog.services(slug), staleTime: 60_000 });
  const pros = useQuery({ queryKey: ["site-pros", slug], queryFn: () => publicCatalog.professionals(slug), staleTime: 60_000 });
  return { services: services.data ?? [], pros: pros.data ?? [], loading: services.isLoading || pros.isLoading };
}

/** Keep the admin's chosen order when ids are listed; otherwise show everything. */
function pick<T extends { id: string }>(items: T[], ids: string[]): T[] {
  if (!ids.length) return items;
  const byId = new Map(items.map((i) => [i.id, i]));
  return ids.map((id) => byId.get(id)).filter((x): x is T => !!x);
}

function bgStyle(background: Background, custom: string): { style?: React.CSSProperties; className: string; dark: boolean } {
  switch (background) {
    case "muted": return { className: "bg-[color-mix(in_oklab,var(--site-bg)_94%,#000)]", dark: false };
    case "brand": return { className: "bg-[var(--primary)] text-[var(--primary-foreground)]", dark: true };
    case "dark": return { className: "bg-[#0f172a] text-white", dark: true };
    case "custom": {
      const c = safeHex(custom, "#f5f5f4");
      return { style: { background: c, color: textOn(c) }, className: "", dark: textOn(c) === "#ffffff" };
    }
    default: return { className: "", dark: false };
  }
}

function Shell({ section, children, wide = true, className }: { section: Section; children: React.ReactNode; wide?: boolean; className?: string }) {
  const bg = bgStyle(section.background, section.custom_background);
  return (
    <section id={section.id} className={cn("scroll-mt-20 py-16 sm:py-24", bg.className, className)} style={bg.style} aria-labelledby={section.heading ? `${section.id}-title` : undefined} data-section={section.type}>
      <div className={cn("mx-auto px-4", wide ? "max-w-6xl" : "max-w-3xl")}>{children}</div>
    </section>
  );
}

function Heading({ section, center = false }: { section: Section; center?: boolean }) {
  if (!section.heading && !section.intro) return null;
  return (
    <div className={cn("mb-10 max-w-2xl space-y-3", center && "mx-auto text-center")}>
      {section.heading ? <h2 id={`${section.id}-title`} className="text-3xl font-semibold tracking-tight text-balance [font-family:var(--site-heading-font)] sm:text-4xl">{section.heading}</h2> : null}
      {section.intro ? <p className="text-lg text-pretty opacity-75">{section.intro}</p> : null}
    </div>
  );
}

function PreviewHint({ section, text }: { section: Section; text: string }) {
  return (
    <Shell section={section}>
      <Heading section={section} />
      <p className="rounded-2xl border-2 border-dashed border-current/20 p-8 text-center text-sm opacity-70">{text} <span className="block text-xs">(Only you see this in the preview. Visitors don&apos;t see empty sections.)</span></p>
    </Shell>
  );
}

// ---------------------------------------------------------------------------------------------------- hero
function Hero({ s }: { s: HeroSection }) {
  const { doc, org } = useSite();
  const name = s.heading || doc.settings.clinic_name;
  const image = s.image.url ? mediaUrl(s.image.url) : undefined;
  const city = (org.branches[0]?.address as Record<string, string> | null)?.city;
  const text = (
    <div className={cn("space-y-6", s.layout !== "split" && "mx-auto max-w-3xl text-center")}>
      {s.eyebrow ? <p className={cn("pb-enter inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider", s.layout === "full" && image ? "bg-white/15 text-white backdrop-blur" : "bg-[color-mix(in_oklab,var(--primary)_12%,transparent)] text-[var(--primary)]")}><span className="size-1.5 rounded-full bg-current" />{s.eyebrow}</p> : null}
      <h1 className="pb-enter text-4xl font-semibold leading-[1.05] tracking-tight text-balance [font-family:var(--site-heading-font)] sm:text-5xl lg:text-6xl">{name}</h1>
      {s.intro ? <p className={cn("pb-enter max-w-xl text-lg leading-relaxed text-pretty opacity-80 sm:text-xl", s.layout !== "split" && "mx-auto")}>{s.intro}</p> : null}
      <ButtonsAt position="hero" size="lg" className={cn("pb-enter pt-2", s.layout !== "split" && "justify-center")} buttonClassName={s.layout === "full" && image ? "" : ""} />
      {s.stats.length ? (
        <dl className={cn("pb-enter grid max-w-xl grid-cols-2 gap-6 border-t border-current/10 pt-6 sm:grid-cols-4", s.layout !== "split" && "mx-auto")}>
          {s.stats.map((st, i) => <div key={i}><dt className="sr-only">{st.label}</dt><dd className="text-2xl font-semibold [font-family:var(--site-heading-font)]">{st.value}</dd><dd className="text-sm opacity-70">{st.label}</dd></div>)}
        </dl>
      ) : null}
    </div>
  );
  if (s.layout === "full" && image) {
    return (
      <section id={s.id} className="relative isolate overflow-hidden text-white" data-section="hero">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={image} alt={s.image.alt} className="absolute inset-0 -z-20 h-full w-full object-cover" fetchPriority="high" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-t from-black/80 via-black/50 to-black/30" />
        <div className="mx-auto max-w-6xl px-4 py-28 sm:py-36">{text}</div>
      </section>
    );
  }
  if (s.layout === "centered" || !image) {
    const bg = bgStyle(s.background, s.custom_background);
    return (
      <section id={s.id} className={cn("relative isolate overflow-hidden", bg.className)} style={bg.style} data-section="hero">
        <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(900px_420px_at_85%_-10%,color-mix(in_oklab,var(--site-secondary)_30%,transparent),transparent_65%)]" />
        <div className={cn("mx-auto grid max-w-6xl items-center gap-12 px-4 py-20 sm:py-28", s.layout === "split" && "lg:grid-cols-[1.2fr_0.8fr]")}>
          {text}
          {s.layout === "split" ? (
            <div className="pb-enter hidden rounded-[2rem] border border-black/5 bg-white/70 p-8 shadow-xl shadow-black/5 backdrop-blur lg:block">
              <div className="flex items-center gap-4"><SiteLogo size="lg" /><div><p className="font-semibold">{doc.settings.clinic_name}</p>{city ? <p className="flex items-center gap-1 text-sm opacity-70"><MapPin className="size-3.5" aria-hidden />{city}{org.branches.length > 1 ? ` · ${org.branches.length} locations` : ""}</p> : null}</div></div>
              <ul className="mt-6 space-y-3 text-sm">
                <li className="flex items-center gap-3"><CalendarDays className="size-4 text-[var(--primary)]" aria-hidden />Choose a time that suits you</li>
                <li className="flex items-center gap-3"><Clock className="size-4 text-[var(--primary)]" aria-hidden />Live availability from the clinic&apos;s calendar</li>
                {doc.settings.phone ? <li className="flex items-center gap-3"><Phone className="size-4 text-[var(--primary)]" aria-hidden />{doc.settings.phone}</li> : null}
              </ul>
            </div>
          ) : null}
        </div>
      </section>
    );
  }
  return (
    <section id={s.id} className="relative isolate overflow-hidden" data-section="hero">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(900px_420px_at_10%_-10%,color-mix(in_oklab,var(--site-secondary)_22%,transparent),transparent_65%)]" />
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:py-24 lg:grid-cols-2">
        {text}
        <div className="pb-enter relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image} alt={s.image.alt} className="aspect-[4/3] w-full rounded-[2rem] object-cover shadow-2xl shadow-black/10 lg:aspect-[4/5]" fetchPriority="high" />
          {s.image.caption ? <p className="absolute bottom-4 left-4 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-gray-900 shadow">{s.image.caption}</p> : null}
        </div>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------------------------------- about
function About({ s }: { s: AboutSection }) {
  const { preview } = useSite();
  if (!s.body && !s.intro && !s.highlights.length) return preview ? <PreviewHint section={s} text="Write a few lines about the clinic." /> : null;
  const image = s.image.url && s.layout !== "text_only" ? mediaUrl(s.image.url) : undefined;
  return (
    <Shell section={s}>
      <div className={cn("grid items-center gap-12", image && "lg:grid-cols-2")}>
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt={s.image.alt} loading="lazy" className={cn("aspect-[4/3] w-full rounded-[2rem] object-cover shadow-xl shadow-black/5", s.layout === "image_right" && "lg:order-2")} />
        ) : null}
        <div>
          <Heading section={s} />
          {s.body ? <Markdown source={s.body} className="text-lg opacity-85" /> : null}
          {s.highlights.length ? (
            <dl className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3">
              {s.highlights.map((h, i) => <div key={i} className="rounded-2xl border border-current/10 p-4"><dd className="text-2xl font-semibold text-[var(--primary)] [font-family:var(--site-heading-font)]">{h.value}</dd><dt className="text-sm opacity-70">{h.label}</dt></div>)}
            </dl>
          ) : null}
        </div>
      </div>
    </Shell>
  );
}

// ------------------------------------------------------------------------------------------------- doctors
export function DoctorCard({ pro, showFee, compact = false }: { pro: Professional; showFee?: boolean; compact?: boolean }) {
  const { base, campaign } = useSite();
  const [open, setOpen] = useState(false);
  const photo = pro.profile_photo_url ? mediaUrl(pro.profile_photo_url) : undefined;
  const branches = (pro.branches ?? []).map((b) => b.branch_name).filter(Boolean);
  return (
    <article className="group flex flex-col overflow-hidden rounded-3xl border border-black/5 bg-white text-gray-900 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-black/5 motion-reduce:hover:translate-y-0" data-testid="site-doctor">
      <div className={cn("relative overflow-hidden bg-[color-mix(in_oklab,var(--primary)_10%,#fff)]", compact || !pro.profile_photo_url ? "aspect-[16/9]" : "aspect-[16/10] sm:aspect-[4/3]")}>
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photo} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105 motion-reduce:group-hover:scale-100" />
        ) : (
          <span className="grid h-full w-full place-items-center text-5xl font-semibold text-[var(--primary)] [font-family:var(--site-heading-font)]">{initials(pro.display_name)}</span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-6">
        <div>
          <h3 className="text-lg font-semibold [font-family:var(--site-heading-font)]">{pro.display_name}</h3>
          {pro.specialization || pro.title ? <p className="text-sm font-medium text-[var(--primary)]">{pro.specialization ?? pro.title}</p> : null}
          {pro.qualification ? <p className="text-sm text-gray-600">{pro.qualification}</p> : null}
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600">
          {pro.experience_years ? <li className="flex items-center gap-1"><Award className="size-3.5" aria-hidden />{pro.experience_years}+ years</li> : null}
          {pro.languages?.length ? <li className="flex items-center gap-1"><Languages className="size-3.5" aria-hidden />{pro.languages.join(", ")}</li> : null}
          {pro.consultation_modes?.includes("online") ? <li className="flex items-center gap-1"><Video className="size-3.5" aria-hidden />Video consults</li> : null}
          {branches.length ? <li className="flex items-center gap-1"><MapPin className="size-3.5" aria-hidden />{branches.join(", ")}</li> : null}
        </ul>
        {showFee && pro.default_fee_paise ? <p className="text-sm text-gray-700">Consultation from <b>₹{(pro.default_fee_paise / 100).toLocaleString("en-IN")}</b></p> : null}
        <div className="mt-auto flex items-center justify-between gap-3 pt-2">
          {pro.biography || pro.registration_number ? <button type="button" onClick={() => setOpen(true)} className="text-sm font-medium text-gray-700 underline-offset-4 hover:underline">View profile</button> : <span />}
          <Link href={bookHref(base, { doctor: pro.slug }, campaign)} className="inline-flex h-10 items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-foreground)] transition-opacity hover:opacity-90">
            Book <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{pro.display_name}</DialogTitle>
            <DialogDescription>{[pro.specialization ?? pro.title, pro.qualification].filter(Boolean).join(" · ")}</DialogDescription>
          </DialogHeader>
          {pro.biography ? <p className="whitespace-pre-line text-sm text-muted-foreground">{pro.biography}</p> : null}
          {pro.registration_number ? <p className="text-xs text-muted-foreground">Registration {pro.registration_number}{pro.registration_council ? `, ${pro.registration_council}` : ""}</p> : null}
          <Link href={bookHref(base, { doctor: pro.slug }, campaign)} className="inline-flex h-11 items-center justify-center rounded-full bg-[var(--primary)] px-5 text-sm font-semibold text-[var(--primary-foreground)]">Book with {pro.display_name}</Link>
        </DialogContent>
      </Dialog>
    </article>
  );
}

function Doctors({ s }: { s: DoctorsSection }) {
  const { pros, loading } = useCatalog();
  const { preview } = useSite();
  const list = pick(pros, s.professional_ids);
  if (!loading && !list.length) return preview ? <PreviewHint section={s} text="Doctors bookable online appear here automatically." /> : null;
  return (
    <Shell section={s}>
      <Heading section={s} />
      <div className={cn("grid gap-6", s.layout === "grid" ? "sm:grid-cols-2 lg:grid-cols-3" : "lg:grid-cols-2")}>
        {list.map((p) => <DoctorCard key={p.id} pro={p} showFee={s.show_fees} compact={s.layout === "list"} />)}
      </div>
    </Shell>
  );
}

// ------------------------------------------------------------------------------------------------ services
export function ServiceCard({ service, showPrice }: { service: Service; showPrice: boolean }) {
  const { base, campaign } = useSite();
  return (
    <article className="group flex flex-col gap-4 rounded-3xl border border-black/5 bg-white p-6 text-gray-900 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-black/5 motion-reduce:hover:translate-y-0" data-testid="site-service">
      {service.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(service.image_url)} alt="" loading="lazy" className="-mx-6 -mt-6 aspect-[16/9] w-[calc(100%+3rem)] max-w-none rounded-t-3xl object-cover" />
      ) : null}
      <div className="space-y-1.5">
        <h3 className="text-lg font-semibold [font-family:var(--site-heading-font)]">{service.name}</h3>
        {service.short_description || service.description ? <p className="line-clamp-3 text-sm text-gray-600">{service.short_description ?? service.description}</p> : null}
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-600">
        <span className="flex items-center gap-1"><Clock className="size-4" aria-hidden />{service.duration_minutes} min</span>
        {service.consultation_mode === "online" ? <span className="flex items-center gap-1"><Video className="size-4" aria-hidden />Online</span> : null}
        {showPrice ? <span className="ml-auto text-base text-gray-900"><PriceTag service={service} /></span> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-black/5 pt-4">
        <Link href={bookHref(base, { service: service.slug }, campaign)} className="inline-flex h-10 items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-foreground)] transition-opacity hover:opacity-90">
          Book now <ArrowRight className="size-4" aria-hidden />
        </Link>
        <ButtonsAt position="service_cards" size="sm" />
      </div>
    </article>
  );
}

function Services({ s }: { s: ServicesSection }) {
  const { services, loading } = useCatalog();
  const { org, preview } = useSite();
  let list = pick(services, s.service_ids);
  if (s.category_ids.length) list = list.filter((x) => x.category_id && s.category_ids.includes(x.category_id));
  if (!loading && !list.length) return preview ? <PreviewHint section={s} text="Services bookable online appear here automatically." /> : null;
  const groups = s.group_by_category
    ? org.categories.map((c) => ({ name: c.name, items: list.filter((x) => x.category_id === c.id) })).filter((g) => g.items.length)
      .concat([{ name: "Other services", items: list.filter((x) => !x.category_id || !org.categories.some((c) => c.id === x.category_id)) }].filter((g) => g.items.length))
    : [{ name: "", items: list }];
  const showGroupNames = groups.length > 1;
  return (
    <Shell section={s}>
      <Heading section={s} />
      <div className="space-y-12">
        {groups.map((g) => (
          <div key={g.name || "all"} className="space-y-5">
            {showGroupNames ? <h3 className="text-sm font-semibold uppercase tracking-wider opacity-60">{g.name}</h3> : null}
            {s.layout === "cards" ? (
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{g.items.map((x) => <ServiceCard key={x.id} service={x} showPrice={s.show_prices} />)}</div>
            ) : (
              <ul className="divide-y divide-current/10 rounded-3xl border border-current/10">
                {g.items.map((x) => <ServiceRow key={x.id} service={x} showPrice={s.show_prices} />)}
              </ul>
            )}
          </div>
        ))}
      </div>
    </Shell>
  );
}

function ServiceRow({ service, showPrice }: { service: Service; showPrice: boolean }) {
  const { base, campaign } = useSite();
  return (
    <li className="flex flex-wrap items-center gap-4 p-5" data-testid="site-service">
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{service.name}</p>
        <p className="text-sm opacity-70">{service.duration_minutes} min{service.short_description ? ` · ${service.short_description}` : ""}</p>
      </div>
      {showPrice ? <PriceTag service={service} /> : null}
      <Link href={bookHref(base, { service: service.slug }, campaign)} className="inline-flex h-9 items-center rounded-full bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-foreground)]">Book</Link>
    </li>
  );
}

function Categories({ s }: { s: CategoriesSection }) {
  const { org, base, preview, links } = useSite();
  const list = pick(org.categories, s.category_ids);
  if (!list.length) return preview ? <PreviewHint section={s} text="Add treatment categories under Catalogue → Categories." /> : null;
  return (
    <Shell section={s}>
      <Heading section={s} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {list.map((c) => (
          <a key={c.id} href={`${base}#${links.sectionIds?.services ?? "services"}`} className="group relative overflow-hidden rounded-3xl border border-black/5 bg-white p-6 text-gray-900 shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg motion-reduce:hover:translate-y-0">
            {c.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={mediaUrl(c.image_url)} alt="" loading="lazy" className="mb-4 aspect-[3/2] w-full rounded-2xl object-cover" />
            ) : <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_12%,#fff)] text-[var(--primary)]"><SiteIcon name="leaf" className="size-6" /></span>}
            <p className="font-semibold">{c.name}</p>
            {c.description ? <p className="mt-1 line-clamp-2 text-sm text-gray-600">{c.description}</p> : null}
            {c.service_count ? <p className="mt-3 text-xs font-medium text-[var(--primary)]">{c.service_count} service{c.service_count === 1 ? "" : "s"}</p> : null}
          </a>
        ))}
      </div>
    </Shell>
  );
}

// ------------------------------------------------------------------------------------------------- features
function Features({ s }: { s: FeaturesSection }) {
  const { preview } = useSite();
  if (!s.items.length) return preview ? <PreviewHint section={s} text="Add facilities or reasons to choose the clinic." /> : null;
  const bg = bgStyle(s.background, s.custom_background);
  return (
    <Shell section={s}>
      <Heading section={s} />
      <div className={cn("grid gap-6 sm:grid-cols-2", s.columns === 3 && "lg:grid-cols-3", s.columns === 4 && "lg:grid-cols-4")}>
        {s.items.map((f, i) => (
          <div key={i} className={cn("rounded-3xl p-6", bg.dark ? "bg-white/10" : "border border-black/5 bg-white text-gray-900 shadow-sm")}>
            <span className={cn("mb-4 grid size-12 place-items-center rounded-2xl", bg.dark ? "bg-white/15" : "bg-[color-mix(in_oklab,var(--primary)_12%,#fff)] text-[var(--primary)]")}><SiteIcon name={f.icon === "none" ? "sparkles" : f.icon} className="size-6" /></span>
            <h3 className="font-semibold">{f.title}</h3>
            {f.text ? <p className={cn("mt-2 text-sm leading-relaxed", bg.dark ? "opacity-80" : "text-gray-600")}>{f.text}</p> : null}
          </div>
        ))}
      </div>
    </Shell>
  );
}

// -------------------------------------------------------------------------------------------------- gallery
function Gallery({ s }: { s: GallerySection }) {
  const { preview } = useSite();
  const [open, setOpen] = useState<number | null>(null);
  const images = s.images.filter((i) => i.url);
  if (!images.length) return preview ? <PreviewHint section={s} text="Upload photos of the clinic, rooms and facilities." /> : null;
  const current = open !== null ? images[open] : null;
  return (
    <Shell section={s}>
      <Heading section={s} />
      <ul className={cn("grid gap-4", s.layout === "mosaic" ? "grid-cols-2 sm:grid-cols-3 [&>li:nth-child(5n+1)]:sm:col-span-2 [&>li:nth-child(5n+1)]:sm:row-span-2" : "grid-cols-2 lg:grid-cols-3")}>
        {images.map((img, i) => (
          <li key={i} className="overflow-hidden rounded-2xl">
            <button type="button" onClick={() => setOpen(i)} className="group relative block h-full w-full focus-visible:outline-2 focus-visible:outline-[var(--primary)]" aria-label={img.alt || img.caption || `Photo ${i + 1}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={mediaUrl(img.url)} alt={img.alt} loading="lazy" className="aspect-[4/3] h-full w-full object-cover transition-transform duration-500 group-hover:scale-105 motion-reduce:group-hover:scale-100" />
              {img.caption ? <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3 text-left text-sm font-medium text-white">{img.caption}</span> : null}
            </button>
          </li>
        ))}
      </ul>
      <Dialog open={open !== null} onOpenChange={(o) => { if (!o) setOpen(null); }}>
        {current ? (
          <DialogContent className="max-w-4xl p-2">
            <DialogTitle className="sr-only">{current.caption || current.alt || "Photo"}</DialogTitle>
            <DialogDescription className="sr-only">Enlarged photo</DialogDescription>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={mediaUrl(current.url)} alt={current.alt} className="max-h-[80dvh] w-full rounded-lg object-contain" />
            {current.caption ? <p className="p-2 text-center text-sm text-muted-foreground">{current.caption}</p> : null}
          </DialogContent>
        ) : null}
      </Dialog>
    </Shell>
  );
}

// -------------------------------------------------------------------------------------------- testimonials
const SOURCE_LABEL = { in_clinic: "Patient", google: "Google review", email: "By email", whatsapp: "By WhatsApp", other: "Patient" } as const;

function Testimonials({ s }: { s: TestimonialsSection }) {
  const { preview } = useSite();
  // Only reviews the clinic approved, with the patient's consent on record, are ever shown.
  const items = s.items.filter((t) => t.approved && t.consent);
  if (!items.length) return preview ? <PreviewHint section={s} text="Approved patient reviews appear here (Website → Testimonials)." /> : null;
  return (
    <Shell section={s}>
      <Heading section={s} />
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {items.map((t) => (
          <figure key={t.id} className="flex flex-col gap-4 rounded-3xl border border-black/5 bg-white p-6 text-gray-900 shadow-sm" data-testid="site-testimonial">
            <Quote className="size-7 text-[var(--primary)] opacity-60" aria-hidden />
            {t.rating ? <p className="flex gap-0.5" aria-label={`${t.rating} out of 5 stars`}>{Array.from({ length: 5 }, (_, i) => <Star key={i} className={cn("size-4", i < t.rating! ? "fill-amber-400 text-amber-400" : "text-gray-300")} aria-hidden />)}</p> : null}
            <blockquote className="flex-1 leading-relaxed text-gray-700">“{t.text}”</blockquote>
            <figcaption className="text-sm"><span className="font-semibold">{t.name}</span>{t.context ? <span className="text-gray-500"> · {t.context}</span> : null}<span className="block text-xs text-gray-500">{SOURCE_LABEL[t.source]}</span></figcaption>
          </figure>
        ))}
      </div>
    </Shell>
  );
}

// ---------------------------------------------------------------------------------------------------- FAQ
function FAQ({ s }: { s: FAQSection }) {
  const { preview } = useSite();
  if (!s.items.length) return preview ? <PreviewHint section={s} text="Add common questions about timings, payments and treatments." /> : null;
  return (
    <Shell section={s} wide={false}>
      <Heading section={s} center />
      <div className="divide-y divide-current/10 rounded-3xl border border-current/10">
        {s.items.map((f, i) => (
          <details key={i} className="group p-5 [&_summary::-webkit-details-marker]:hidden" data-testid="site-faq">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
              {f.question}
              <span className="grid size-7 shrink-0 place-items-center rounded-full border border-current/20 transition-transform group-open:rotate-45" aria-hidden>+</span>
            </summary>
            <Markdown source={f.answer} className="pt-3 opacity-80" />
          </details>
        ))}
      </div>
    </Shell>
  );
}

// ---------------------------------------------------------------------------------------------- locations
const DAYS: [string, string][] = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];

function fmt(t: string) {
  const [h, m] = t.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

export function HoursTable({ hours }: { hours: BusinessHours | null }) {
  if (!hours || !Object.keys(hours).length) return null;
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Opening hours</caption>
      <tbody>
        {DAYS.map(([key, label]) => (
          <tr key={key} className="border-b border-current/5 last:border-0">
            <th scope="row" className="py-1.5 pr-4 text-left font-normal opacity-70">{label}</th>
            <td className="py-1.5 text-right tabular-nums">{hours[key]?.length ? hours[key].map(([a, b]) => `${fmt(a)} – ${fmt(b)}`).join(", ") : <span className="opacity-60">Closed</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function BranchCard({ branch, showHours = true, showMap = true }: { branch: Branch; showHours?: boolean; showMap?: boolean }) {
  const { base, campaign, doc } = useSite();
  const line = addressLine(branch.address);
  const maps = branch.latitude !== null && branch.longitude !== null ? mapsLink(`${branch.latitude},${branch.longitude}`) : line ? mapsLink(`${doc.settings.clinic_name} ${line}`) : null;
  return (
    <article className="flex flex-col gap-4 rounded-3xl border border-black/5 bg-white p-6 text-gray-900 shadow-sm" data-testid="site-branch">
      {branch.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(branch.image_url)} alt="" loading="lazy" className="-mx-6 -mt-6 aspect-[16/9] w-[calc(100%+3rem)] max-w-none rounded-t-3xl object-cover" />
      ) : null}
      <div>
        <h3 className="text-lg font-semibold [font-family:var(--site-heading-font)]"><Link href={`${base}/${branch.slug}`} className="hover:underline">{branch.name}</Link></h3>
        {line ? <p className="mt-1 flex gap-2 text-sm text-gray-600"><MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />{line}</p> : null}
        {branch.phone ? <p className="mt-1 flex gap-2 text-sm text-gray-600"><Phone className="mt-0.5 size-4 shrink-0" aria-hidden /><a href={`tel:${phoneDigits(branch.phone)}`} className="hover:underline">{branch.phone}</a></p> : null}
      </div>
      {showHours ? <HoursTable hours={branch.business_hours} /> : null}
      <div className="mt-auto flex flex-wrap gap-2 pt-2">
        <Link href={bookHref(base, { branch: branch.slug }, campaign)} className="inline-flex h-10 items-center rounded-full bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-foreground)]">Book here</Link>
        {showMap && maps ? <a href={maps} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-full border border-gray-200 px-4 text-sm font-medium hover:bg-gray-50">Directions <ExternalLink className="size-3.5" aria-hidden /></a> : null}
      </div>
    </article>
  );
}

function Branches({ s }: { s: BranchesSection }) {
  const { org, preview } = useSite();
  const list = pick(org.branches, s.branch_ids);
  if (!list.length) return preview ? <PreviewHint section={s} text="Add locations under Catalogue → Branches." /> : null;
  return (
    <Shell section={s}>
      <Heading section={s} />
      <div className={cn("grid gap-6", list.length > 1 && "md:grid-cols-2 lg:grid-cols-3")}>
        {list.map((b) => <BranchCard key={b.id} branch={b} showHours={s.show_hours} showMap={s.show_map} />)}
      </div>
    </Shell>
  );
}

// -------------------------------------------------------------------------------------------------- contact
function Contact({ s }: { s: ContactSection }) {
  const { doc, org } = useSite();
  const st = doc.settings;
  const address = st.address || addressLine(org.branches[0]?.address);
  const items = [
    s.show_phone && st.phone ? { icon: <Phone className="size-5" aria-hidden />, label: "Call us", value: st.phone, href: `tel:${phoneDigits(st.phone)}` } : null,
    s.show_whatsapp && st.whatsapp ? { icon: <SocialIcon network="whatsapp" className="size-5" />, label: "WhatsApp", value: st.whatsapp, href: whatsappLink(st.whatsapp), external: true } : null,
    s.show_email && st.email ? { icon: <Mail className="size-5" aria-hidden />, label: "Email", value: st.email, href: `mailto:${st.email}` } : null,
    s.show_map && address ? { icon: <MapPin className="size-5" aria-hidden />, label: "Find us", value: address, href: mapsLink(`${st.clinic_name} ${address}`), external: true } : null,
  ].filter((x): x is NonNullable<typeof x> => !!x);
  return (
    <Shell section={s}>
      <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <Heading section={s} />
          <ButtonsAt position="contact" size="lg" />
        </div>
        <ul className="grid gap-4 sm:grid-cols-2">
          {items.map((i) => (
            <li key={i.label}>
              <a href={i.href} {...(i.external ? { target: "_blank", rel: "noopener noreferrer" } : {})} className="flex h-full gap-4 rounded-3xl border border-black/5 bg-white p-5 text-gray-900 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md">
                <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-[color-mix(in_oklab,var(--primary)_12%,#fff)] text-[var(--primary)]">{i.icon}</span>
                <span className="min-w-0"><span className="block text-sm text-gray-500">{i.label}</span><span className="block break-words font-medium">{i.value}</span></span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </Shell>
  );
}

// ------------------------------------------------------------------------------------------------ CTA, text
function CTA({ s }: { s: CTASection }) {
  return (
    <section id={s.id} className="scroll-mt-20 px-4 py-16" data-section="cta">
      <div className={cn("mx-auto max-w-6xl rounded-[2rem] px-6 py-14 text-center sm:px-12", bgStyle(s.background === "default" ? "brand" : s.background, s.custom_background).className)}
        style={bgStyle(s.background === "default" ? "brand" : s.background, s.custom_background).style}>
        {s.heading ? <h2 className="text-3xl font-semibold tracking-tight text-balance [font-family:var(--site-heading-font)] sm:text-4xl">{s.heading}</h2> : null}
        {s.intro ? <p className="mx-auto mt-3 max-w-2xl text-lg opacity-85">{s.intro}</p> : null}
        <div className="mt-8 flex flex-wrap justify-center gap-3">{s.buttons.map((b) => <SiteButtonLink key={b.id} button={b} size="lg" />)}</div>
      </div>
    </section>
  );
}

function Text({ s }: { s: TextSection }) {
  const { preview } = useSite();
  if (!s.body && !s.heading) return preview ? <PreviewHint section={s} text="Write some text for this section." /> : null;
  return (
    <Shell section={s} wide={s.width === "wide"}>
      <Heading section={s} />
      {s.body ? <Markdown source={s.body} className="text-lg opacity-85" /> : null}
    </Shell>
  );
}

export function SectionView({ section }: { section: Section }) {
  if (!section.enabled) return null;
  switch (section.type) {
    case "hero": return <Hero s={section} />;
    case "about": return <About s={section} />;
    case "doctors": return <Doctors s={section} />;
    case "services": return <Services s={section} />;
    case "categories": return <Categories s={section} />;
    case "features": return <Features s={section} />;
    case "gallery": return <Gallery s={section} />;
    case "testimonials": return <Testimonials s={section} />;
    case "faq": return <FAQ s={section} />;
    case "branches": return <Branches s={section} />;
    case "contact": return <Contact s={section} />;
    case "cta": return <CTA s={section} />;
    case "text": return <Text s={section} />;
    default: return null;
  }
}
