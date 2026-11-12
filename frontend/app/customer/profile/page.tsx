"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Smartphone } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { authService } from "@/services/auth";
import { usersService } from "@/services/users";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

export default function ProfilePage() {
  const { user, refresh } = useAuth();
  const queryClient = useQueryClient();
  const [name, setName] = useState(user?.full_name ?? "");
  const [pw, setPw] = useState({ current: "", next: "" });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: authService.sessions });

  const saveName = useMutation({
    mutationFn: () => usersService.updateMe({ full_name: name }),
    onSuccess: async () => { toast.success("Profile saved"); await refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const changePw = useMutation({
    mutationFn: () => authService.changePassword(pw.current || null, pw.next),
    onSuccess: () => { toast.success("Password updated"); setPw({ current: "", next: "" }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => authService.revokeSession(id),
    onSuccess: () => { toast.success("Device signed out"); queryClient.invalidateQueries({ queryKey: ["sessions"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const verifyEmail = useMutation({
    mutationFn: authService.requestEmailVerification,
    onSuccess: (r) => toast.success(r.detail),
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (!user) return null;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Profile & security" description="Your account details, password and signed-in devices." />
      <Card>
        <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); saveName.mutate(); }}>
            <Field label="Full name" htmlFor="full_name" className="flex-1"><Input id="full_name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Button type="submit" disabled={saveName.isPending}>Save</Button>
          </form>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div><dt className="text-muted-foreground">Mobile</dt><dd>{user.mobile ?? "—"} {user.mobile_verified_at ? <Badge variant="success">verified</Badge> : null}</dd></div>
            <div>
              <dt className="text-muted-foreground">Email</dt>
              <dd className="flex items-center gap-2">{user.email ?? "—"} {user.email ? user.email_verified_at ? <Badge variant="success">verified</Badge> : <Button size="sm" variant="link" onClick={() => verifyEmail.mutate()}>Verify</Button> : null}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Password</CardTitle><CardDescription>Leave the current password empty if you signed up with OTP or Google.</CardDescription></CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); changePw.mutate(); }}>
            <Field label="Current password" htmlFor="pw_cur"><Input id="pw_cur" type="password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></Field>
            <Field label="New password" htmlFor="pw_new"><Input id="pw_new" type="password" required minLength={8} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
            <div className="flex items-end"><Button type="submit" disabled={changePw.isPending}>Update</Button></div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Signed-in devices</CardTitle></CardHeader>
        <CardContent>
          <ul className="divide-y">
            {(sessions.data ?? []).map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="flex items-center gap-3">
                  <Smartphone className="size-4 text-muted-foreground" />
                  <div>
                    <p className="font-medium">{s.device_label ?? "Browser"} {s.is_current ? <Badge variant="secondary" className="ml-1">this device</Badge> : null}</p>
                    <p className="text-xs text-muted-foreground">{s.ip_address ?? "unknown IP"} · last seen {formatDateTime(s.last_seen_at)}</p>
                  </div>
                </div>
                {!s.is_current ? <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>Sign out</Button> : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
