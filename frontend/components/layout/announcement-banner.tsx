"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Info, TriangleAlert, X } from "lucide-react";
import { platformService } from "@/services/platform";
import { cn } from "@/lib/utils";

/** Platform-wide announcement set by super admins (maintenance windows, notices). Dismissible per message. */
export function AnnouncementBanner() {
  const info = useQuery({ queryKey: ["platform-public"], queryFn: platformService.publicInfo, staleTime: 5 * 60_000, retry: false });
  const message = info.data?.announcement?.trim();
  const [dismissed, setDismissed] = useState<string | null>(() => {
    try { return window.localStorage.getItem("ap.announcement.dismissed"); } catch { return null; }
  });
  if (!message || dismissed === message) return null;
  const warning = info.data?.announcement_level === "warning";
  const Icon = warning ? TriangleAlert : Info;
  return (
    <div role="status" className={cn("flex items-start gap-2 border-b px-4 py-2 text-sm md:px-8", warning ? "bg-warning/15" : "bg-accent text-accent-foreground")} data-testid="announcement">
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="flex-1">{message}</p>
      <button type="button" aria-label="Dismiss announcement" className="rounded p-0.5 hover:bg-black/5" onClick={() => { setDismissed(message); try { window.localStorage.setItem("ap.announcement.dismissed", message); } catch { /* storage blocked: dismiss for this view only */ } }}>
        <X className="size-4" />
      </button>
    </div>
  );
}
