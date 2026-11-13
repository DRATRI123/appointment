import { Suspense } from "react";
import { AppointmentStatusPage } from "./status";

export default async function Page({ params }: { params: Promise<{ reference: string }> }) {
  const { reference } = await params;
  return (
    <Suspense>
      <AppointmentStatusPage reference={reference} />
    </Suspense>
  );
}
