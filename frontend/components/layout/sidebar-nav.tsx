"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  phase?: number;
  /** Shown only to people with this permission (or any of these). The server enforces it either way. */
  permission?: string | string[];
}

export interface NavGroup {
  title?: string;
  items: NavItem[];
}

export function SidebarNav({ groups: allGroups }: { groups: NavGroup[] }) {
  const pathname = usePathname();
  const { hasPermission, user } = useAuth();
  const allowed = (item: NavItem) => !item.permission || !!user?.is_platform_admin
    || (Array.isArray(item.permission) ? item.permission.some(hasPermission) : hasPermission(item.permission));
  const groups = allGroups.map((g) => ({ ...g, items: g.items.filter(allowed) })).filter((g) => g.items.length);
  const matches = (href: string) => pathname === href || (href.split("/").length > 2 && pathname.startsWith(href + "/"));
  // Only the most specific matching item is active (e.g. "Developer docs" rather than also "Developers").
  const best = groups.flatMap((g) => g.items).filter((i) => matches(i.href)).sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (
    <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-6">
      {groups.map((group, index) => (
        <div key={group.title ?? index} className="space-y-1">
          {group.title ? (
            <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{group.title}</p>
          ) : null}
          {group.items.map((item) => {
            const active = item.href === best;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group flex items-center justify-between rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
                  active && "bg-accent text-accent-foreground font-medium",
                )}
              >
                <span className="flex items-center gap-2.5">
                  <item.icon className={cn("size-4 text-muted-foreground group-hover:text-accent-foreground", active && "text-accent-foreground")} />
                  {item.label}
                </span>
                {item.phase ? <Badge variant="outline" className="text-[10px]">P{item.phase}</Badge> : null}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
