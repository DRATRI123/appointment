"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Database, Loader2, PlugZap, RotateCcw, XCircle } from "lucide-react";
import { platformService, type DatabaseConfirm, type DatabaseOverview, type PostgresTarget } from "@/services/platform";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";

function mb(bytes?: number) {
  return bytes === undefined ? "" : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Your own password (and authenticator code if you use one), asked before anything changes. */
function ConfirmFields({ value, onChange, needsCode, id }: { value: DatabaseConfirm; onChange: (v: DatabaseConfirm) => void; needsCode: boolean; id: string }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Your password (to confirm it is you)" htmlFor={`${id}-pw`}>
        <Input id={`${id}-pw`} type="password" autoComplete="current-password" value={value.confirm_password} onChange={(e) => onChange({ ...value, confirm_password: e.target.value })} />
      </Field>
      {needsCode ? (
        <Field label="Code from your authenticator app" htmlFor={`${id}-code`}>
          <Input id={`${id}-code`} inputMode="numeric" autoComplete="one-time-code" maxLength={12} value={value.mfa_code ?? ""} onChange={(e) => onChange({ ...value, mfa_code: e.target.value })} />
        </Field>
      ) : null}
    </div>
  );
}

function TaskPanel({ info }: { info: DatabaseOverview }) {
  const t = info.task;
  if (!t || t.state === "undone") return null;
  const running = t.state === "running";
  return (
    <Card data-testid="database-task">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {running ? <Loader2 className="size-4 animate-spin" aria-hidden /> : t.state === "done" ? <CheckCircle2 className="size-4 text-success-ink" aria-hidden /> : <XCircle className="size-4 text-destructive-ink" aria-hidden />}
          {t.kind === "move" ? "Moving to PostgreSQL" : "Database updates"}: {running ? "working… (keep this page open)" : t.state === "done" ? "finished" : "stopped"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ol className="space-y-1 font-mono text-xs">{t.log.map((line, i) => <li key={i}>{line}</li>)}</ol>
        {t.error ? <Alert variant="destructive"><AlertTitle>It stopped</AlertTitle><AlertDescription>{t.error} Nothing was switched; the app keeps using the current database.</AlertDescription></Alert> : null}
      </CardContent>
    </Card>
  );
}

export default function DatabasePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const overview = useQuery({
    queryKey: ["platform-database"], queryFn: platformService.database,
    refetchInterval: (q) => (q.state.data?.task?.state === "running" ? 1500 : false),
  });
  const [target, setTarget] = useState<PostgresTarget>({ host: "localhost", port: 5432, database: "appointments", user: "postgres", password: "" });
  const [test, setTest] = useState<{ ok: boolean; exists?: boolean; message: string } | null>(null);
  const [confirm, setConfirm] = useState<DatabaseConfirm>({ confirm_password: "" });
  const [understood, setUnderstood] = useState(false);
  const needsCode = !!user?.mfa_enabled_at;
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["platform-database"] });
  const set = (patch: Partial<PostgresTarget>) => { setTarget({ ...target, ...patch }); setTest(null); };

  const testIt = useMutation({ mutationFn: () => platformService.databaseTest(target), onSuccess: setTest, onError: (e) => toast.error(errorMessage(e)) });
  const createIt = useMutation({ mutationFn: () => platformService.databaseCreate(target), onSuccess: (r) => { setTest(r); toast.success("Database created"); }, onError: (e) => toast.error(errorMessage(e)) });
  const updates = useMutation({ mutationFn: () => platformService.databaseUpdates(confirm), onSuccess: () => { setConfirm({ confirm_password: "" }); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const move = useMutation({ mutationFn: () => platformService.databaseMove(target, confirm), onSuccess: () => { setConfirm({ confirm_password: "" }); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const undo = useMutation({ mutationFn: () => platformService.databaseUndo(confirm), onSuccess: () => { setConfirm({ confirm_password: "" }); toast.success("Back on SQLite. Saving resumed."); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });

  const info = overview.data;
  if (overview.isLoading || !info) return <div className="mx-auto max-w-4xl"><Skeleton className="h-96" /></div>;
  const running = info.task?.state === "running";
  const switched = info.task?.kind === "move" && info.task.state === "done" && info.engine === "sqlite";

  return (
    <div className="mx-auto max-w-4xl space-y-6" data-testid="database-page">
      <PageHeader title="Database" description="See which database the app uses, apply updates, and move to PostgreSQL. No commands needed." />

      {/* Current database */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><Database className="size-4" aria-hidden /> Current database</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={info.engine === "postgresql" ? "success" : "secondary"} data-testid="database-engine">{info.engine === "postgresql" ? "PostgreSQL" : info.engine === "sqlite" ? "SQLite" : info.engine}</Badge>
            <span className="font-mono text-xs break-all text-muted-foreground">{info.location}{info.size_bytes ? ` · ${mb(info.size_bytes)}` : ""}</span>
            {info.saving_paused ? <Badge variant="warning">Saving paused</Badge> : null}
          </div>
          {info.engine === "sqlite" ? (
            <p className="text-sm text-muted-foreground">SQLite is a single file on this computer: good for one clinic and testing. For going live with many users, move to PostgreSQL below.</p>
          ) : null}
          {info.pending_updates.length ? (
            <div className="space-y-3 rounded-xl border p-4">
              <p className="font-medium">{info.pending_updates.length} database update{info.pending_updates.length === 1 ? "" : "s"} waiting</p>
              <ul className="list-disc pl-5 text-sm text-muted-foreground">{info.pending_updates.map((u) => <li key={u}>{u}</li>)}</ul>
              <ConfirmFields id="upd" value={confirm} onChange={setConfirm} needsCode={needsCode} />
              <Button onClick={() => updates.mutate()} disabled={running || updates.isPending || !confirm.confirm_password} data-testid="apply-updates">Apply updates</Button>
            </div>
          ) : (
            <p className="flex items-center gap-2 text-sm"><CheckCircle2 className="size-4 text-success-ink" aria-hidden /> Database is up to date.</p>
          )}
        </CardContent>
      </Card>

      {/* After a move: restart */}
      {switched ? (
        <Alert variant="success" data-testid="restart-now">
          <CheckCircle2 className="size-4" aria-hidden />
          <AlertTitle>Copied and checked. Now restart the app.</AlertTitle>
          <AlertDescription className="space-y-3">
            {info.task?.switched ? (
              <ol className="list-decimal space-y-1 pl-5">
                <li>Close the 3 black windows of the app.</li>
                <li>Double-click <strong>START-APP.bat</strong> again.</li>
                <li>Come back here: it should say <strong>PostgreSQL</strong>.</li>
              </ol>
            ) : (
              <p>This server sets its database address outside <code>backend/.env</code>. Change <code>DATABASE_URL</code> there to {info.task?.target}, then restart.</p>
            )}
            <p className="text-xs">Until the restart, saving stays paused so nothing is written to the old database. The old SQLite file and a snapshot are kept as a backup.</p>
            <div className="space-y-2 border-t pt-3">
              <p className="text-xs">Changed your mind? Keep using SQLite instead:</p>
              <ConfirmFields id="undo" value={confirm} onChange={setConfirm} needsCode={needsCode} />
              <Button variant="outline" size="sm" onClick={() => undo.mutate()} disabled={undo.isPending || !confirm.confirm_password}><RotateCcw /> Undo, keep SQLite</Button>
            </div>
          </AlertDescription>
        </Alert>
      ) : null}

      <TaskPanel info={info} />

      {/* Move to PostgreSQL */}
      {info.engine === "sqlite" && !switched ? (
        <Card data-testid="move-card">
          <CardHeader>
            <CardTitle className="text-base">Move to PostgreSQL</CardTitle>
            <CardDescription>Copies everything (clinics, patients, bookings, payments) into PostgreSQL, checks every table matches exactly, then switches the app to it. If anything goes wrong, nothing changes.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <section className="space-y-3">
              <p className="font-medium">1. Your PostgreSQL details</p>
              <p className="text-sm text-muted-foreground">Install PostgreSQL 16 on this computer (postgresql.org, Windows installer) or use a hosted one. Use the password you chose when installing.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Server" htmlFor="pg-host" hint="localhost if PostgreSQL is on this computer"><Input id="pg-host" value={target.host} onChange={(e) => set({ host: e.target.value })} /></Field>
                <Field label="Port" htmlFor="pg-port" hint="Usually 5432"><Input id="pg-port" inputMode="numeric" value={target.port} onChange={(e) => set({ port: Number(e.target.value.replace(/\D/g, "")) || 0 })} /></Field>
                <Field label="Database name" htmlFor="pg-db" hint="A new, empty database"><Input id="pg-db" value={target.database} onChange={(e) => set({ database: e.target.value })} /></Field>
                <Field label="User" htmlFor="pg-user"><Input id="pg-user" value={target.user} onChange={(e) => set({ user: e.target.value })} /></Field>
                <Field label="PostgreSQL password" htmlFor="pg-pw"><Input id="pg-pw" type="password" autoComplete="off" value={target.password} onChange={(e) => set({ password: e.target.value })} /></Field>
              </div>
            </section>

            <section className="space-y-3">
              <p className="font-medium">2. Test the connection</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => testIt.mutate()} disabled={testIt.isPending || running} data-testid="test-connection"><PlugZap /> Test connection</Button>
                {test && !test.ok && test.exists === false ? (
                  <Button variant="outline" onClick={() => createIt.mutate()} disabled={createIt.isPending} data-testid="create-database">Create the database</Button>
                ) : null}
              </div>
              {test ? (
                <Alert variant={test.ok ? "success" : "destructive"} data-testid="test-result">
                  {test.ok ? <CheckCircle2 className="size-4" aria-hidden /> : <AlertTriangle className="size-4" aria-hidden />}
                  <AlertDescription>{test.message}</AlertDescription>
                </Alert>
              ) : null}
            </section>

            <section className="space-y-3">
              <p className="font-medium">3. Copy and switch</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                <li>Best done when the clinic is closed. Saving is paused while copying (usually under a few minutes); patients see “back in a few minutes”.</li>
                <li>A snapshot of the current database is kept as a backup. Uploaded photos and files stay where they are.</li>
                <li>Afterwards you restart the app once with START-APP.bat. You may need to sign in again.</li>
              </ul>
              <label className="flex items-start gap-2 text-sm">
                <Checkbox checked={understood} onCheckedChange={(v) => setUnderstood(v === true)} aria-label="I understand" className="mt-0.5" />
                <span>I understand saving pauses for a few minutes and I will restart the app afterwards.</span>
              </label>
              <ConfirmFields id="move" value={confirm} onChange={setConfirm} needsCode={needsCode} />
              <Button onClick={() => move.mutate()} disabled={!test?.ok || !understood || !confirm.confirm_password || move.isPending || running} data-testid="start-move">
                {move.isPending || running ? <Loader2 className="animate-spin" /> : null} Copy to PostgreSQL and switch
              </Button>
              {!test?.ok ? <p className="text-xs text-muted-foreground">Test the connection first.</p> : null}
            </section>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
