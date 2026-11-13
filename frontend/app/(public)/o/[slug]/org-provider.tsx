"use client";

import { createContext, useContext } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Building2, MapPin, Phone } from "lucide-react";
import { publicCatalog, mediaUrl } from "@/services/catalog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import type { PublicOrganization } from "@/types/catalog";

const OrgContext = createContext<{ slug: string; data: PublicOrganization } | null>(null);

export function useOrg() {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrg outside provider");
  return ctx;
}

export function OrgProvider({ slug, children }: { slug: string; children: React.ReactNode }) {
  const query = useQuery({ queryKey: ["public-org", slug], queryFn: () => publicCatalog.organization(slug), retry: false });
  if (query.isLoading) return <div className="mx-auto max-w-6xl space-y-4 px-4 py-12"><Skeleton className="h-10 w-72" /><Skeleton className="h-48" /></div>;
  if (query.isError || !query.data) {
    return <div className="mx-auto max-w-2xl px-4 py-20"><EmptyState icon={Building2} title="Organization not found" body="This booking page does not exist or is not active." /></div>;
  }
  const { organization: org, branches } = query.data;
  const primary = branches[0];
  const address = (primary?.address ?? {}) as Record<string, string>;
  return (
    <OrgContext.Provider value={{ slug, data: query.data }}>
      <div className="border-b bg-sidebar">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-6">
          <div className="grid size-14 place-items-center overflow-hidden rounded-xl bg-primary/10 text-xl font-semibold text-primary">
            {org.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={mediaUrl(org.logo_url)} alt="" className="h-full w-full object-cover" />
            ) : org.name[0]}
          </div>
          <div className="min-w-0 flex-1">
            <Link href={`/o/${slug}`} className="text-2xl font-semibold tracking-tight hover:underline">{org.name}</Link>
            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              {org.business_type ? <span>{org.business_type.replace(/_/g, " ")}</span> : null}
              {address.city ? <span className="flex items-center gap-1"><MapPin className="size-3.5" />{address.city}</span> : null}
              {org.phone ? <span className="flex items-center gap-1"><Phone className="size-3.5" />{org.phone}</span> : null}
            </p>
          </div>
          <nav className="flex w-full gap-4 text-sm sm:w-auto">
            <Link href={`/o/${slug}`} className="hover:text-primary">Overview</Link>
            <Link href={`/o/${slug}#services`} className="hover:text-primary">Services</Link>
            <Link href={`/o/${slug}#professionals`} className="hover:text-primary">Professionals</Link>
          </nav>
        </div>
      </div>
      <div className="mx-auto max-w-6xl px-4 py-8">{children}</div>
    </OrgContext.Provider>
  );
}
