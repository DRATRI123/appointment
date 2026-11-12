"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import { organizationsService } from "@/services/organizations";
import { PageHeader } from "@/components/layout/page-header";
import { AuditLogTable } from "@/components/audit-log-table";
import { Input } from "@/components/ui/input";

export default function AuditLogsPage() {
  const { currentOrganizationId: orgId } = useAuth();
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const logs = useQuery({
    queryKey: ["audit-logs", orgId, page, action],
    queryFn: () => organizationsService.auditLogs(orgId!, { page, page_size: 25, action: action || undefined }),
    enabled: !!orgId,
  });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Audit logs"
        description="Every privileged action in this organization, with who did it and what changed."
        actions={<Input placeholder="Filter by action, e.g. staff." className="w-64" value={action} onChange={(e) => { setPage(1); setAction(e.target.value); }} />}
      />
      <AuditLogTable page={logs.data} isLoading={logs.isLoading} onPage={setPage} />
    </div>
  );
}
