"use client";

import { Logo } from "./logo";
import { HeaderUser } from "@/components/auth/header-user";
import { SidebarNav, type NavGroup } from "./sidebar-nav";

export type { NavGroup, NavItem } from "./sidebar-nav";

export function DashboardShell({
  title,
  roleLabel,
  groups,
  showOrgSwitcher = true,
  children,
}: {
  title: string;
  roleLabel: string;
  groups: NavGroup[];
  showOrgSwitcher?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen w-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground lg:flex">
        <div className="flex h-16 items-center border-b border-sidebar-border px-5">
          <Logo href="/" />
        </div>
        <div className="px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{roleLabel}</p>
        </div>
        <SidebarNav groups={groups} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between gap-3 border-b px-4 md:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="lg:hidden">
              <Logo />
            </span>
            <h1 className="hidden truncate text-base font-semibold sm:block md:text-lg">{title}</h1>
          </div>
          <HeaderUser showOrgSwitcher={showOrgSwitcher} />
        </header>
        <main className="flex-1 p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
