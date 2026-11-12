"use client";

import { Activity, Building2, CreditCard, Gauge, Home, ScrollText, Settings2, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/super-admin", label: "Overview", icon: Home },
      { href: "/super-admin/organizations", label: "Organizations", icon: Building2, phase: 2 },
      { href: "/super-admin/users", label: "Users", icon: Users, phase: 2 },
      { href: "/super-admin/subscriptions", label: "Subscriptions", icon: CreditCard, phase: 10 },
      { href: "/super-admin/usage", label: "Usage & API", icon: Gauge, phase: 11 },
      { href: "/super-admin/health", label: "System health", icon: Activity, phase: 13 },
      { href: "/super-admin/audit-logs", label: "Platform audit logs", icon: ScrollText, phase: 2 },
      { href: "/super-admin/settings", label: "Platform settings", icon: Settings2, phase: 10 },
    ],
  },
];

export default function SuperAdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth requirePlatformAdmin>
      <DashboardShell title="Platform administration" roleLabel="Platform super admin" groups={groups} showOrgSwitcher={false}>{children}</DashboardShell>
    </RequireAuth>
  );
}
