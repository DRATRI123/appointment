"use client";

import { useState } from "react";
import { Award, Check, Clock, ExternalLink, Languages, MapPin, Phone, Sparkles, Stethoscope, UsersRound, Video } from "lucide-react";
import { mediaUrl } from "@/services/catalog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn, formatPaise } from "@/lib/utils";
import { addressLine, initials } from "./booking-shell";
import type { Branch, Category, Professional, Service } from "@/types/catalog";

const CARD = "group relative flex w-full flex-col rounded-2xl border bg-card p-4 text-left shadow-xs transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:hover:translate-y-0";
const SELECTED = "border-primary ring-2 ring-primary/20";

function SelectedMark({ on }: { on: boolean }) {
  return on ? <span className="absolute right-3 top-3 grid size-6 place-items-center rounded-full bg-primary text-primary-foreground shadow-sm"><Check className="size-3.5" aria-hidden /></span> : null;
}

export function servicePrice(service: Service, branchId?: string | null): { shown: number; was: number | null } {
  const base = (branchId ? (service as Service & { pricing?: { branch_id: string; price_paise: number }[] }).pricing?.find((p) => p.branch_id === branchId)?.price_paise : undefined) ?? service.price_paise;
  const discounted = service.discounted_price_paise;
  return discounted !== null && discounted < base ? { shown: discounted, was: base } : { shown: base, was: null };
}

export function PriceTag({ service, branchId }: { service: Service; branchId?: string | null }) {
  if (service.payment_mode === "free") return <span className="font-semibold text-success-ink">Free</span>;
  const { shown, was } = servicePrice(service, branchId);
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="font-semibold">{formatPaise(shown)}</span>
      {was !== null ? <span className="text-xs text-muted-foreground line-through">{formatPaise(was)}</span> : null}
    </span>
  );
}

// ------------------------------------------------------------------------------------------------- services
export function ServiceStep({ services, categories, selected, branchId, onSelect }: {
  services: Service[]; categories: Category[]; selected: string | null; branchId: string | null; onSelect: (s: Service) => void;
}) {
  const [category, setCategory] = useState<string | null>(null);
  const used = categories.filter((c) => services.some((s) => s.category_id === c.id));
  const shown = category ? services.filter((s) => s.category_id === category) : services;
  return (
    <div className="space-y-4">
      {used.length > 1 ? (
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]" role="group" aria-label="Filter by category">
          {[{ id: null, name: "All" }, ...used].map((c) => (
            <button key={c.id ?? "all"} type="button" aria-pressed={category === c.id} onClick={() => setCategory(c.id)}
              className={cn("shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors", category === c.id ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-muted")}>
              {c.name}
            </button>
          ))}
        </div>
      ) : null}
      {shown.length === 0 ? <EmptyChoice text="No services are available for online booking yet. Please call the clinic." /> : (
        <div className="grid gap-3 sm:grid-cols-2">
          {shown.map((s) => (
            <button key={s.id} type="button" data-testid="pick-service" onClick={() => onSelect(s)} className={cn(CARD, "gap-3", selected === s.id && SELECTED)} aria-pressed={selected === s.id}>
              <SelectedMark on={selected === s.id} />
              <div className="flex gap-3">
                {s.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={mediaUrl(s.image_url)} alt="" className="size-16 shrink-0 rounded-xl object-cover" />
                ) : (
                  <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-accent text-accent-foreground"><Stethoscope className="size-5" aria-hidden /></span>
                )}
                <div className="min-w-0 pr-6">
                  <p className="font-semibold leading-snug">{s.name}</p>
                  {s.category_name ? <p className="text-xs text-muted-foreground">{s.category_name}</p> : null}
                </div>
              </div>
              {s.short_description || s.description ? <p className="line-clamp-2 text-sm text-muted-foreground">{s.short_description ?? s.description}</p> : null}
              <div className="mt-auto flex items-center justify-between gap-3 border-t pt-3 text-sm">
                <span className="flex items-center gap-3 text-muted-foreground">
                  <span className="flex items-center gap-1"><Clock className="size-3.5" aria-hidden />{s.duration_minutes} min</span>
                  {s.consultation_mode === "online" ? <span className="flex items-center gap-1"><Video className="size-3.5" aria-hidden />Online</span> : null}
                </span>
                <PriceTag service={s} branchId={branchId} />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------- branches
export function BranchStep({ branches, selected, onSelect }: { branches: Branch[]; selected: string | null; onSelect: (b: Branch) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {branches.map((b) => {
        const line = addressLine(b.address);
        const maps = b.latitude !== null && b.longitude !== null
          ? `https://www.google.com/maps/search/?api=1&query=${b.latitude},${b.longitude}`
          : line ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(line)}` : null;
        return (
          <div key={b.id} className={cn(CARD, "gap-2 p-0", selected === b.id && SELECTED)}>
            <button type="button" data-testid="pick-branch" onClick={() => onSelect(b)} className="flex flex-col gap-2 rounded-2xl p-4 text-left focus-visible:outline-2 focus-visible:outline-primary" aria-pressed={selected === b.id}>
              <SelectedMark on={selected === b.id} />
              <span className="flex items-center gap-2 pr-6 font-semibold"><MapPin className="size-4 text-primary" aria-hidden />{b.name}</span>
              <span className="text-sm text-muted-foreground">{line || "Address shared after booking"}</span>
              {b.phone ? <span className="flex items-center gap-1.5 text-sm text-muted-foreground"><Phone className="size-3.5" aria-hidden />{b.phone}</span> : null}
            </button>
            {maps ? <a href={maps} target="_blank" rel="noopener noreferrer" className="mx-4 mb-4 inline-flex w-fit items-center gap-1 text-xs font-medium text-primary hover:underline">Directions <ExternalLink className="size-3" aria-hidden /></a> : null}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- professionals
const AVATAR = { xs: "size-5 text-[9px] ring-0", md: "size-14 text-lg", lg: "size-20 text-2xl" } as const;

export function DoctorAvatar({ pro, size = "md" }: { pro: Pick<Professional, "display_name" | "profile_photo_url">; size?: keyof typeof AVATAR }) {
  return (
    <span className={cn("grid shrink-0 place-items-center overflow-hidden rounded-full bg-accent font-semibold text-accent-foreground ring-2 ring-background", AVATAR[size])}>
      {pro.profile_photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(pro.profile_photo_url)} alt="" className="h-full w-full object-cover" />
      ) : initials(pro.display_name)}
    </span>
  );
}

function DoctorFacts({ pro }: { pro: Professional }) {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {pro.experience_years ? <li className="flex items-center gap-1"><Award className="size-3.5" aria-hidden />{pro.experience_years}+ yrs experience</li> : null}
      {pro.languages?.length ? <li className="flex items-center gap-1"><Languages className="size-3.5" aria-hidden />{pro.languages.join(", ")}</li> : null}
      {pro.consultation_modes?.includes("online") ? <li className="flex items-center gap-1"><Video className="size-3.5" aria-hidden />Video consults</li> : null}
    </ul>
  );
}

export function DoctorStep({ professionals, allowAny, selected, onSelect }: {
  professionals: Professional[]; allowAny: boolean; selected: string | null; onSelect: (id: string) => void;
}) {
  const [profile, setProfile] = useState<Professional | null>(null);
  if (professionals.length === 0) return <EmptyChoice text="No doctor offers this service at this location yet. Please choose another location or service." />;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        {allowAny && professionals.length > 1 ? (
          <button type="button" data-testid="pick-any" onClick={() => onSelect("any")} className={cn(CARD, "flex-row items-center gap-4 border-dashed", selected === "any" && SELECTED)} aria-pressed={selected === "any"}>
            <SelectedMark on={selected === "any"} />
            <span className="grid size-14 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><UsersRound className="size-6" aria-hidden /></span>
            <span><span className="block font-semibold">First available doctor</span><span className="block text-sm text-muted-foreground">See every free time across {professionals.length} doctors</span></span>
          </button>
        ) : null}
        {professionals.map((p) => (
          <div key={p.id} className={cn(CARD, "gap-3", selected === p.id && SELECTED)}>
            <SelectedMark on={selected === p.id} />
            <button type="button" data-testid="pick-professional" onClick={() => onSelect(p.id)} className="flex items-start gap-4 rounded-xl text-left focus-visible:outline-2 focus-visible:outline-primary" aria-pressed={selected === p.id}>
              <DoctorAvatar pro={p} />
              <span className="min-w-0 space-y-1 pr-6">
                <span className="block font-semibold leading-snug">{p.display_name}</span>
                {p.specialization || p.title ? <span className="block text-sm text-primary">{p.specialization ?? p.title}</span> : null}
                {p.qualification ? <span className="block text-sm text-muted-foreground">{p.qualification}</span> : null}
              </span>
            </button>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <DoctorFacts pro={p} />
              {p.biography || p.registration_number ? (
                <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setProfile(p)}>View profile</Button>
              ) : null}
            </div>
          </div>
        ))}
      </div>
      <Dialog open={profile !== null} onOpenChange={(open) => { if (!open) setProfile(null); }}>
        {profile ? (
          <DialogContent>
            <DialogHeader>
              <div className="flex items-center gap-4">
                <DoctorAvatar pro={profile} size="lg" />
                <div>
                  <DialogTitle>{profile.display_name}</DialogTitle>
                  <DialogDescription>{[profile.specialization ?? profile.title, profile.qualification].filter(Boolean).join(" · ")}</DialogDescription>
                </div>
              </div>
            </DialogHeader>
            <div className="space-y-3 text-sm">
              <DoctorFacts pro={profile} />
              {profile.biography ? <p className="whitespace-pre-line text-muted-foreground">{profile.biography}</p> : null}
              {profile.registration_number ? <p className="text-xs text-muted-foreground">Registration {profile.registration_number}{profile.registration_council ? `, ${profile.registration_council}` : ""}</p> : null}
              <Button className="w-full" onClick={() => { onSelect(profile.id); setProfile(null); }}><Sparkles /> Book with {profile.display_name}</Button>
            </div>
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}

export function EmptyChoice({ text }: { text: string }) {
  return <p className="rounded-2xl border border-dashed bg-background p-8 text-center text-sm text-muted-foreground" role="status">{text}</p>;
}

