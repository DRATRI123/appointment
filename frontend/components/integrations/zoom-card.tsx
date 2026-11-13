"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Video } from "lucide-react";
import { integrationsService } from "@/services/integrations";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import type { Integration } from "@/types/integration";

export function ZoomCard({ zoom }: { zoom: Integration | null }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["integrations"] });
  const fail = (e: unknown) => toast.error(errorMessage(e));
  const [form, setForm] = useState({ account_id: "", client_id: "", client_secret: "", default_user: "" });
  const [editing, setEditing] = useState(!zoom || zoom.status === "disconnected");
  const connect = useMutation({ mutationFn: () => integrationsService.connectZoom({ ...form, default_user: form.default_user || undefined }), onSuccess: () => { toast.success("Zoom connected"); setForm({ account_id: "", client_id: "", client_secret: "", default_user: "" }); setEditing(false); refresh(); }, onError: fail });
  const test = useMutation({ mutationFn: () => integrationsService.test(zoom!.id), onSuccess: (r) => { if (r.last_error) toast.error(r.last_error); else toast.success("Zoom connection works"); refresh(); }, onError: fail });
  const toggle = useMutation({ mutationFn: (v: boolean) => integrationsService.update(zoom!.id, { is_enabled: v }), onSuccess: refresh, onError: fail });
  const disconnect = useMutation({ mutationFn: () => integrationsService.disconnect(zoom!.id), onSuccess: () => { toast.success("Zoom disconnected"); setEditing(true); refresh(); }, onError: fail });
  const live = zoom && zoom.status !== "disconnected";
  return (
    <Card data-testid="zoom-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Video className="size-4" /> Zoom {live ? (zoom.status === "error" ? <Badge variant="destructive">Needs attention</Badge> : zoom.is_enabled ? <Badge variant="success">Connected</Badge> : <Badge variant="outline">Paused</Badge>) : null}</CardTitle>
        <CardDescription>One Zoom account for the clinic creates a meeting for each online consultation. Uses a Zoom Server-to-Server OAuth app.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {live && !editing ? (
          <>
            <p className="text-sm">Account: <span className="font-medium">{zoom.account}</span> · default host: <span className="font-mono text-xs">{zoom.config.default_user ?? "me"}</span></p>
            {zoom.last_error ? <Alert variant="destructive"><AlertDescription>{zoom.last_error}</AlertDescription></Alert> : null}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>Test</Button>
              <Button size="sm" variant="outline" onClick={() => toggle.mutate(!zoom.is_enabled)}>{zoom.is_enabled ? "Pause" : "Resume"}</Button>
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>Replace credentials</Button>
              <Button size="sm" variant="ghost" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>Disconnect</Button>
            </div>
          </>
        ) : (
          <form className="grid gap-3 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); connect.mutate(); }}>
            <Field label="Account ID" htmlFor="z_acct"><Input id="z_acct" autoComplete="off" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} /></Field>
            <Field label="Client ID" htmlFor="z_cid"><Input id="z_cid" autoComplete="off" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} /></Field>
            <Field label="Client secret" htmlFor="z_sec" hint="Stored encrypted; never shown again"><Input id="z_sec" type="password" autoComplete="new-password" value={form.client_secret} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} /></Field>
            <Field label="Default host email (optional)" htmlFor="z_user" hint="Zoom user who hosts meetings; empty = the account owner"><Input id="z_user" type="email" value={form.default_user} onChange={(e) => setForm({ ...form, default_user: e.target.value })} /></Field>
            <p className="text-xs text-muted-foreground md:col-span-2">In the Zoom App Marketplace create a Server-to-Server OAuth app with the scopes <span className="font-mono">meeting:write:meeting:admin</span> and <span className="font-mono">user:read:user:admin</span>, activate it, then paste its credentials here. They are checked with Zoom before saving.</p>
            <div className="flex gap-2 md:col-span-2">
              <Button type="submit" disabled={connect.isPending || !form.account_id || !form.client_id || !form.client_secret} data-testid="connect-zoom">{connect.isPending ? "Checking…" : "Connect Zoom"}</Button>
              {live ? <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button> : null}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
