/**
 * Embedded admin panel: the clinic's own app shows this admin panel in an iframe (/panel/<clinic>).
 *
 * The sign-in made there is separate from the ordinary one. Its tokens are kept in this frame's session storage only
 * (never in cookies), so it never replaces or ends the person's ordinary sign-in in the same browser, browsers that
 * block cookies in frames still work, and closing the clinic app's tab signs the panel out. The server limits these
 * sessions to the one clinic and checks the clinic's settings and the person's permission on every request.
 */
import { apiBase } from "@/lib/env";

const KEY = "ap.panel";
const SLUG_KEY = "ap.panel.slug";
const HINT_COOKIE = "panel_slug";

export interface PanelSession {
  slug: string;
  organizationId: string;
  access: string;
  refresh: string;
}

export interface PanelTokens {
  access_token: string;
  refresh_token: string;
  organization_id: string;
}

// Pages the panel shows. Other framed pages of this site (the booking page embedded on a website, the website preview)
// never use the panel's sign-in, even in the same browser tab.
const PANEL_PAGES = /^\/(panel|admin|professional)(\/|$)/;

function onPanelPage(): boolean {
  return isFramed() && PANEL_PAGES.test(window.location.pathname);
}

/** True inside an iframe (a browser that hides the parent also counts as framed). */
export function isFramed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

/** The panel sign-in, only while this page is inside a frame (opened on its own, the ordinary sign-in applies). */
export function panelSession(): PanelSession | null {
  if (!onPanelPage()) return null;
  try {
    const raw = storage()?.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<PanelSession>;
    return s.slug && s.organizationId && s.access && s.refresh ? (s as PanelSession) : null;
  } catch {
    return null;
  }
}

/** The clinic of the panel this frame shows (kept after signing out, to come back to its sign-in page). */
export function panelSlug(): string | null {
  if (!onPanelPage()) return null;
  return storage()?.getItem(SLUG_KEY) ?? null;
}

export function panelLoginPath(next?: string | null): string {
  const slug = panelSlug();
  if (!slug) return "/login";
  return next ? `/panel/${slug}?next=${encodeURIComponent(next)}` : `/panel/${slug}`;
}

export function rememberPanelSlug(slug: string) {
  storage()?.setItem(SLUG_KEY, slug);
  // Only a routing hint for the server (a reload inside the frame returns through /panel/<clinic>); it grants nothing.
  const secure = window.location.protocol === "https:";
  document.cookie = `${HINT_COOKIE}=${encodeURIComponent(slug)}; Path=/; Max-Age=43200; ${secure ? "SameSite=None; Secure; Partitioned" : "SameSite=Lax"}`;
}

export function savePanelSession(slug: string, tokens: PanelTokens) {
  rememberPanelSlug(slug);
  storage()?.setItem(KEY, JSON.stringify({ slug, organizationId: tokens.organization_id, access: tokens.access_token, refresh: tokens.refresh_token }));
  notify();
}

export function clearPanelSession() {
  storage()?.removeItem(KEY);
  notify();
}

/** "omit" inside the panel's frame (signed in or not): the frame never uses the browser's ordinary sign-in cookies. */
export function credentialsMode(): RequestCredentials {
  return panelSlug() ? "omit" : "include";
}

/** Headers for a request made by the panel: its own token and its clinic. Empty outside the panel. */
export function panelHeaders(): Record<string, string> {
  const s = panelSession();
  return s ? { Authorization: `Bearer ${s.access}`, "X-Organization-Id": s.organizationId } : {};
}

let refreshing: Promise<boolean> | null = null;
/** New access token for the panel sign-in (the refresh token is rotated). False: sign in again. */
export function refreshPanelSession(): Promise<boolean> {
  const s = panelSession();
  if (!s) return Promise.resolve(false);
  refreshing ??= fetch(`${apiBase}/panel/${s.slug}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ refresh_token: s.refresh }),
    credentials: "omit",
  })
    .then(async (r) => {
      if (!r.ok) {
        clearPanelSession();
        return false;
      }
      savePanelSession(s.slug, (await r.json()) as PanelTokens);
      return true;
    })
    .catch(() => false)
    .finally(() => setTimeout(() => (refreshing = null), 0));
  return refreshing;
}

/** Sign out of the panel only: the ordinary sign-in in this browser is not touched. */
export async function panelSignOut(): Promise<void> {
  const s = panelSession();
  clearPanelSession();
  if (!s) return;
  await fetch(`${apiBase}/panel/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: s.refresh }),
    credentials: "omit",
  }).catch(() => undefined);
}

/** Where the person's parent page lives (for the audit log only; the browser enforces the allowed list). */
export function parentOrigin(): string | undefined {
  try {
    const ancestors = (window.location as Location & { ancestorOrigins?: DOMStringList }).ancestorOrigins;
    if (ancestors && ancestors.length) return ancestors[0];
    return document.referrer ? new URL(document.referrer).origin : undefined;
  } catch {
    return undefined;
  }
}

// React components read the panel state with useSyncExternalStore (nothing on the server, the real value in the
// browser), so the first render matches the server's.
const listeners = new Set<() => void>();
function notify() {
  listeners.forEach((l) => l());
}
export function subscribePanel(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
