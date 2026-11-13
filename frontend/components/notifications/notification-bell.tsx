"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { inboxService } from "@/services/notifications";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { InboxItem } from "@/types/notification";

export function NotificationBell() {
  const { user, memberships, currentOrganizationId, setCurrentOrganizationId } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const inbox = useQuery({ queryKey: ["inbox", user?.id], queryFn: () => inboxService.mine(), enabled: !!user, refetchInterval: 60_000, refetchOnWindowFocus: true });
  const read = useMutation({ mutationFn: (ids?: string[]) => inboxService.markRead(ids), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inbox"] }) });
  if (!user) return null;
  const unread = inbox.data?.unread ?? 0;

  const open = (item: InboxItem) => {
    if (!item.read_at) read.mutate([item.id]);
    if (item.organization_id && item.organization_id !== currentOrganizationId && memberships.some((m) => m.organization.id === item.organization_id)) {
      setCurrentOrganizationId(item.organization_id);
    }
    if (item.link) router.push(item.link);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="relative grid size-9 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} data-testid="notification-bell">
          <Bell className="size-[18px]" />
          {unread ? <span className="absolute -top-0.5 -right-0.5 grid min-w-[18px] place-items-center rounded-full bg-destructive px-1 text-[10px] leading-[18px] font-semibold text-white" data-testid="unread-count">{unread > 99 ? "99+" : unread}</span> : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(22rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between px-3 py-2">
          <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
          {unread ? <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={(e) => { e.preventDefault(); read.mutate(undefined); }}><CheckCheck className="size-3.5" /> Mark all read</Button> : null}
        </div>
        <DropdownMenuSeparator className="m-0" />
        <div className="max-h-96 overflow-y-auto" data-testid="inbox">
          {!inbox.data?.items.length ? <p className="px-3 py-8 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p> : inbox.data.items.map((item) => (
            <button key={item.id} type="button" onClick={() => open(item)} className={cn("flex w-full gap-2 border-b px-3 py-2.5 text-left text-sm last:border-0 hover:bg-muted/60", !item.read_at && "bg-primary/5")} data-testid="inbox-item">
              <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", item.read_at ? "bg-transparent" : "bg-primary")} />
              <span className="min-w-0 flex-1">
                <span className="block font-medium leading-snug">{item.title ?? item.body}</span>
                {item.title ? <span className="line-clamp-2 block text-xs text-muted-foreground">{item.body}</span> : null}
                <span className="block text-[11px] text-muted-foreground">{formatDateTime(item.created_at)}</span>
              </span>
            </button>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
