import { Suspense } from "react";
import { AppointmentStatus } from "@/components/public-booking/appointment-status";

export const metadata = { title: "Your appointment", robots: { index: false, follow: false } };

export default async function AppointmentPage({ params }: { params: Promise<{ reference: string }> }) {
  const { reference } = await params;
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Suspense>
        <AppointmentStatus reference={reference} />
      </Suspense>
    </div>
  );
}
