"use client";

import { useRouter } from "next/navigation";
import { Building2, Check, ChevronsUpDown, LogOut, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth/auth-provider";
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
  if (!user) return null;

  const staffMemberships = memberships.filter((m) => m.role_code !== "customer");

  return (
    <div className="flex items-center gap-2">
      {showOrgSwitcher && staffMemberships.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="max-w-56 justify-between gap-2">
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
          <button className="grid size-9 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary" aria-label="Account menu">
            {initials(user.full_name) || <UserRound className="size-4" />}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>
            <p className="truncate font-medium">{user.full_name}</p>
            <p className="truncate text-xs font-normal text-muted-foreground">{user.email ?? user.mobile}</p>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => router.push("/customer/profile")}>Profile &amp; security</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={async () => {
              await logout();
              toast.success("Signed out");
              router.push("/login");
            }}
          >
            <LogOut className="size-4" /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
