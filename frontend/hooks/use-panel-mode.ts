"use client";

import { useSyncExternalStore } from "react";
import { panelSession, subscribePanel } from "@/lib/panel-session";

/** The clinic slug while this screen runs inside the clinic's app (embedded panel), otherwise null. */
export function usePanelMode(): string | null {
  return useSyncExternalStore(subscribePanel, () => panelSession()?.slug ?? null, () => null);
}
