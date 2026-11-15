"use client";

import {
  BarChart3,
  Bell,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardList,
  Code2,
  CreditCard,
  FileSpreadsheet,
  Globe,
  LayoutTemplate,
  Home,
  KeyRound,
  Landmark,
  LayoutList,
  ListPlus,
  Clock,
  Plug,
  QrCode,
  RotateCcw,
  ScrollText,
  Settings,
  ShieldCheck,
  TicketPercent,
  Stethoscope,
  Users,
  UsersRound,
} from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RequireAuth } from "@/components/auth/require-auth";

const groups = [
  {
    items: [
      { href: "/admin", label: "Dashboard", icon: Home },
      { href: "/admin/calendar", label: "Calendar", icon: CalendarDays },
      { href: "/admin/appointments", label: "Appointments", icon: ClipboardList },
      { href: "/admin/waitlist", label: "Waitlist", icon: ListPlus },
      { href: "/admin/website", label: "Website", icon: LayoutTemplate },
      { href: "/admin/booking-page", label: "Booking page & Shopify", icon: Globe },
    ],
  },
  {
    title: "Catalogue",
    items: [
      { href: "/admin/professionals", label: "Professionals", icon: Stethoscope },
      { href: "/admin/schedules", label: "Schedules", icon: Clock },
      { href: "/admin/services", label: "Services", icon: Briefcase },
      { href: "/admin/categories", label: "Categories", icon: LayoutList },
      { href: "/admin/branches", label: "Branches", icon: Building2 },
      { href: "/admin/customers", label: "Customers", icon: Users },
      { href: "/admin/booking-forms", label: "Booking forms", icon: FileSpreadsheet },
    ],
  },
  {
    title: "Payments",
    items: [
      { href: "/admin/payments", label: "Payments", icon: CreditCard },
      { href: "/admin/upi-accounts", label: "UPI accounts", icon: QrCode },
      { href: "/admin/payments/verification", label: "Verification", icon: ShieldCheck },
      { href: "/admin/coupons", label: "Coupons", icon: TicketPercent },
      { href: "/admin/reconciliation", label: "Bank reconciliation", icon: Landmark },
      { href: "/admin/refunds", label: "Refunds", icon: RotateCcw },
    ],
  },
  {
    title: "Operations",
    items: [
      { href: "/admin/notifications", label: "Notifications", icon: Bell },
      { href: "/admin/integrations", label: "Integrations", icon: Plug },
      { href: "/admin/developers", label: "Developers", icon: Code2 },
      { href: "/admin/reports", label: "Reports", icon: BarChart3 },
      { href: "/admin/staff", label: "Staff", icon: UsersRound },
      { href: "/admin/roles", label: "Roles & permissions", icon: KeyRound },
      { href: "/admin/settings", label: "Organization settings", icon: Settings },
      { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText },
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
