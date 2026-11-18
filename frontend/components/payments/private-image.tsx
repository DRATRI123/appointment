"use client";

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionFetch } from "@/lib/api-client";

/** Loads an authenticated file (screenshot, document) with the session and organization header. */
export function PrivateImage({ url, organizationId, alt }: { url: string; organizationId: string | null; alt: string }) {
  const [state, setState] = useState<{ src?: string; type?: string; error?: string }>({});
  useEffect(() => {
    let revoked: string | undefined;
    let cancelled = false;
    sessionFetch(url, organizationId)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Could not load (${res.status})`);
        const type = res.headers.get("content-type") ?? "";
        const objectUrl = URL.createObjectURL(await res.blob());
        revoked = objectUrl;
        if (!cancelled) setState({ src: objectUrl, type });
      })
      .catch((e: Error) => !cancelled && setState({ error: e.message }));
    return () => { cancelled = true; if (revoked) URL.revokeObjectURL(revoked); };
  }, [url, organizationId]);
  if (state.error) return <p className="text-sm text-destructive">{state.error}</p>;
  if (!state.src) return <Skeleton className="h-64 w-full" />;
  if (state.type?.includes("pdf")) return <a href={state.src} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-sm underline"><FileText className="size-4" /> Open PDF</a>;
  // eslint-disable-next-line @next/next/no-img-element
  return <a href={state.src} target="_blank" rel="noreferrer"><img src={state.src} alt={alt} className="max-h-[420px] w-full rounded-lg border object-contain" data-testid="payment-screenshot" /></a>;
}
