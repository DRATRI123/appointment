"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const MESSAGES: Record<string, [string, "success" | "error"]> = {
  connected: ["Google Calendar connected. Busy times are being read now.", "success"],
  denied: ["Google Calendar was not connected: access was not allowed.", "error"],
  failed: ["Google Calendar could not be connected. Try again, and allow calendar access when Google asks.", "error"],
  invalid_state: ["That connection link expired or was already used. Start again from this page.", "error"],
};

/** Shows the outcome of the Google OAuth redirect once, then removes it from the URL. */
export function GoogleResult() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const outcome = params.get("google");
  useEffect(() => {
    if (!outcome) return;
    const [msg, kind] = MESSAGES[outcome] ?? MESSAGES.failed;
    if (kind === "success") toast.success(msg);
    else toast.error(msg);
    queryClient.invalidateQueries({ queryKey: ["integrations"] });
    router.replace(pathname);
  }, [outcome, pathname, router, queryClient]);
  return null;
}
