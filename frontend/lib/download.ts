/** Download an authenticated file (CSV export, etc.) with the session and organization header. */
export async function downloadPrivateFile(url: string, filename: string, organizationId?: string | null): Promise<void> {
  const res = await fetch(url, { credentials: "include", headers: organizationId ? { "X-Organization-Id": organizationId } : undefined });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const objectUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
