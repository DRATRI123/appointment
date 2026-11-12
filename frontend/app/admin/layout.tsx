"use client";

import {
  BarChart3,
  Bell,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardList,
  CreditCard,
  FileSpreadsheet,
  Home,
  KeyRound,
  Landmark,
  LayoutList,
  Plug,
  QrCode,
  RotateCcw,
  ScrollText,
  Settings,
  ShieldCheck,
  Stethoscope,
  Users,
  UsersRound,
} from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/admin", label: "Overview", icon: Home },
      { href: "/admin/calendar", label: "Calendar", icon: CalendarDays, phase: 4 },
      { href: "/admin/appointments", label: "Appointments", icon: ClipboardList, phase: 4 },
    ],
  },
  {
    title: "Catalogue",
    items: [
      { href: "/admin/professionals", label: "Professionals", icon: Stethoscope, phase: 3 },
      { href: "/admin/services", label: "Services", icon: Briefcase, phase: 3 },
      { href: "/admin/categories", label: "Categories", icon: LayoutList, phase: 3 },
      { href: "/admin/branches", label: "Branches", icon: Building2, phase: 3 },
      { href: "/admin/customers", label: "Customers", icon: Users, phase: 5 },
      { href: "/admin/booking-forms", label: "Booking forms", icon: FileSpreadsheet, phase: 5 },
    ],
  },
  {
    title: "Payments",
    items: [
      { href: "/admin/payments", label: "Payments", icon: CreditCard, phase: 6 },
      { href: "/admin/upi-accounts", label: "UPI accounts", icon: QrCode, phase: 6 },
      { href: "/admin/payments/verification", label: "Verification", icon: ShieldCheck, phase: 6 },
      { href: "/admin/reconciliation", label: "Bank reconciliation", icon: Landmark, phase: 7 },
      { href: "/admin/refunds", label: "Refunds", icon: RotateCcw, phase: 7 },
    ],
  },
  {
    title: "Operations",
    items: [
      { href: "/admin/notifications", label: "Notifications", icon: Bell, phase: 8 },
      { href: "/admin/integrations", label: "Integrations", icon: Plug, phase: 9 },
      { href: "/admin/reports", label: "Reports", icon: BarChart3, phase: 10 },
      { href: "/admin/staff", label: "Staff", icon: UsersRound, phase: 2 },
      { href: "/admin/roles", label: "Roles & permissions", icon: KeyRound, phase: 2 },
      { href: "/admin/settings", label: "Organization settings", icon: Settings, phase: 2 },
      { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText, phase: 2 },
    ],
  },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth requireMembership>
      <DashboardShell title="Organization admin" roleLabel="Organization admin" groups={groups}>{children}</DashboardShell>
    </RequireAuth>
  );
}
