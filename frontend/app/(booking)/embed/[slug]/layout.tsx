import { BookingShell } from "@/components/public-booking/booking-shell";

// Shown inside other websites (e.g. a Shopify page). Which sites may frame it is decided per clinic in proxy.ts.
export const metadata = { title: "Book an appointment", robots: { index: false, follow: false } };

export default async function EmbeddedBookingLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <BookingShell slug={slug} embedded>{children}</BookingShell>;
}
