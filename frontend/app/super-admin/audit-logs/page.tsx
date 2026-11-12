"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { platformService } from "@/services/platform";
import { PageHeader } from "@/components/layout/page-header";
import { AuditLogTable } from "@/components/audit-log-table";

export default function PlatformAuditLogsPage() {
  const [page, setPage] = useState(1);
  const logs = useQuery({ queryKey: ["platform-audit", page], queryFn: () => platformService.auditLogs({ page, page_size: 25 }) });
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Platform audit logs" description="All organizations, including platform-level actions and impersonation." />
      <AuditLogTable page={logs.data} isLoading={logs.isLoading} onPage={setPage} />
    </div>
  );
}
