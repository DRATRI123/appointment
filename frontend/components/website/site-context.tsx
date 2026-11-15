"use client";

import { createContext, useContext } from "react";
import type { LinkContext } from "@/lib/site-links";
import type { PublicOrganization } from "@/types/catalog";
import type { WebsiteDocument } from "@/types/website";

export interface SiteContextValue {
  slug: string;
  base: string;
  org: PublicOrganization;
  doc: WebsiteDocument;
  /** Admin preview: empty sections show a hint instead of disappearing, and links do not leave the preview. */
  preview: boolean;
  campaign: Record<string, string>;
  links: LinkContext;
}

export const SiteContext = createContext<SiteContextValue | null>(null);

export function useSite(): SiteContextValue {
  const ctx = useContext(SiteContext);
  if (!ctx) throw new Error("useSite outside SiteShell");
  return ctx;
}
