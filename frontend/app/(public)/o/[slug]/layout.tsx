import type { Metadata } from "next";
import { OrgProvider } from "./org-provider";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return { title: `Book with ${slug.replace(/-/g, " ")}` };
}

export default async function OrgLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <OrgProvider slug={slug}>{children}</OrgProvider>;
}
