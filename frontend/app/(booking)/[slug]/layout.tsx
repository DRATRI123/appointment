import type { Metadata } from "next";
import { BookingShell } from "@/components/public-booking/booking-shell";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const name = slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return { title: `Book an appointment · ${name}`, description: `Book an appointment with ${name} online in a few steps.` };
}

export default async function PublicBookingLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <BookingShell slug={slug}>{children}</BookingShell>;
}
