"use client";

import Link from "next/link";
import { useAuth, defaultDestination } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";

export function HeaderAuthButtons() {
  const { user, isLoading, memberships, isPlatformAdmin } = useAuth();
  if (isLoading) return <div className="h-8 w-28" />;
  if (user) {
    return (
      <Button asChild size="sm">
        <Link href={defaultDestination({ is_platform_admin: isPlatformAdmin, memberships })}>Open dashboard</Link>
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <Button asChild variant="ghost" size="sm">
        <Link href="/login">Sign in</Link>
      </Button>
      <Button asChild size="sm">
        <Link href="/register">Get started</Link>
      </Button>
    </div>
  );
}
