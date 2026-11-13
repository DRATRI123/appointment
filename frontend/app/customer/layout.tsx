"use client";

import { CalendarDays, CreditCard, Home, UserCog, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/customer", label: "Overview", icon: Home },
      { href: "/customer/appointments", label: "Appointments", icon: CalendarDays },
      { href: "/customer/payments", label: "Payments", icon: CreditCard },
      { href: "/customer/family", label: "Family & preferences", icon: Users },
      { href: "/customer/profile", label: "Profile & security", icon: UserCog },
    ],
  },
];

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth >
      <DashboardShell title="My appointments" roleLabel="Customer" groups={groups} showOrgSwitcher={false}>{children}</DashboardShell>
    </RequireAuth>
  );
}
