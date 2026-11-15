import type { Metadata } from "next";
import { DocsView } from "@/components/developers/docs/docs-view";

export const metadata: Metadata = { title: "Developer docs" };

export default function DeveloperDocsHome() {
  return <DocsView slug="overview" />;
}
