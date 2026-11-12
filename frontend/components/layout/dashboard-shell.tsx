import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Logo } from "./logo";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  phase?: number;
}

export interface NavGroup {
  title?: string;
  items: NavItem[];
}

export function DashboardShell({
  title,
  roleLabel,
  groups,
  children,
}: {
  title: string;
  roleLabel: string;
  groups: NavGroup[];
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
        <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-6">
          {groups.map((group, index) => (
            <div key={group.title ?? index} className="space-y-1">
              {group.title ? (
                <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
                  {group.title}
                </p>
              ) : null}
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "group flex items-center justify-between rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  <span className="flex items-center gap-2.5">
                    <item.icon className="size-4 text-muted-foreground group-hover:text-accent-foreground" />
                    {item.label}
                  </span>
                  {item.phase ? <Badge variant="outline" className="text-[10px]">P{item.phase}</Badge> : null}
                </Link>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b px-4 md:px-8">
          <div className="flex items-center gap-3">
            <span className="lg:hidden">
              <Logo />
            </span>
            <h1 className="text-base font-semibold md:text-lg">{title}</h1>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="hidden sm:inline">Signed-in state arrives in Phase 2</span>
            <span className="grid size-9 place-items-center rounded-full bg-muted text-xs font-semibold">AP</span>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
