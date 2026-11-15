import type { Metadata } from "next";
import { BookPage } from "@/components/website/pages";
import { siteMetadata } from "@/lib/site-metadata";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return siteMetadata(slug, { title: "Book an appointment" });
}

export default function ClinicBookPage() {
  return <BookPage />;
}
