"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Award, Languages, MapPin } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { useOrg } from "../../org-provider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPaise } from "@/lib/utils";

export default function ProfessionalProfile({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { slug, data } = useOrg();
  const pro = useQuery({ queryKey: ["public-pro", slug, id], queryFn: () => publicCatalog.professional(slug, id) });
  const services = useQuery({ queryKey: ["public-services-for", slug, id], queryFn: () => publicCatalog.services(slug).then((all) => all.filter((s) => s.professional_ids.includes(id))) });
  if (pro.isLoading) return <Skeleton className="h-64" />;
  if (!pro.data) return <p>Professional not found.</p>;
  const p = pro.data;
  return (
    <div className="space-y-8">
      <Link href={`/o/${slug}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Back to {data.organization.name}</Link>
      <div className="flex flex-col gap-6 md:flex-row">
        <div className="grid size-32 shrink-0 place-items-center overflow-hidden rounded-2xl bg-accent text-3xl font-semibold text-accent-foreground">
          {p.profile_photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mediaUrl(p.profile_photo_url)} alt="" className="h-full w-full object-cover" />
          ) : p.display_name[0]}
        </div>
        <div className="flex-1 space-y-3">
          <div><h1 className="text-3xl font-semibold tracking-tight">{p.display_name}</h1><p className="text-muted-foreground">{[p.specialization, p.qualification].filter(Boolean).join(" · ")}</p></div>
          <div className="flex flex-wrap gap-2 text-sm">
            {p.experience_years ? <Badge variant="secondary"><Award className="size-3" /> {p.experience_years} years</Badge> : null}
            {p.languages?.length ? <Badge variant="secondary"><Languages className="size-3" /> {p.languages.join(", ")}</Badge> : null}
            {p.registration_number ? <Badge variant="outline">Reg. {p.registration_number}</Badge> : null}
          </div>
          {p.biography ? <p className="max-w-2xl whitespace-pre-line text-sm leading-relaxed">{p.biography}</p> : null}
          <Button asChild size="lg"><Link href={`/o/${slug}/book?professional=${p.id}`}>Book an appointment</Link></Button>
        </div>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><MapPin className="size-4" /> Available at</CardTitle></CardHeader>
          <CardContent><ul className="space-y-2 text-sm">{p.branches.filter((b) => b.is_active).map((b) => <li key={b.branch_id} className="flex justify-between"><span>{b.branch_name}</span><span className="text-muted-foreground">{b.fee_paise !== null ? formatPaise(b.fee_paise) : p.default_fee_paise !== null ? formatPaise(p.default_fee_paise) : ""}</span></li>)}</ul></CardContent></Card>
        <Card><CardHeader><CardTitle>Services</CardTitle></CardHeader>
          <CardContent>{services.isLoading ? <Skeleton className="h-20" /> : <ul className="space-y-2 text-sm">{services.data?.map((s) => <li key={s.id} className="flex justify-between"><Link href={`/o/${slug}/services/${s.id}`} className="hover:underline">{s.name}</Link><span className="text-muted-foreground">{s.duration_minutes} min · {formatPaise(s.discounted_price_paise ?? s.price_paise)}</span></li>)}{services.data?.length === 0 ? <li className="text-muted-foreground">No online-bookable services listed.</li> : null}</ul>}</CardContent></Card>
      </div>
    </div>
  );
}
