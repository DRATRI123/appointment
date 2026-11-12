"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LayoutList, Plus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { catalogService } from "@/services/catalog";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/forms/field";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import type { Category } from "@/types/catalog";

export default function CategoriesPage() {
  const { hasPermission, currentOrganizationId: orgId } = useAuth();
  const canWrite = hasPermission("services:write");
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ["categories", orgId], queryFn: catalogService.categories, enabled: !!orgId });
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["categories", orgId] });
  const remove = useMutation({
    mutationFn: (id: string) => catalogService.deleteCategory(id),
    onSuccess: () => { toast.success("Category deleted"); invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Service categories" description="Group services the way customers browse them: general consultation, skin, weight management, follow-ups…" actions={canWrite ? <Button onClick={() => setEditing("new")}><Plus /> Add category</Button> : null} />
      {categories.isLoading ? <Skeleton className="h-48" /> : categories.data?.length === 0 ? (
        <EmptyState icon={LayoutList} title="No categories yet" body="Create categories, then assign services to them." action={canWrite ? <Button onClick={() => setEditing("new")}>Add category</Button> : undefined} />
      ) : (
        <Table>
          <TableHeader><TableRow><TableHead>Category</TableHead><TableHead>Slug</TableHead><TableHead>Services</TableHead><TableHead>Status</TableHead>{canWrite ? <TableHead className="text-right">Actions</TableHead> : null}</TableRow></TableHeader>
          <TableBody>
            {categories.data?.map((c) => (
              <TableRow key={c.id} data-testid="category-row">
                <TableCell className="font-medium">{c.name}{c.description ? <p className="text-xs font-normal text-muted-foreground">{c.description}</p> : null}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{c.slug}</TableCell>
                <TableCell>{c.service_count}</TableCell>
                <TableCell><Badge variant={c.is_active ? "success" : "destructive"}>{c.is_active ? "active" : "inactive"}</Badge></TableCell>
                {canWrite ? (
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>Edit</Button>
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Delete ${c.name}? Its services stay but become uncategorised.`)) remove.mutate(c.id); }}>Delete</Button>
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {editing ? <CategoryDialog category={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); invalidate(); }} /> : null}
    </div>
  );
}

function CategoryDialog({ category, onClose, onSaved }: { category: Category | null; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState({ name: category?.name ?? "", description: category?.description ?? "", sort_order: category?.sort_order ?? 0, is_active: category?.is_active ?? true });
  const save = useMutation({
    mutationFn: () => (category ? catalogService.updateCategory(category.id, { ...draft, description: draft.description || null }) : catalogService.createCategory({ ...draft, description: draft.description || null })),
    onSuccess: () => { toast.success(category ? "Category updated" : "Category created"); onSaved(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{category ? "Edit category" : "New category"}</DialogTitle></DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="category-form">
          <Field label="Name" htmlFor="c_name"><Input id="c_name" required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
          <Field label="Description" htmlFor="c_desc"><Textarea id="c_desc" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Sort order" htmlFor="c_sort"><Input id="c_sort" type="number" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value) })} /></Field>
            <label className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>Active</span><Switch checked={draft.is_active} onCheckedChange={(v) => setDraft({ ...draft, is_active: v })} /></label>
          </div>
          <DialogFooter><Button type="submit" disabled={save.isPending}>{category ? "Save" : "Create"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
