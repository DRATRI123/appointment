"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock, IndianRupee, Video } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { useOrg } from "../../org-provider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPaise } from "@/lib/utils";
import { titleCase } from "@/lib/format";

export default function ServiceDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { slug, data } = useOrg();
  const service = useQuery({ queryKey: ["public-service", slug, id], queryFn: () => publicCatalog.service(slug, id) });
  const pros = useQuery({ queryKey: ["public-pros-for", slug, id], queryFn: () => publicCatalog.professionals(slug, { service_id: id }) });
  if (service.isLoading) return <Skeleton className="h-64" />;
  if (!service.data) return <p>Service not found.</p>;
  const s = service.data;
  const advance = s.payment_mode === "partial_advance" ? (s.advance_amount_paise ?? Math.round(((s.discounted_price_paise ?? s.price_paise) * (s.advance_percent ?? 0)) / 100)) : null;
  return (
    <div className="space-y-8">
      <Link href={`/o/${slug}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Back to {data.organization.name}</Link>
      <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          {s.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mediaUrl(s.image_url)} alt="" className="h-64 w-full rounded-2xl object-cover" />
          ) : null}
          <div>
            <div className="flex flex-wrap items-center gap-2">{s.category_name ? <Badge variant="secondary">{s.category_name}</Badge> : null}{s.consultation_mode !== "in_person" ? <Badge variant="outline"><Video className="size-3" /> {s.consultation_mode === "online" ? "Online" : "Online or in person"}</Badge> : null}</div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">{s.name}</h1>
            {s.short_description ? <p className="mt-1 text-muted-foreground">{s.short_description}</p> : null}
          </div>
          {s.description ? <p className="whitespace-pre-line text-sm leading-relaxed">{s.description}</p> : null}
          {s.instructions ? <Card><CardHeader><CardTitle className="text-base">Before your visit</CardTitle></CardHeader><CardContent className="whitespace-pre-line text-sm">{s.instructions}</CardContent></Card> : null}
          <div>
            <h2 className="mb-3 text-lg font-semibold">Professionals offering this service</h2>
            {pros.isLoading ? <Skeleton className="h-20" /> : pros.data?.length === 0 ? <p className="text-sm text-muted-foreground">Any available professional.</p> : (
              <div className="grid gap-3 sm:grid-cols-2">{pros.data?.map((p) => <Link key={p.id} href={`/o/${slug}/professionals/${p.id}`} className="rounded-lg border p-3 text-sm hover:bg-muted/50"><p className="font-medium">{p.display_name}</p><p className="text-muted-foreground">{p.specialization}</p></Link>)}</div>
            )}
          </div>
        </div>
        <Card className="h-fit lg:sticky lg:top-24">
          <CardHeader><CardTitle>Book this service</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-muted-foreground"><Clock className="size-4" /> Duration</span><span>{s.duration_minutes} min</span></div>
            <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-muted-foreground"><IndianRupee className="size-4" /> Price</span><span className="font-semibold">{s.payment_mode === "free" ? "Free" : <>{s.discounted_price_paise !== null ? <span className="mr-1 text-muted-foreground line-through">{formatPaise(s.price_paise)}</span> : null}{formatPaise(s.discounted_price_paise ?? s.price_paise)}</>}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted-foreground">Payment</span><span>{titleCase(s.payment_mode)}{advance !== null ? ` · ${formatPaise(advance)} now` : ""}</span></div>
            {s.pricing.some((p) => p.price_paise !== null) ? <ul className="rounded-lg bg-muted/50 p-3 text-xs">{s.pricing.filter((p) => p.is_available).map((p) => <li key={p.branch_id} className="flex justify-between"><span>{p.branch_name}</span><span>{p.price_paise !== null ? formatPaise(p.price_paise) : formatPaise(s.price_paise)}</span></li>)}</ul> : null}
            <Button asChild size="lg" className="w-full"><Link href={`/o/${slug}/book?service=${s.id}`}>Choose date &amp; time</Link></Button>
            <p className="text-xs text-muted-foreground">Payment goes directly to {data.organization.name}&apos;s UPI account and is confirmed by their team.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
