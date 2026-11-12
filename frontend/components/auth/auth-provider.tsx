"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, setDefaultOrganizationId } from "@/lib/api-client";
import { authService } from "@/services/auth";
import { usersService } from "@/services/users";
import type { MeResponse, MembershipSummary, User } from "@/types/auth";

const ORG_STORAGE_KEY = "ap.currentOrganization";

interface AuthContextValue {
  user: User | null;
  memberships: MembershipSummary[];
  isPlatformAdmin: boolean;
  isLoading: boolean;
  currentMembership: MembershipSummary | null;
  currentOrganizationId: string | null;
  setCurrentOrganizationId: (id: string) => void;
  hasPermission: (code: string) => boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const ME_QUERY_KEY = ["me"] as const;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [storedOrg, setStoredOrg] = useState<string | null>(() => {
    try {
      return typeof window === "undefined" ? null : window.localStorage.getItem(ORG_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const meQuery = useQuery<MeResponse | null>({
    queryKey: ME_QUERY_KEY,
    queryFn: async () => {
      try {
        return await usersService.me();
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });

  const memberships = useMemo(() => meQuery.data?.memberships ?? [], [meQuery.data]);
  const currentMembership = useMemo(() => {
    if (!memberships.length) return null;
    return memberships.find((m) => m.organization.id === storedOrg) ?? memberships[0];
  }, [memberships, storedOrg]);
  const currentOrganizationId = currentMembership?.organization.id ?? null;

  useEffect(() => {
    setDefaultOrganizationId(currentOrganizationId ?? undefined);
  }, [currentOrganizationId]);

  const setCurrentOrganizationId = useCallback((id: string) => {
    setStoredOrg(id);
    try {
      window.localStorage.setItem(ORG_STORAGE_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const hasPermission = useCallback(
    (code: string) => Boolean(meQuery.data?.is_platform_admin || currentMembership?.permissions.includes(code)),
    [meQuery.data, currentMembership],
  );

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
  }, [queryClient]);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } finally {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.clear();
    }
  }, [queryClient]);

  const value: AuthContextValue = {
    user: meQuery.data?.user ?? null,
    memberships,
    isPlatformAdmin: Boolean(meQuery.data?.is_platform_admin),
    isLoading: meQuery.isLoading,
    currentMembership,
    currentOrganizationId,
    setCurrentOrganizationId,
    hasPermission,
    refresh,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Where a user should land after signing in. */
export function defaultDestination(me: { is_platform_admin: boolean; memberships: MembershipSummary[] } | null | undefined) {
  if (!me) return "/login";
  if (me.is_platform_admin) return "/super-admin";
  const staff = me.memberships.find((m) => m.role_code !== "customer");
  if (staff) return staff.role_code === "doctor" || staff.role_code === "professional" ? "/professional" : "/admin";
  return "/customer";
}
