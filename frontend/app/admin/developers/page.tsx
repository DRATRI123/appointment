"use client";

import { useState } from "react";
import { Code2 } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/empty-state";
import { ApiKeysPanel } from "@/components/developers/api-keys-panel";
import { DocsPanel } from "@/components/developers/docs-panel";
import { WebhooksPanel } from "@/components/developers/webhooks-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function DevelopersPage() {
  const { hasPermission } = useAuth();
  const [tab, setTab] = useState("keys");
  if (!hasPermission("api_keys:manage")) return <EmptyState icon={Code2} title="No access" body="Ask an owner or administrator to manage API keys and webhooks." />;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title="Developers" description="Connect your website, CRM or automation tools with API keys and webhooks." />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList><TabsTrigger value="keys">API keys</TabsTrigger><TabsTrigger value="webhooks">Webhooks</TabsTrigger><TabsTrigger value="docs">Docs</TabsTrigger></TabsList>
        <TabsContent value="keys" className="pt-4"><ApiKeysPanel /></TabsContent>
        <TabsContent value="webhooks" className="pt-4"><WebhooksPanel /></TabsContent>
        <TabsContent value="docs" className="pt-4"><DocsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
