import { Suspense } from "react";
import { BookingFlow } from "@/components/public-booking/booking-flow";

export default function PublicBookingPage() {
  return (
    <Suspense>
      <BookingFlow />
    </Suspense>
  );
}
