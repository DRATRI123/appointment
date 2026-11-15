import { redirect } from "next/navigation";
import { SiteHome } from "@/components/website/pages";

const BOOKING_HINTS = ["service", "branch", "location", "doctor", "professional", "date"];

/**
 * The clinic website. Links made for the booking page before it had a website (e.g. Shopify buttons with
 * ?service=consultation) are forwarded to /{clinic}/book with their parameters, so they keep working.
 */
export default async function ClinicHomePage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const [{ slug }, query] = await Promise.all([params, searchParams]);
  if (BOOKING_HINTS.some((k) => typeof query[k] === "string")) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (typeof v === "string") qs.set(k, v);
    redirect(`/${slug}/book?${qs.toString()}`);
  }
  return <SiteHome />;
}
