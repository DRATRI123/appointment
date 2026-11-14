import { permanentRedirect } from "next/navigation";

type Search = Record<string, string | string[] | undefined>;

/** The public booking page moved from /o/<slug>/... to /<slug>/...; old links (emails, SMS, QR posters) keep working. */
export function redirectTo(path: string, search: Search, extra: Record<string, string> = {}): never {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    if (typeof value === "string") qs.set(key, value);
    else if (Array.isArray(value) && value[0]) qs.set(key, value[0]);
  }
  for (const [key, value] of Object.entries(extra)) qs.set(key, value);
  const query = qs.toString();
  permanentRedirect(query ? `${path}?${query}` : path);
}
