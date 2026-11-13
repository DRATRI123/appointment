"use client";

import { CalendarDays, ClipboardList, Home, Plane, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/professional", label: "Today", icon: Home },
      { href: "/professional/calendar", label: "Calendar", icon: CalendarDays },
      { href: "/professional/patients", label: "Patients", icon: Users, phase: 5 },
      { href: "/professional/notes", label: "Notes", icon: ClipboardList, phase: 5 },
      { href: "/admin/schedules", label: "Schedule & leave", icon: Plane },
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
