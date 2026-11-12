import { CalendarDays, CreditCard, History, Home, Users } from "lucide-react";
import { DashboardShell } from "@/components/layout/dashboard-shell";

const groups = [
  {
    items: [
      { href: "/customer", label: "Overview", icon: Home },
      { href: "/customer/appointments", label: "Appointments", icon: CalendarDays, phase: 4 },
      { href: "/customer/history", label: "History", icon: History, phase: 4 },
      { href: "/customer/payments", label: "Payments", icon: CreditCard, phase: 6 },
      { href: "/customer/family", label: "Family members", icon: Users, phase: 5 },
    ],
  },
];

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  return (
    <DashboardShell title="My appointments" roleLabel="Customer" groups={groups}>
      {children}
    </DashboardShell>
  );
}
