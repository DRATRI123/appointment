"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { isFramed, panelLoginPath, panelSlug } from "@/lib/panel-session";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  children: React.ReactNode;
  requirePlatformAdmin?: boolean;
  requireMembership?: boolean;
  permission?: string;
}

export function RequireAuth({ children, requirePlatformAdmin, requireMembership, permission }: Props) {
  const { user, isLoading, isPlatformAdmin, memberships, hasPermission } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      // Inside the clinic's app: back to the panel's own sign-in, never the ordinary one.
      router.replace(isFramed() && panelSlug() ? panelLoginPath(pathname) : `/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (requireMembership && !isPlatformAdmin && memberships.length === 0) {
      router.replace("/onboarding");
    }
  }, [isLoading, user, requireMembership, isPlatformAdmin, memberships.length, router, pathname]);

  if (isLoading || !user) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 p-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if ((requirePlatformAdmin && !isPlatformAdmin) || (permission && !hasPermission(permission))) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 p-12 text-center">
        <ShieldAlert className="size-10 text-destructive" />
        <h2 className="text-lg font-semibold">You don&apos;t have access to this area</h2>
        <p className="text-sm text-muted-foreground">Ask an organization owner to grant you the required role.</p>
        <Button variant="outline" onClick={() => router.push("/")}>Back to home</Button>
      </div>
    );
  }
  if (requireMembership && !isPlatformAdmin && memberships.length === 0) return null;
  return <>{children}</>;
}
