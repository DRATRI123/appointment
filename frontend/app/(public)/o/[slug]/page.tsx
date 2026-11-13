"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock, MapPin } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { useOrg } from "./org-provider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPaise } from "@/lib/utils";

const DAY_LABEL: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };

export default function OrganizationHome() {
  const { slug, data } = useOrg();
  const { organization: org, branches, categories } = data;
  const [branchId, setBranchId] = useState<string | undefined>(undefined);
  const [categoryId, setCategoryId] = useState<string | undefined>(undefined);
  const services = useQuery({ queryKey: ["public-services", slug, branchId, categoryId], queryFn: () => publicCatalog.services(slug, { branch_id: branchId, category_id: categoryId }) });
  const professionals = useQuery({ queryKey: ["public-pros", slug, branchId], queryFn: () => publicCatalog.professionals(slug, { branch_id: branchId }) });
  const tagline = (data.settings.branding?.tagline as string) || org.description;

  return (
    <div className="space-y-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {tagline ? <p className="max-w-3xl text-lg text-muted-foreground">{tagline}</p> : <span />}
        <Button asChild size="lg" data-testid="book-now"><Link href={`/o/${slug}/book`}>Book an appointment <ArrowRight /></Link></Button>
      </div>

      <section id="branches">
        <h2 className="mb-4 text-xl font-semibold tracking-tight">Locations</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <button onClick={() => setBranchId(undefined)} className={`rounded-xl border p-4 text-left transition-colors ${!branchId ? "border-primary bg-accent/50" : "hover:bg-muted/50"}`}>
            <p className="font-medium">All locations</p><p className="text-sm text-muted-foreground">{branches.length} branch{branches.length === 1 ? "" : "es"}</p>
          </button>
          {branches.map((b) => {
            const a = (b.address ?? {}) as Record<string, string>;
            return (
              <button key={b.id} data-testid="public-branch" onClick={() => setBranchId(b.id)} className={`rounded-xl border p-4 text-left transition-colors ${branchId === b.id ? "border-primary bg-accent/50" : "hover:bg-muted/50"}`}>
                <p className="font-medium">{b.name}</p>
                <p className="flex items-center gap-1 text-sm text-muted-foreground"><MapPin className="size-3.5" />{[a.line1, a.city].filter(Boolean).join(", ") || "Address on request"}</p>
                {b.business_hours ? <p className="mt-1 text-xs text-muted-foreground">Open {Object.keys(b.business_hours).map((d) => DAY_LABEL[d]).join(", ")}</p> : null}
              </button>
            );
          })}
        </div>
      </section>

      <section id="services">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold tracking-tight">Services</h2>
          {categories.length ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant={!categoryId ? "default" : "outline"} className="cursor-pointer" onClick={() => setCategoryId(undefined)}>All</Badge>
              {categories.map((c) => <Badge key={c.id} variant={categoryId === c.id ? "default" : "outline"} className="cursor-pointer" onClick={() => setCategoryId(c.id)}>{c.name}</Badge>)}
            </div>
          ) : null}
        </div>
        {services.isLoading ? <Skeleton className="h-40" /> : services.data?.length === 0 ? <p className="text-sm text-muted-foreground">No services available for this selection.</p> : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {services.data?.map((s) => {
              const price = branchId ? s.pricing.find((p) => p.branch_id === branchId)?.price_paise ?? s.price_paise : s.price_paise;
              const shown = s.discounted_price_paise ?? price;
              return (
                <Card key={s.id} data-testid="public-service" className="gap-3 py-5 transition-shadow hover:shadow-md">
                  {s.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={mediaUrl(s.image_url)} alt="" className="mx-6 h-32 rounded-lg object-cover" />
                  ) : null}
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2"><CardTitle>{s.name}</CardTitle>{s.category_name ? <Badge variant="secondary">{s.category_name}</Badge> : null}</div>
                    <CardDescription>{s.short_description ?? s.description?.slice(0, 120)}</CardDescription>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between">
                    <div className="text-sm"><span className="flex items-center gap-1 text-muted-foreground"><Clock className="size-3.5" />{s.duration_minutes} min</span><span className="font-semibold">{s.payment_mode === "free" ? "Free" : formatPaise(shown)}</span></div>
                    <Button asChild size="sm" variant="outline"><Link href={`/o/${slug}/services/${s.id}`}>Details <ArrowRight /></Link></Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <section id="professionals">
        <h2 className="mb-4 text-xl font-semibold tracking-tight">Professionals</h2>
        {professionals.isLoading ? <Skeleton className="h-40" /> : professionals.data?.length === 0 ? <p className="text-sm text-muted-foreground">No professionals listed yet.</p> : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {professionals.data?.map((p) => (
              <Link key={p.id} href={`/o/${slug}/professionals/${p.id}`} data-testid="public-professional" className="flex gap-4 rounded-xl border p-4 transition-shadow hover:shadow-md">
                <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-full bg-accent text-lg font-semibold text-accent-foreground">
                  {p.profile_photo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={mediaUrl(p.profile_photo_url)} alt="" className="h-full w-full object-cover" />
                  ) : p.display_name.split(" ").filter((x) => !x.endsWith(".")).slice(0, 2).map((x) => x[0]).join("")}
                </div>
                <div className="min-w-0">
                  <p className="font-semibold">{p.display_name}</p>
                  <p className="text-sm text-muted-foreground">{[p.specialization, p.qualification].filter(Boolean).join(" · ")}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{p.experience_years ? `${p.experience_years} yrs experience · ` : ""}{p.default_fee_paise !== null ? `from ${formatPaise(p.default_fee_paise)}` : ""}</p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
