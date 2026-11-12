"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, KeyRound, ScrollText, Settings, UsersRound } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const next = [
  { href: "/admin/staff", icon: UsersRound, title: "Invite your team", body: "Receptionists, doctors and accountants sign in with their mobile number." },
  { href: "/admin/roles", icon: KeyRound, title: "Review permissions", body: "System roles cover most clinics; create custom roles when needed." },
  { href: "/admin/settings", icon: Settings, title: "Booking & payment rules", body: "Advance payment, cancellation windows, reminders and branding." },
  { href: "/admin/audit-logs", icon: ScrollText, title: "Audit trail", body: "Every privileged change is recorded with actor and IP." },
];

export default function AdminOverview() {
  const { currentMembership, currentOrganizationId: orgId } = useAuth();
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => organizationsService.members(orgId!), enabled: !!orgId });
  const org = currentMembership?.organization;
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={org?.name ?? "Overview"} description={`You are signed in as ${currentMembership?.role_name ?? "staff"}.`} />
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Staff members" value={members.data?.length ?? "—"} />
        <Stat label="Status" value={<Badge variant={org?.status === "active" ? "success" : "warning"}>{org?.status}</Badge>} />
        <Stat label="Time zone / currency" value={`${org?.timezone ?? ""} · ${org?.currency ?? ""}`} />
      </div>
      <h3 className="mt-10 mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Set up next</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        {next.map((n) => (
          <Card key={n.href} className="gap-3 py-5">
            <CardHeader>
              <span className="grid size-9 place-items-center rounded-lg bg-accent text-accent-foreground"><n.icon className="size-4" /></span>
              <CardTitle className="pt-2">{n.title}</CardTitle>
              <CardDescription>{n.body}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline" size="sm"><Link href={n.href}>Open <ArrowRight /></Link></Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="mt-10 text-sm text-muted-foreground">Appointments, calendar, payments and reports arrive in the next phases. The sidebar shows the phase for each module.</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader><CardDescription>{label}</CardDescription></CardHeader>
      <CardContent className="text-xl font-semibold">{value}</CardContent>
    </Card>
  );
}
