"use client";

import {
  BarChart3,
  BookOpen,
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
  LineChart,
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
  EyeOff,
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
      { href: "/admin/calendar", label: "Calendar", icon: CalendarDays, permission: ["appointments:read", "appointments:read_own"] },
      { href: "/admin/appointments", label: "Appointments", icon: ClipboardList, permission: ["appointments:read", "appointments:read_own"] },
      { href: "/admin/waitlist", label: "Waitlist", icon: ListPlus, permission: "appointments:read" },
      { href: "/admin/website", label: "Website", icon: LayoutTemplate, permission: "website:write" },
      { href: "/admin/booking-page", label: "Booking page & Shopify", icon: Globe, permission: "organization:write" },
    ],
  },
  {
    title: "Catalogue",
    items: [
      { href: "/admin/professionals", label: "Professionals", icon: Stethoscope, permission: "professionals:read" },
      { href: "/admin/schedules", label: "Schedules", icon: Clock, permission: "professionals:read" },
      { href: "/admin/services", label: "Services", icon: Briefcase, permission: "services:read" },
      { href: "/admin/categories", label: "Categories", icon: LayoutList, permission: "services:read" },
      { href: "/admin/branches", label: "Branches", icon: Building2, permission: "branches:read" },
      { href: "/admin/customers", label: "Customers", icon: Users, permission: "customers:read" },
      { href: "/admin/booking-forms", label: "Booking forms", icon: FileSpreadsheet, permission: "booking_forms:read" },
    ],
  },
  {
    title: "Payments",
    items: [
      { href: "/admin/payments", label: "Payments", icon: CreditCard, permission: "payments:read" },
      { href: "/admin/upi-accounts", label: "UPI accounts", icon: QrCode, permission: "upi_accounts:read" },
      { href: "/admin/payments/verification", label: "Verification", icon: ShieldCheck, permission: "payments:verify" },
      { href: "/admin/coupons", label: "Coupons", icon: TicketPercent, permission: "services:write" },
      { href: "/admin/reconciliation", label: "Bank reconciliation", icon: Landmark, permission: "reconciliation:manage" },
      { href: "/admin/refunds", label: "Refunds", icon: RotateCcw, permission: ["refunds:request", "refunds:approve"] },
    ],
  },
  {
    title: "Operations",
    items: [
      { href: "/admin/notifications", label: "Notifications", icon: Bell, permission: "notifications:read" },
      { href: "/admin/integrations", label: "Integrations", icon: Plug, permission: "integrations:read" },
      { href: "/admin/developers", label: "Developers", icon: Code2, permission: "api_keys:manage" },
      { href: "/admin/developers/docs", label: "Developer docs", icon: BookOpen, permission: "api_keys:manage" },
      { href: "/admin/reports", label: "Reports", icon: BarChart3, permission: "reports:read" },
      { href: "/admin/website-analytics", label: "Website analytics", icon: LineChart, permission: "reports:read" },
      { href: "/admin/staff", label: "Staff", icon: UsersRound, permission: "staff:read" },
      { href: "/admin/roles", label: "Roles & permissions", icon: KeyRound, permission: "roles:write" },
      { href: "/admin/settings", label: "Organization settings", icon: Settings, permission: "organization:write" },
      { href: "/admin/settings/verification", label: "OTP & verification", icon: ShieldCheck, permission: "organization:write" },
      { href: "/admin/settings/privacy", label: "Privacy & data protection", icon: EyeOff, permission: "organization:write" },
      { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText, permission: "audit_logs:read" },
    ],
  },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth requireMembership>
      <DashboardShell title="Organization admin" groups={groups}>{children}</DashboardShell>
    </RequireAuth>
  );
}
