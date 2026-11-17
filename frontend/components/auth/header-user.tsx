"use client";

import { useRouter } from "next/navigation";
import { Building2, Check, ChevronsUpDown, LogOut, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth/auth-provider";
import { usePanelMode } from "@/hooks/use-panel-mode";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function HeaderUser({ showOrgSwitcher = true }: { showOrgSwitcher?: boolean }) {
  const { user, memberships, currentMembership, setCurrentOrganizationId, logout } = useAuth();
  const router = useRouter();
  const panel = usePanelMode();
  if (!user) return null;

  const staffMemberships = memberships.filter((m) => m.role_code !== "customer");

  return (
    <div className="flex min-w-0 shrink items-center gap-1.5 sm:gap-2">
      <NotificationBell />
      {showOrgSwitcher && !panel && staffMemberships.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="max-w-32 min-w-0 justify-between gap-2 sm:max-w-56">
              <Building2 className="size-4 text-muted-foreground" />
              <span className="truncate">{currentMembership?.organization.name}</span>
              <ChevronsUpDown className="size-3.5 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel>Organizations</DropdownMenuLabel>
            {staffMemberships.map((m) => (
              <DropdownMenuItem key={m.id} onSelect={() => setCurrentOrganizationId(m.organization.id)}>
                <span className="flex-1 truncate">{m.organization.name}</span>
                <span className="text-xs text-muted-foreground">{m.role_name}</span>
                {m.organization.id === currentMembership?.organization.id ? <Check className="size-4" /> : null}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => router.push("/onboarding")}>Create organization</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {initials(user.full_name) || <UserRound className="size-4" aria-hidden />}
            <span className="sr-only">, account menu for {user.full_name}</span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>
            <p className="truncate font-medium">{user.full_name}</p>
            <p className="truncate text-xs font-normal text-muted-foreground">{user.email ?? user.mobile}</p>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {panel ? null : (
            <>
              <DropdownMenuItem onSelect={() => router.push("/customer/profile")}>Profile &amp; security</DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          )}
          <DropdownMenuItem
            onSelect={async () => {
              await logout();
              toast.success("Signed out");
              // Inside the clinic's app: back to the panel's own sign-in.
              router.push(panel ? `/panel/${panel}` : "/login");
            }}
          >
            <LogOut className="size-4" /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
