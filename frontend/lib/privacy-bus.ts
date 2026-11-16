/**
 * Connects the API client (outside React) to the privacy screens (inside React):
 * - "reauth_required": the API wants the person to confirm it is them; the dialog asks, then the request is retried.
 * - "session_locked": the screen locked after inactivity; the lock screen takes over the page.
 */
type ReauthHandler = () => Promise<boolean>;

let reauthHandler: ReauthHandler | null = null;
let lockHandler: (() => void) | null = null;
let pending: Promise<boolean> | null = null;

export function setReauthHandler(handler: ReauthHandler | null) {
  reauthHandler = handler;
}

export function setLockHandler(handler: (() => void) | null) {
  lockHandler = handler;
}

/** One dialog at a time: parallel requests that all need confirmation share the same answer. */
export function askReauth(): Promise<boolean> {
  if (!reauthHandler) return Promise.resolve(false);
  if (!pending) pending = reauthHandler().finally(() => (pending = null));
  return pending;
}

export function notifyLocked() {
  lockHandler?.();
}
