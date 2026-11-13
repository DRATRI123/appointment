"use client";

import { CalendarCheck2, CalendarDays, Home, Plane, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/professional", label: "Today", icon: Home },
      { href: "/professional/calendar", label: "Calendar", icon: CalendarDays },
      { href: "/admin/customers", label: "Patients", icon: Users },
      { href: "/admin/schedules", label: "Schedule & leave", icon: Plane },
      { href: "/professional/calendar-sync", label: "Calendar & video", icon: CalendarCheck2 },
    ],
  },
];

export default function ProfessionalLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth requireMembership>
      <DashboardShell title="Professional dashboard" roleLabel="Doctor / Professional" groups={groups}>{children}</DashboardShell>
    </RequireAuth>
  );
}
