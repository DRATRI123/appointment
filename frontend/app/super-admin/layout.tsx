"use client";

import { Activity, Building2, CreditCard, Database, Gauge, Home, Plug, ScrollText, Settings2, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/super-admin", label: "Overview", icon: Home },
      { href: "/super-admin/organizations", label: "Organizations", icon: Building2 },
      { href: "/super-admin/users", label: "Users", icon: Users },
      { href: "/super-admin/subscriptions", label: "Subscriptions", icon: CreditCard },
      { href: "/super-admin/usage", label: "Usage & API", icon: Gauge },
      { href: "/super-admin/health", label: "System health", icon: Activity },
      { href: "/super-admin/database", label: "Database", icon: Database },
      { href: "/super-admin/integrations", label: "Integrations", icon: Plug },
      { href: "/super-admin/audit-logs", label: "Platform audit logs", icon: ScrollText },
      { href: "/super-admin/settings", label: "Platform settings", icon: Settings2 },
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
