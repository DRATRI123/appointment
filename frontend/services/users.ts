import { api } from "@/lib/api-client";
import type { MeResponse, User } from "@/types/auth";

export const usersService = {
  me: () => api.get<MeResponse>("/users/me"),
  updateMe: (body: { full_name?: string; avatar_url?: string | null }) => api.patch<User>("/users/me", body),
};
