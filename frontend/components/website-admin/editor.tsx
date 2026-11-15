"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ExternalLink, Eye, Loader2, Save, Send, Undo2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { websiteAdmin } from "@/services/website";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";
import type { WebsiteDocument, WebsiteState } from "@/types/website";

interface EditorValue {
  doc: WebsiteDocument;
  state: WebsiteState;
  dirty: boolean;
  canWrite: boolean;
  canPublish: boolean;
  /** Replace the working copy (not saved until save()). */
  update: (fn: (doc: WebsiteDocument) => WebsiteDocument) => void;
  save: () => Promise<boolean>;
  saving: boolean;
  publish: (note?: string) => Promise<boolean>;
  publishing: boolean;
  reload: () => void;
}

const EditorContext = createContext<EditorValue | null>(null);

export function useEditor(): EditorValue {
  const ctx = useContext(EditorContext);
  if (!ctx) throw new Error("useEditor outside WebsiteEditorProvider");
  return ctx;
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export function WebsiteEditorProvider({ children }: { children: React.ReactNode }) {
  const { currentOrganizationId: orgId, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canWrite = hasPermission("website:write");
  const canPublish = hasPermission("website:publish");
  const query = useQuery({ queryKey: ["website-admin", orgId], queryFn: websiteAdmin.get, enabled: !!orgId && canWrite, refetchOnWindowFocus: false });
  const [working, setWorking] = useState<{ base: number; doc: WebsiteDocument } | null>(null);

  const state = query.data;
  // The working copy follows the server until the admin edits something.
  const doc = working && state && working.base === state.lock_version ? working.doc : state?.draft;
  const dirty = !!(working && state && working.base === state.lock_version && JSON.stringify(working.doc) !== JSON.stringify(state.draft));

  const accept = useCallback((next: WebsiteState) => {
    queryClient.setQueryData(["website-admin", orgId], next);
    setWorking(null);
    void queryClient.invalidateQueries({ queryKey: ["website-versions", orgId] });
  }, [queryClient, orgId]);

  const onError = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.code === "website_edit_conflict") {
      toast.error("Someone else saved the website meanwhile. Your changes are still here; copy anything you need, then reload.", { duration: 10_000 });
    } else toast.error(errorMessage(e));
  }, []);

  const saveM = useMutation({ mutationFn: () => websiteAdmin.saveDraft(doc!, state!.lock_version), onSuccess: (r) => { accept(r); toast.success("Draft saved"); }, onError });
  const publishM = useMutation({
    mutationFn: async (note: string) => {
      let lock = state!.lock_version;
      if (dirty) lock = (await websiteAdmin.saveDraft(doc!, lock)).lock_version;
      return websiteAdmin.publish(lock, note);
    },
    onSuccess: (r) => { accept(r); toast.success(`Published version ${r.published_version}`); },
    onError,
  });

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const value = useMemo<EditorValue | null>(() => (state && doc ? {
    doc, state, dirty, canWrite, canPublish,
    update: (fn) => setWorking({ base: state.lock_version, doc: fn(clone(doc)) }),
    save: async () => { try { await saveM.mutateAsync(); return true; } catch { return false; } },
    saving: saveM.isPending,
    publish: async (note = "") => { try { await publishM.mutateAsync(note); return true; } catch { return false; } },
    publishing: publishM.isPending,
    reload: () => { setWorking(null); void query.refetch(); },
  } : null), [state, doc, dirty, canWrite, canPublish, saveM, publishM, query]);

  if (!canWrite) return <p className="rounded-xl border p-6 text-sm text-muted-foreground">You need the “Edit the public website” permission to manage the website.</p>;
  if (query.isLoading || !value) return query.isError ? <p className="rounded-xl border p-6 text-sm text-destructive">{errorMessage(query.error)}</p> : <Skeleton className="h-96" />;
  return <EditorContext.Provider value={value}>{children}</EditorContext.Provider>;
}

export function EditorToolbar() {
  const { state, dirty, save, saving, publish, publishing, canPublish, reload } = useEditor();
  const status = dirty ? <Badge variant="outline" className="border-amber-400 text-amber-700">Unsaved changes</Badge>
    : state.has_unpublished_changes ? <Badge variant="outline">Draft not published</Badge>
      : <Badge variant="outline" className="border-emerald-400 text-emerald-700">Live · version {state.published_version}</Badge>;
  return (
    <div className="sticky top-0 z-20 -mx-4 mb-6 flex flex-wrap items-center gap-2 border-b bg-background/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6" data-testid="website-toolbar">
      {status}
      <span className="hidden text-xs text-muted-foreground sm:inline">{state.published_at ? `Last published ${new Date(state.published_at).toLocaleString("en-IN")}` : "Not published yet. Visitors see a starter site built from your clinic profile."}</span>
      <div className="ml-auto flex flex-wrap gap-2">
        {dirty ? <Button variant="ghost" size="sm" onClick={reload}><Undo2 /> Undo changes</Button> : null}
        <Button variant="outline" size="sm" asChild><Link href={state.public_url_path} target="_blank"><ExternalLink /> View live site</Link></Button>
        <Button variant="outline" size="sm" asChild><Link href="/admin/website/publish"><Eye /> Preview</Link></Button>
        <Button variant="outline" size="sm" onClick={() => void save()} disabled={!dirty || saving} data-testid="save-draft">{saving ? <Loader2 className="animate-spin" /> : <Save />} Save draft</Button>
        {canPublish ? <Button size="sm" onClick={() => void publish()} disabled={publishing || (!dirty && !state.has_unpublished_changes)} data-testid="publish">{publishing ? <Loader2 className="animate-spin" /> : <Send />} Publish</Button> : null}
      </div>
    </div>
  );
}
