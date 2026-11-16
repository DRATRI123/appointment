import { askReauth, notifyLocked } from "@/lib/privacy-bus";
/** Download an authenticated file (CSV export, etc.) with the session and organization header. */
export async function downloadPrivateFile(url: string, filename: string, organizationId?: string | null, retried = false): Promise<void> {
  const res = await fetch(url, { credentials: "include", headers: organizationId ? { "X-Organization-Id": organizationId } : undefined });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { code?: string; detail?: string } | null;
    // Exports need a recent "confirm it is you": ask, then try once more.
    if (res.status === 403 && body?.code === "reauth_required" && !retried && (await askReauth())) {
      return downloadPrivateFile(url, filename, organizationId, true);
    }
    if (res.status === 403 && body?.code === "session_locked") notifyLocked();
    throw new Error(body?.detail ?? `Download failed (${res.status})`);
  }
  const objectUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
