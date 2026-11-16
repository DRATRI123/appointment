"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, ArrowRight, Plug, RefreshCcw, Search } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { ProviderMark } from "@/components/integrations-hub/provider-mark";
import { StatusPill } from "@/components/integrations-hub/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { hubService, type HubCard, type HubOverview } from "@/services/integration-hub";

export default function IntegrationHubPage() {
  const { currentOrganizationId: orgId } = useAuth();
  const query = useQuery({ queryKey: ["hub", orgId], queryFn: hubService.overview, enabled: !!orgId });
  const [category, setCategory] = useState<string>("all");
  const [search, setSearch] = useState("");
  const data = query.data;
  const cards = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.cards ?? []).filter((c) => (category === "all" || c.category === category) && (!q || `${c.name} ${c.description}`.toLowerCase().includes(q)));
  }, [data, category, search]);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader title="Integrations" description="Connect Google, email, WhatsApp, SMS, n8n, Shopify, your website, CRM and accounting. Each one can be switched on and off, tested, and has its own history." />
      {query.isLoading ? <Skeleton className="h-96" /> : query.error ? <EmptyState icon={Plug} title="No access" body={errorMessage(query.error)} /> : data ? (
        <>
          <Summary data={data} />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Categories">
              {[{ key: "all", title: "All" }, ...data.categories].filter((c) => c.key === "all" || data.cards.some((x) => x.category === c.key)).map((c) => (
                <button key={c.key} type="button" role="tab" aria-selected={category === c.key} onClick={() => setCategory(c.key)}
                  className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", category === c.key ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent")}>
                  {c.title}
                </button>
              ))}
            </div>
            <div className="relative lg:w-64">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
              <Input className="pl-8" placeholder="Search integrations" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search integrations" />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="hub-cards">
            {cards.map((c) => <IntegrationCard key={c.key} card={c} />)}
            {cards.length === 0 ? <p className="text-sm text-muted-foreground">Nothing matches.</p> : null}
          </div>
          <Activity data={data} />
        </>
      ) : null}
    </div>
  );
}

function Summary({ data }: { data: HubOverview }) {
  const tiles = [["Integrations", data.summary.total, ""], ["Connected or active", data.summary.connected, "text-success-ink"],
    ["Need attention", data.summary.failed, data.summary.failed ? "text-destructive-ink" : ""], ["Not connected yet", data.summary.disconnected, ""]] as const;
  return (
    <div className="grid gap-3 sm:grid-cols-4" data-testid="hub-summary">
      {tiles.map(([label, value, cls]) => (
        <Card key={label}><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className={cn("text-2xl font-semibold tabular-nums", cls)}>{value}</p></CardContent></Card>
      ))}
    </div>
  );
}

function IntegrationCard({ card }: { card: HubCard }) {
  const queryClient = useQueryClient();
  const { hasPermission } = useAuth();
  const toggle = useMutation({
    mutationFn: (v: boolean) => hubService.setEnabled(card.key, v),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hub"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const href = card.builtin ? card.link : `/admin/integrations/${card.key}`;
  const failing = (card.sync.failed ?? 0) + (card.sync.dead ?? 0);
  return (
    <Card className="flex flex-col" data-testid={`hub-card-${card.key}`}>
      <CardHeader className="flex flex-row items-start gap-3 space-y-0 pb-3">
        <ProviderMark provider={card.key} category={card.category} />
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base">{card.name}</CardTitle>
          <div className="mt-1"><StatusPill status={card.status} /></div>
        </div>
        {!card.builtin && card.status !== "not_configured" && card.can_manage && hasPermission("integrations:write") ? (
          <Switch checked={card.enabled} disabled={toggle.isPending} onCheckedChange={(v) => toggle.mutate(v)} aria-label={`${card.enabled ? "Switch off" : "Switch on"} ${card.name}`} />
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <p className="text-sm text-muted-foreground">{card.description}</p>
        {card.account ? <p className="truncate text-xs"><span className="text-muted-foreground">Account:</span> {card.account}</p> : null}
        {card.last_synced_at ? <p className="text-xs text-muted-foreground">Last sync {formatDateTime(card.last_synced_at)}</p> : null}
        {failing ? <p className="flex items-center gap-1 text-xs text-destructive"><AlertTriangle className="size-3.5" aria-hidden /> {failing} record{failing === 1 ? "" : "s"} could not be sent</p> : null}
        {card.status === "error" && card.last_error ? <p className="line-clamp-2 text-xs text-destructive">{card.last_error}</p> : null}
        <div className="mt-auto flex gap-2 pt-1">
          {href ? (
            <Button asChild size="sm" variant={card.status === "not_configured" ? "default" : "outline"}>
              <Link href={href}>{card.builtin ? "Open" : card.status === "not_configured" ? "Set up" : "Configure"} <ArrowRight /></Link>
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function Activity({ data }: { data: HubOverview }) {
  if (!data.recent_errors.length && !data.recent_sync.length) return null;
  const name = (key: string) => data.cards.find((c) => c.key === key)?.name ?? key;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><RefreshCcw className="size-4" aria-hidden /> Recent synchronisation</CardTitle></CardHeader>
        <CardContent>
          {data.recent_sync.length ? (
            <ul className="space-y-1.5 text-sm">{data.recent_sync.map((r) => <li key={r.integration} className="flex justify-between gap-2"><span>{name(r.integration)}</span><span className="text-muted-foreground">{formatDateTime(r.at)}</span></li>)}</ul>
          ) : <p className="text-sm text-muted-foreground">Nothing synced yet.</p>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><AlertTriangle className="size-4" aria-hidden /> Recent errors</CardTitle></CardHeader>
        <CardContent>
          {data.recent_errors.length ? (
            <ul className="space-y-2 text-sm" data-testid="hub-recent-errors">
              {data.recent_errors.map((e, i) => (
                <li key={i}><span className="font-medium">{name(e.integration)}</span> <span className="text-xs text-muted-foreground">{formatDateTime(e.at)} · {e.action}</span><span className="block text-xs text-destructive">{e.error}</span></li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No errors.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
