"use client";

import { Activity, Database, ServerCrash } from "lucide-react";
import { useSystemStatus } from "@/hooks/use-system-status";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBase } from "@/lib/env";

export function SystemStatus() {
  const { data, isLoading, isError, error } = useSystemStatus();

  return (
    <Card data-testid="system-status">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Activity className="size-4 text-primary" /> API connection
          </CardTitle>
          {isLoading ? (
            <Badge variant="outline">Checking…</Badge>
          ) : isError ? (
            <Badge variant="destructive">Offline</Badge>
          ) : data?.status === "ok" ? (
            <Badge variant="success">Healthy</Badge>
          ) : (
            <Badge variant="warning">Degraded</Badge>
          )}
        </div>
        <CardDescription className="font-mono text-xs">{apiBase || "/api/v1"} (proxied to FastAPI)</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {isError ? (
          <p className="flex items-start gap-2 text-destructive">
            <ServerCrash className="mt-0.5 size-4" />
            <span>
              Could not reach the backend. Start it with <code className="rounded bg-muted px-1">uvicorn app.main:app --reload</code>.
              <span className="block text-xs text-muted-foreground">{(error as Error)?.message}</span>
            </span>
          </p>
        ) : data ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
            <dt className="text-muted-foreground">Version</dt>
            <dd className="font-mono">{data.version}</dd>
            <dt className="text-muted-foreground">Environment</dt>
            <dd>{data.environment}</dd>
            <dt className="flex items-center gap-1 text-muted-foreground">
              <Database className="size-3.5" /> Database
            </dt>
            <dd>
              {data.database} · {data.checks?.database}
            </dd>
          </dl>
        ) : null}
      </CardContent>
    </Card>
  );
}
