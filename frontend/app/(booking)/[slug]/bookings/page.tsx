import type { Metadata } from "next";
import { DeviceBookingsPage } from "@/components/website/pages";

export const metadata: Metadata = { title: "My bookings", robots: { index: false, follow: false } };

export default function ClinicBookingsPage() {
  return <DeviceBookingsPage />;
}
