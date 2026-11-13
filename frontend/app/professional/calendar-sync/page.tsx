"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { integrationsService } from "@/services/integrations";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { GoogleResult } from "@/components/integrations/google-result";
import { ProfessionalCard } from "@/components/integrations/professional-card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";

export default function CalendarSyncPage() {
  const { currentOrganizationId: orgId } = useAuth();
  const overview = useQuery({ queryKey: ["integrations", orgId], queryFn: integrationsService.overview, enabled: !!orgId, retry: false });
  const mine = overview.data?.professionals.filter((p) => p.is_me) ?? [];
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Suspense fallback={null}><GoogleResult /></Suspense>
      <PageHeader title="Calendar & video" description="Put your appointments in your own calendar and choose how online consultations get their video link." />
      {overview.isLoading ? <Skeleton className="h-64" /> : overview.error ? <EmptyState icon={CalendarCheck2} title="Not available" body={errorMessage(overview.error)} /> : mine.length === 0 ? (
        <EmptyState icon={CalendarCheck2} title="No professional profile linked" body="Ask the clinic administrator to link your account to your professional profile." />
      ) : mine.map((p) => (
        <ProfessionalCard key={`${p.professional_id}:${JSON.stringify(p.meeting)}`} row={p} googleConfigured={overview.data!.google_configured} zoomConnected={overview.data!.zoom?.status === "connected"} returnTo="/professional/calendar-sync" />
      ))}
    </div>
  );
}
