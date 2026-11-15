import type { Metadata } from "next";
import { DocsView } from "@/components/developers/docs/docs-view";

export const metadata: Metadata = { title: "Developer docs" };

export default async function DeveloperDocsPage({ params }: { params: Promise<{ page: string }> }) {
  const { page } = await params;
  return <DocsView slug={page} />;
}
