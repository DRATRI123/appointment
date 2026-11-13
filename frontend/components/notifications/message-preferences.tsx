"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { preferencesService } from "@/services/notifications";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/errors";
import type { MessagePreferences as Prefs } from "@/types/notification";

type Key = "email" | "sms" | "whatsapp" | "reminders";
const LABELS: [Key, string, string][] = [
  ["email", "Email", "Booking, payment and refund updates"],
  ["sms", "SMS", "Short updates to your mobile"],
  ["whatsapp", "WhatsApp", "Updates on WhatsApp (you can stop any time)"],
  ["reminders", "Appointment reminders", "Before each confirmed appointment"],
];

export function MessagePreferences() {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["message-preferences"], queryFn: preferencesService.list });
  const update = useMutation({
    mutationFn: ({ org, patch }: { org: string; patch: Partial<Record<Key, boolean>> }) => preferencesService.update(org, patch),
    onSuccess: (saved) => { queryClient.setQueryData<Prefs[]>(["message-preferences"], (rows) => rows?.map((r) => (r.organization_id === saved.organization_id ? saved : r))); toast.success("Preferences saved"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!prefs.data?.length) return null;
  return (
    <Card data-testid="message-preferences">
      <CardHeader><CardTitle>Messages from clinics</CardTitle><CardDescription>Choose how each clinic may contact you about your appointments.</CardDescription></CardHeader>
      <CardContent className="space-y-6">
        {prefs.data.map((p) => (
          <div key={p.organization_id} className="space-y-2">
            {prefs.data.length > 1 ? <p className="font-medium">{p.organization_name}</p> : null}
            <div className="divide-y rounded-lg border">
              {LABELS.filter(([k]) => k !== "whatsapp" || p.whatsapp_available || p.whatsapp).map(([k, label, hint]) => (
                <label key={k} className="flex items-center justify-between gap-4 px-3 py-2.5">
                  <span><span className="block text-sm font-medium">{label}</span><span className="text-xs text-muted-foreground">{hint}</span></span>
                  <Switch checked={p[k]} disabled={update.isPending} onCheckedChange={(v) => update.mutate({ org: p.organization_id, patch: { [k]: v } })} aria-label={`${label} from ${p.organization_name}`} />
                </label>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
