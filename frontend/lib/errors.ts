import { ApiError } from "@/lib/api-client";

/** Human-readable message for any thrown value. */
export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error instanceof ApiError) return error.message || fallback;
  if (error instanceof Error) return error.message;
  return fallback;
}
