/**
 * Only same-site paths may be used as a post-login destination. Rejects absolute URLs, protocol-relative
 * "//host", backslash variants ("/\\host" is treated as "//host" by browsers), and control characters.
 */
export function safeNextPath(next: string | null | undefined): string | null {
  if (!next) return null;
  let value = next;
  try { value = decodeURIComponent(next); } catch { return null; }
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return null;
  if (/[\u0000-\u001f\u007f\\]/.test(value)) return null;
  return value;
}
