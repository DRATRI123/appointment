import { api } from "@/lib/api-client";
import type { PublicWebsite, WebsiteDocument, WebsiteState, WebsiteVersion } from "@/types/website";

export const websiteAdmin = {
  get: () => api.get<WebsiteState>("/website"),
  saveDraft: (document: WebsiteDocument, lock_version: number) => api.put<WebsiteState>("/website/draft", { document, lock_version }),
  publish: (lock_version: number, note = "") => api.post<WebsiteState>("/website/publish", { lock_version, note }),
  discard: (lock_version: number) => api.post<WebsiteState>("/website/draft/discard", { lock_version }),
  versions: () => api.get<WebsiteVersion[]>("/website/versions"),
  restore: (version: number, lock_version: number) => api.post<WebsiteState>(`/website/versions/${version}/restore`, { lock_version }),
};

export const publicWebsite = {
  get: (slug: string) => api.get<PublicWebsite>(`/public/organizations/${slug}/website`),
};
