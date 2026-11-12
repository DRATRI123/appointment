"use client";

import { CalendarDays, ClipboardList, Home, Plane, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/professional", label: "Today", icon: Home },
      { href: "/professional/calendar", label: "Calendar", icon: CalendarDays, phase: 4 },
      { href: "/professional/patients", label: "Patients", icon: Users, phase: 5 },
      { href: "/professional/notes", label: "Notes", icon: ClipboardList, phase: 5 },
      { href: "/professional/leave", label: "Leave", icon: Plane, phase: 4 },
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
