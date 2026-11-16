"use client";

import { Logo } from "./logo";
import { HeaderUser } from "@/components/auth/header-user";
import { AnnouncementBanner } from "@/components/layout/announcement-banner";
import { SidebarNav, type NavGroup } from "./sidebar-nav";
import { EnvironmentBadge } from "./environment-badge";
import { useAuth } from "@/components/auth/auth-provider";
import { PrivacyGuard } from "@/components/privacy/privacy-guard";

export type { NavGroup, NavItem } from "./sidebar-nav";

export function DashboardShell({
  title,
  roleLabel,
  groups,
  showOrgSwitcher = true,
  protect = true,
  children,
}: {
  title: string;
  /** Fixed label (platform, patient); by default the signed-in person's role in the current clinic. */
  roleLabel?: string;
  groups: NavGroup[];
  showOrgSwitcher?: boolean;
  /** Staff screens: inactivity lock, watermark, print policy, "confirm it is you". Off for the patient area. */
  protect?: boolean;
  children: React.ReactNode;
}) {
  const { currentMembership } = useAuth();
  const label = roleLabel ?? (currentMembership ? `${currentMembership.role_name}${currentMembership.branch_id ? " · one branch" : ""}` : "");
  return (
    <div className="flex min-h-screen w-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground lg:flex">
        <div className="flex h-16 items-center border-b border-sidebar-border px-5">
          <Logo href="/" />
        </div>
        <div className="px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground" data-testid="role-label">{label}</p>
        </div>
        <SidebarNav groups={groups} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between gap-3 border-b px-4 md:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="lg:hidden">
              <Logo labelClassName="hidden sm:inline" />
            </span>
            <h1 className="hidden truncate text-base font-semibold sm:block md:text-lg">{title}</h1>
            <EnvironmentBadge />
          </div>
          <HeaderUser showOrgSwitcher={showOrgSwitcher} />
        </header>
        <AnnouncementBanner />
        <main className="flex-1 p-4 md:p-8"><PrivacyGuard enabled={protect}>{children}</PrivacyGuard></main>
      </div>
    </div>
  );
}
