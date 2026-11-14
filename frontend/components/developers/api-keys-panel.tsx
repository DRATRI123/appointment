"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, Plus } from "lucide-react";
import { developersService } from "@/services/developers";
import { SecretReveal } from "@/components/developers/secret-reveal";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

export function ApiKeysPanel() {
  const queryClient = useQueryClient();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: developersService.keys });
  const scopes = useQuery({ queryKey: ["api-scopes"], queryFn: developersService.scopes });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<string[]>(["appointments:read"]);
  const [expires, setExpires] = useState("");
  const [ips, setIps] = useState("");
  const [limit, setLimit] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["api-keys"] });
  const create = useMutation({
    mutationFn: () => developersService.createKey({ name, scopes: chosen, expires_at: expires ? `${expires}T23:59:59Z` : null,
      allowed_ips: ips.split(/[\s,]+/).filter(Boolean), rate_limit_per_minute: limit ? Number(limit) : null }),
    onSuccess: (k) => { setSecret(k.key); setOpen(false); setName(""); setIps(""); setExpires(""); setLimit(""); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const revoke = useMutation({ mutationFn: (id: string) => developersService.revokeKey(id), onSuccess: () => { toast.success("Key revoked"); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <div className="space-y-4">
      {secret ? <SecretReveal label="Your new API key" value={secret} onDone={() => setSecret(null)} /> : null}
      <div className="flex justify-end">{!open ? <Button onClick={() => setOpen(true)} data-testid="new-api-key"><Plus /> New API key</Button> : null}</div>
      {open ? (
        <Card data-testid="api-key-form">
          <CardHeader><CardTitle className="text-base">New API key</CardTitle><CardDescription>Give each integration its own key with only the scopes it needs. It acts as you, inside this organization.</CardDescription></CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Name" htmlFor="k_name" hint="e.g. Website, CRM sync"><Input id="k_name" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></Field>
                <Field label="Expires (optional)" htmlFor="k_exp"><Input id="k_exp" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} /></Field>
                <Field label="Requests per minute" htmlFor="k_rl" hint="Empty = default (120)"><Input id="k_rl" type="number" min={1} max={1200} value={limit} onChange={(e) => setLimit(e.target.value)} /></Field>
              </div>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">Scopes</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {scopes.data?.map((s) => (
                    <label key={s.code} className={`flex items-start gap-2 rounded-lg border p-2.5 text-sm ${s.you_have_it ? "" : "opacity-50"}`}>
                      <Checkbox checked={chosen.includes(s.code)} disabled={!s.you_have_it} onCheckedChange={(v) => setChosen((c) => (v === true ? [...c, s.code] : c.filter((x) => x !== s.code)))} aria-label={s.code} />
                      <span><span className="font-mono text-xs">{s.code}</span><span className="block text-xs text-muted-foreground">{s.description}{s.you_have_it ? "" : " (you don't have this permission)"}</span></span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">Keys can never record or verify payments, change staff, roles or settings, or manage keys and webhooks.</p>
              </fieldset>
              <Field label="Allowed IP addresses (optional)" htmlFor="k_ips" hint="One address or CIDR range per line. Empty = any address."><Textarea id="k_ips" rows={2} value={ips} onChange={(e) => setIps(e.target.value)} placeholder="203.0.113.10&#10;198.51.100.0/24" className="font-mono text-xs" /></Field>
              <div className="flex gap-2"><Button type="submit" disabled={create.isPending || name.trim().length < 2 || !chosen.length} data-testid="create-api-key">Create key</Button><Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
            </form>
          </CardContent>
        </Card>
      ) : null}
      {keys.isLoading ? <Skeleton className="h-40" /> : !keys.data?.length ? <EmptyState icon={KeyRound} title="No API keys yet" body="Create a key to connect your website, CRM or other systems." /> : (
        <Table className="text-sm" data-testid="api-keys-table">
          <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Key</TableHead><TableHead>Scopes</TableHead><TableHead>Last used</TableHead><TableHead className="text-right">Requests (30 d)</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {keys.data.map((k) => (
              <TableRow key={k.id} className={k.is_active ? "" : "opacity-60"}>
                <TableCell><p className="font-medium">{k.name}</p><p className="text-xs text-muted-foreground">by {k.created_by_name ?? "—"} · {formatDateTime(k.created_at)}{k.expires_at ? ` · expires ${formatDateTime(k.expires_at)}` : ""}{k.allowed_ips.length ? ` · ${k.allowed_ips.length} IP rule(s)` : ""}</p></TableCell>
                <TableCell className="font-mono text-xs">{k.prefix}…{!k.is_active ? <Badge variant="outline" className="ml-2">{k.revoked_at ? "Revoked" : "Expired"}</Badge> : null}</TableCell>
                <TableCell className="max-w-72"><div className="flex flex-wrap gap-1">{k.scopes.map((s) => <Badge key={s} variant="secondary" className="font-mono text-[10px]">{s}</Badge>)}</div></TableCell>
                <TableCell className="text-xs text-muted-foreground">{k.last_used_at ? formatDateTime(k.last_used_at) : "Never"}</TableCell>
                <TableCell className="text-right tabular-nums">{k.requests_30d}</TableCell>
                <TableCell className="text-right">{k.is_active ? <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Revoke "${k.name}"? Integrations using it stop working immediately.`)) revoke.mutate(k.id); }}>Revoke</Button> : null}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
