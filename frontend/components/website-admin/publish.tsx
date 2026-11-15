"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { History, Loader2, Monitor, RotateCcw, Send, Smartphone, Tablet, Undo2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { websiteAdmin } from "@/services/website";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useEditor } from "./editor";
import type { WebsiteDocument } from "@/types/website";

const DEVICES = { desktop: { width: 1280, label: "Desktop", icon: Monitor }, tablet: { width: 820, label: "Tablet", icon: Tablet }, mobile: { width: 390, label: "Phone", icon: Smartphone } } as const;
type Device = keyof typeof DEVICES;

export const PREVIEW_READY = "website-preview:ready";
export const PREVIEW_DOCUMENT = "website-preview:document";

/** The preview frame shows the *unsaved* working copy, sent over postMessage between two pages of this same site. */
export function DevicePreview({ doc, slug, page }: { doc: WebsiteDocument; slug: string; page: string }) {
  const [device, setDevice] = useState<Device>("desktop");
  const frame = useRef<HTMLIFrameElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const send = useCallback(() => {
    frame.current?.contentWindow?.postMessage({ type: PREVIEW_DOCUMENT, document: doc, slug, page }, window.location.origin);
  }, [doc, slug, page]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin === window.location.origin && e.source === frame.current?.contentWindow && e.data?.type === PREVIEW_READY) send();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [send]);
  useEffect(() => { send(); }, [send]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => setScale(Math.min(1, el.clientWidth / DEVICES[device].width));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [device]);

  const width = DEVICES[device].width;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Preview size">
        {(Object.keys(DEVICES) as Device[]).map((d) => {
          const Icon = DEVICES[d].icon;
          return <Button key={d} type="button" size="sm" role="radio" aria-checked={device === d} variant={device === d ? "default" : "outline"} onClick={() => setDevice(d)} data-testid={`preview-${d}`}><Icon /> {DEVICES[d].label}</Button>;
        })}
      </div>
      <div ref={box} className="overflow-hidden rounded-2xl border bg-muted/40 p-2">
        <div className="mx-auto origin-top-left" style={{ width: width * scale, height: 760 * scale }}>
          <iframe ref={frame} title={`Website preview (${DEVICES[device].label})`} src="/website-preview" onLoad={send} data-testid="preview-frame"
            className={cn("block rounded-xl border bg-white shadow-sm", device === "mobile" && "rounded-[2rem]")}
            style={{ width, height: 760, transform: `scale(${scale})`, transformOrigin: "top left" }} />
        </div>
      </div>
    </div>
  );
}

export function PublishPage() {
  const { doc, state, dirty, publish, publishing, canPublish, reload } = useEditor();
  const { currentOrganizationId: orgId } = useAuth();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [page, setPage] = useState("");
  const [restoreV, setRestoreV] = useState<number | null>(null);
  const [discardOpen, setDiscardOpen] = useState(false);
  const versions = useQuery({ queryKey: ["website-versions", orgId], queryFn: websiteAdmin.versions, enabled: !!orgId });
  const slug = state.public_url_path.replace(/^\//, "");
  const after = (r: Awaited<ReturnType<typeof websiteAdmin.get>>) => { queryClient.setQueryData(["website-admin", orgId], r); reload(); };
  const restore = useMutation({
    mutationFn: (v: number) => websiteAdmin.restore(v, state.lock_version),
    onSuccess: (r, v) => { after(r); setRestoreV(null); toast.success(`Version ${v} copied into the draft. Publish to make it live.`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const discard = useMutation({
    mutationFn: () => websiteAdmin.discard(state.lock_version),
    onSuccess: (r) => { after(r); setDiscardOpen(false); toast.success("Draft reset to the live website"); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>Shows your current edits, including unsaved ones. Visitors keep seeing the live version until you publish.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex max-w-sm items-center gap-2 text-sm">Page
            <NativeSelect value={page} onChange={(e) => setPage(e.target.value)} aria-label="Preview page">
              <option value="">Home page</option>
              {doc.pages.map((p) => <option key={p.slug} value={p.slug}>{p.title}</option>)}
            </NativeSelect>
          </label>
          <DevicePreview doc={doc} slug={slug} page={page} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Publish</CardTitle><CardDescription>{canPublish ? "Publishing replaces the live website with this draft. Every published version is kept so you can go back." : "Only administrators with the “Publish the public website” permission can publish. Save your draft and ask them to review it."}</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {canPublish ? (
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={async (e) => { e.preventDefault(); if (await publish(note)) setNote(""); }}>
              <Input aria-label="What changed (optional)" placeholder="What changed? (optional, e.g. New monsoon timings)" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
              <Button type="submit" disabled={publishing || (!dirty && !state.has_unpublished_changes)} data-testid="publish-now">{publishing ? <Loader2 className="animate-spin" /> : <Send />} Publish now</Button>
            </form>
          ) : null}
          {state.published_version ? <Button type="button" variant="ghost" size="sm" onClick={() => setDiscardOpen(true)} disabled={!state.has_unpublished_changes && !dirty}><Undo2 /> Discard draft and go back to the live version</Button> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><History className="size-5" /> Published versions</CardTitle></CardHeader>
        <CardContent>
          {versions.data?.length ? (
            <ul className="divide-y rounded-xl border">
              {versions.data.map((v) => (
                <li key={v.version} className="flex flex-wrap items-center gap-3 p-3 text-sm" data-testid="website-version">
                  <span className="font-medium">Version {v.version}</span>
                  {v.version === state.published_version ? <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">Live</span> : null}
                  <span className="text-muted-foreground">{new Date(v.published_at).toLocaleString("en-IN")}{v.published_by ? ` · ${v.published_by}` : ""}</span>
                  {v.note ? <span className="text-muted-foreground">“{v.note}”</span> : null}
                  {canPublish && v.version !== state.published_version ? <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={() => setRestoreV(v.version)}><RotateCcw /> Restore</Button> : null}
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">Nothing published yet.</p>}
        </CardContent>
      </Card>

      <Dialog open={restoreV !== null} onOpenChange={(o) => { if (!o) setRestoreV(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Restore version {restoreV}?</DialogTitle>
            <DialogDescription>It replaces your current draft{dirty ? " (including unsaved changes)" : ""}. The live website changes only when you publish.</DialogDescription></DialogHeader>
          <DialogFooter><Button variant="outline" onClick={() => setRestoreV(null)}>Cancel</Button><Button onClick={() => restoreV && restore.mutate(restoreV)} disabled={restore.isPending} data-testid="confirm-restore">Restore into draft</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Discard the draft?</DialogTitle><DialogDescription>All changes since the last publish are lost.</DialogDescription></DialogHeader>
          <DialogFooter><Button variant="outline" onClick={() => setDiscardOpen(false)}>Keep editing</Button><Button variant="destructive" onClick={() => discard.mutate()} disabled={discard.isPending}>Discard draft</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
