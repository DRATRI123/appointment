"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, CircleAlert, Send } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { notificationsService } from "@/services/notifications";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Field } from "@/components/forms/field";
import { errorMessage } from "@/lib/errors";
import { CHANNEL_LABEL } from "@/types/notification";

const SETUP: Record<string, string> = {
  email: "EMAIL_PROVIDER=smtp with SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM",
  sms: "SMS_PROVIDER=msg91 (MSG91_AUTH_KEY, MSG91_SENDER_ID) or twilio (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SMS_FROM)",
  whatsapp: "WHATSAPP_PROVIDER=meta (WHATSAPP_CLOUD_TOKEN, WHATSAPP_CLOUD_PHONE_NUMBER_ID) or twilio (TWILIO_WHATSAPP_FROM)",
};

export function ProvidersPanel({ orgId }: { orgId: string | null }) {
  const { hasPermission } = useAuth();
  const providers = useQuery({ queryKey: ["notification-providers", orgId], queryFn: notificationsService.providers, enabled: !!orgId });
  const [channel, setChannel] = useState("email");
  const [to, setTo] = useState("");
  const test = useMutation({
    mutationFn: () => notificationsService.test(channel, to),
    onSuccess: (n) => n.status === "sent" ? toast.success(`Test ${CHANNEL_LABEL[n.channel].toLowerCase()} sent`) : toast.error(n.last_error ?? "Not sent"),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-3">
        {providers.isLoading ? <Skeleton className="h-32 md:col-span-3" /> : providers.data?.map((p) => (
          <Card key={p.channel} className="gap-2 py-4" data-testid="provider-card">
            <CardHeader><CardTitle className="flex items-center gap-2 text-base">{p.configured && !p.is_console ? <CheckCircle2 className="size-4 text-success" /> : <CircleAlert className="size-4 text-warning" />}{CHANNEL_LABEL[p.channel]}</CardTitle>
              <CardDescription>{p.error ?? (p.is_console ? "Development mode: messages are written to the server log, not delivered." : p.configured ? `Sending through ${p.provider}` : `${p.provider} is selected but not fully configured`)}</CardDescription></CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              <p>{p.enabled_for_organization ? "On for your organization" : "Off for your organization"}</p>
              {p.is_console || !p.configured ? <p className="break-words">Set up on the server: <span className="font-mono">{SETUP[p.channel]}</span></p> : null}
            </CardContent>
          </Card>
        ))}
      </div>
      {hasPermission("notifications:write") ? (
        <Card>
          <CardHeader><CardTitle>Send a test message</CardTitle><CardDescription>Checks the provider end to end. The attempt appears in the outbox.</CardDescription></CardHeader>
          <CardContent>
            <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); test.mutate(); }}>
              <Field label="Channel" htmlFor="test_channel"><NativeSelect id="test_channel" value={channel} onChange={(e) => setChannel(e.target.value)}>{(["email", "sms", "whatsapp"] as const).map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}</NativeSelect></Field>
              <Field label={channel === "email" ? "Email address" : "Mobile number"} htmlFor="test_to" className="flex-1"><Input id="test_to" value={to} onChange={(e) => setTo(e.target.value)} inputMode={channel === "email" ? "email" : "tel"} /></Field>
              <Button type="submit" disabled={to.trim().length < 5 || test.isPending}><Send /> Send test</Button>
            </form>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
